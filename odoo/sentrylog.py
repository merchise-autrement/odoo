#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------
# Copyright (c) Merchise Autrement [~º/~] and Contributors
# All rights reserved.
#
# This is free software; you can do what the LICENCE file allows you to.
#

"""Implement a very ad-hoc integration of Odoo with Sentry.

Events are captured with mostly captured with LoggingIntegration,
CeleryIntegration and RedisIntegration help a bit to provide the basic tags in
transaction profiling.

The WSGI transaction are only set for JsonRequest and HttpRequest.  The
ir.cron process also gets special attention to provide context in the
transactions.

SQL queries are also traced by default.

.. rubric:: Environment variables

:odoo_sentry_disable_sql_tracing: If present the SQL tracing is disabled.

:odoo_sentry_traces_sample_rate: A float between 0 and 1 to control the amount
                                 of tracing.  Defaults to 0.5 (i.e 50% of
                                 traces are actually sent).

:odoo_sentry_dsn: (required) The DSN of the project to send events.  If not
                  set, no integration with Sentry is done.

"""
import contextlib
import logging
import os
import sys
from itertools import takewhile
from types import MethodType
from urllib.parse import urlparse

import sentry_sdk
from sentry_sdk import Hub, set_tag, set_user, start_transaction
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.wsgi import get_request_url
from sentry_sdk.tracing import Transaction, record_sql_queries
from xotl.tools.symbols import boolean as Logical

import odoo
from odoo.addons.base.models.qweb import QWebException
from odoo.exceptions import MissingError, RedirectWarning, except_orm

Bail = Logical("Bail", False)
del Logical


try:
    _traces_sample_rate = float(
        os.environ.get(
            "odoo_sentry_traces_sample_rate",
            "0.5",
        )
    )
except ValueError:
    _traces_sample_rate = 0.5

# A dictionary holding the Sentry's Client keyword arguments.  You should
# modify this dictionary before patching the logging.
conf = {
    # The Sentry DSN.  If Bail no logging will be done to Sentry.  This should
    # be string like 'http://12345abc:091bacfe@sentry.example.com/0'.
    "dsn": os.environ.get("odoo_sentry_dsn", Bail),
    # The release to be reported to Sentry.  If Unset, the odoo.release
    # version will be used.
    "release": os.environ.get("odoo_sentry_release", odoo.release.version),
    "integrations": [
        CeleryIntegration(),
        RedisIntegration(),
        LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR,
        ),
    ],
    "traces_sample_rate": _traces_sample_rate,
    "send_default_pii": True,
}

default_environment = os.environ.get("odoo_sentry_environment", None)
if default_environment is not None:
    conf["environment"] = default_environment


# The name of the context to the logger to avoid logging sentry-related
# errors.
SENTRYLOGGER = object()


# When this is not None, all initialization has been done.
_sentry_client = None


def setup_sentry():
    from odoo.tools import config  # noqa

    global _sentry_client
    if not _sentry_client and conf.get("dsn", Bail):
        sentry_sdk.init(**conf)
        if conf.get('traces_sample_rate'):
            install_web_hook()
            install_ir_cron_hook()
            if not os.environ.get('odoo_sentry_disable_sql_tracing'):
                install_sql_hook()
        _sentry_client = Hub.current.client
    return _sentry_client


def install_web_hook():
    from odoo.http import HttpRequest, JsonRequest

    if not getattr(JsonRequest, "_patched_with_sentry", False):
        JsonRequest._patched_with_sentry = True
        real_json_dispatch = JsonRequest.dispatch

        def dispatch(self):
            with _endpoint_transaction(self.endpoint):
                return real_json_dispatch(self)

        JsonRequest.dispatch = dispatch

    if not getattr(HttpRequest, "_patched_with_sentry", False):
        HttpRequest._patched_with_sentry = True
        real_http_dispatch = HttpRequest.dispatch

        def dispatch(self):
            with _endpoint_transaction(self.endpoint):
                return real_http_dispatch(self)

        HttpRequest.dispatch = dispatch


@contextlib.contextmanager
def _endpoint_transaction(endpoint):
    method = getattr(endpoint, "method", None)
    if isinstance(method, MethodType):
        try:
            # The clsname may have spaces if the controller has been extended.
            clsname = type(method.__self__).__name__.split(" ")[0]
            methname = method.__name__
            transaction_name = f"{clsname}.{methname}"
            # TODO: If haven't found a better way to exclude the BusController
            if clsname == "BusController":
                transaction_name = None
        except AttributeError:
            transaction_name = None
    if transaction_name:
        transaction = Transaction(op="odoo.http", name=transaction_name)
        with Hub.current.start_transaction(transaction):
            try:
                from odoo.http import request
            except Exception:
                pass
            else:
                try:
                    set_user({"id": request.env.user.id, "email": request.env.user.login})
                except Exception:
                    pass
                try:
                    set_tag("dbname", request.env.cr.dbname)
                except Exception:
                    pass
            yield
    else:
        yield


def install_ir_cron_hook():
    from odoo import api
    from odoo.addons.base.models.ir_cron import ir_cron

    if not getattr(ir_cron, "_patched_with_sentry", False):
        ir_cron._patched_with_sentry = True
        real_callback = ir_cron._callback

        @api.model
        def _callback(self, cron_name, server_action_id, job_id):
            transaction = Transaction(op="ir.cron", name=f"Cron Job: {cron_name}")
            with Hub.current.start_transaction(transaction):
                try:
                    set_tag("cron_name", cron_name)
                    set_tag("dbname", self.env.cr.dbname)
                    set_user({"id": self.env.user.id, "email": self.env.user.login})
                except Exception:
                    pass
                return real_callback(self, cron_name, server_action_id, job_id)

        ir_cron._callback = _callback


def install_sql_hook():
    # type: () -> None
    """Capture the SQL queries"""
    from odoo.sql_db import Cursor

    if not getattr(Cursor, "_patched_with_sentry", False):
        Cursor._patched_with_sentry = True
        real_execute = Cursor.execute

        def execute(self, query, params=None, log_exceptions=None):
            if self._closed:
                return real_execute(self, query, params=params, log_exceptions=log_exceptions)
            with record_sql_queries(
                Hub.current,
                self._obj,
                query,
                params,
                paramstyle="format",
                executemany=False,
            ):
                return real_execute(self, query, params=params, log_exceptions=log_exceptions)

        Cursor.execute = execute


class SentryWsgiMiddleware:
    """A more suitable WSGI middleware for Odoo.

    Sentry's default WSGI middleware setup the transaction name to 'generic
    WSGI transaction' which is not very helpful.

    This Middleware sets the transaction to the PATH_INFO in the URL.

    .. seealso: `odoo.http.Root.load_addons`:meth:

    We recommend to set this middleware *below* the SharedDataMiddleware to
    remove statics from the report.

    """

    __slots__ = ("app",)

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        try:
            url = get_request_url(environ)
            parsed = urlparse(url)
            name = parsed.path
        except Exception:
            name = environ.get("PATH_INFO", "HTTP request")
        if name.startswith("/longpolling"):
            # TODO: Find a better way to know if we're in a longpolling
            # request to remove the trace.  We don't want traces from
            # longpolling because many of them take up to 50s just waiting
            # without actually affecting the user.
            return self.app(environ, start_response)
        transaction = Transaction.continue_from_environ(environ, op="odoo.http", name=name)
        with start_transaction(transaction):
            return self.app(environ, start_response)


def _require_httprequest(func):
    def inner(*args):
        try:
            from odoo.http import request

            httprequest = getattr(request, "httprequest", None)
            if httprequest:
                args += (httprequest,)
                return func(*args)
        except ImportError:
            # Not inside an HTTP request
            pass
        except RuntimeError:
            # When upgrading a DB the request may exists but the bound to
            # it does not.
            pass

    return inner


def _require_request(func):
    def inner(*args):
        try:
            from odoo.http import request

            args += (request,)
            return func(*args)
        except ImportError:
            # Not inside an HTTP request
            pass
        except RuntimeError:
            # When upgrading a DB the request may exists but the bound to
            # it does not.
            pass

    return inner


@_require_request
def _handle_user_context(request):
    try:
        sentry_sdk.set_user({"id": request.env.user.login})
    except AttributeError:
        return None


def _handle_cli_tags():
    if sys.argv:
        cmd = " ".join(takewhile(lambda arg: not arg.startswith("-"), sys.argv))
    else:
        cmd = None
    if cmd:
        cmd = os.path.basename(cmd)
    if cmd:
        sentry_sdk.set_tag("cmd", cmd)


@_require_httprequest
def _handle_browser_tags(request):
    ua = request.user_agent
    if ua:
        sentry_sdk.set_tag("os", ua.platform.capitalize())
        browser = str(ua.browser).capitalize() + " " + str(ua.version)
        sentry_sdk.set_tag("browser", browser)


@_require_httprequest
def _handle_db_tags(request):
    db = getattr(request, "session", {}).get("db", None)
    if db:
        sentry_sdk.set_tag("db", db)


def can_record(self, record):
    res = super().can_record(record)
    if not res:
        return False
    exc_info = record.exc_info
    if not exc_info:
        return res

    ignored = (QWebException, except_orm, RedirectWarning, MissingError)
    _type, value, _tb = exc_info
    return not isinstance(value, ignored)


def patch_logging():
    setup_sentry()
