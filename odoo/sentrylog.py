#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# sentrylog
# ---------------------------------------------------------------------
# Copyright (c) 2015-2017 Merchise Autrement and Contributors
# All rights reserved.
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.
#
# Created on 2015-04-09

'''Extends/Overrides the OpenERP's logging system to Sentry-based approach.

Sentry_ aggregates logs and lets you inspect the server's health by a web
application.

To configure, simply set the global `conf`:obj: dictionary and call
`patch_logging`:func:.

'''

from __future__ import (division as _py3_division,
                        print_function as _py3_print,
                        absolute_import as _py3_abs_import)

import raven
from raven.transport.http import HTTPTransport
from raven.transport.threaded import ThreadedHTTPTransport
from raven.transport.gevent import GeventedHTTPTransport

from raven.utils.serializer.manager import manager as _manager, transform
from raven.utils.serializer import Serializer
from raven.utils.wsgi import get_headers, get_environ

try:
    import urlparse as _urlparse
except ImportError:
    import urllib.parse as _urlparse

# This module is about logging-only, not wrapping the WSGI application in a
# middleware, etc.

from xoutil.objects import setdefaultattr

from odoo import models

try:
    from xoutil.symbols import Unset
    from xoutil.symbols import boolean as Logical
except ImportError:
    from xoutil import Unset
    from xoutil.logical import Logical
Bail = Logical('Bail', False)
del Logical


# A dictionary holding the Raven's client keyword arguments.  You should
# modify this dictionary before patching the logging.
conf = {
    # The Sentry DSN.  If Bail no logging will be done to Sentry.  This should
    # be string like 'http://12345abc:091bacfe@sentry.example.com/0'.
    'dsn': Bail,

    # The release to be reported to Sentry.  If Unset, the openerp.release
    # version will be used.
    'release': Unset,

    # A tag that will be appended to the release.  Only if 'release' is Unset.
    'sentrylog.release-tag': '',

    # The Raven transport to use to connect to Sentry. One of 'sync',
    # 'gevent', or 'threaded'.  If set to None, default to 'threaded'.  In
    # fact any value other than 'sync', or 'gevent' will be regarded as
    # 'threaded'.
    'transport': 'threaded',

    # Only report errors with at least this level.
    'report_level': 'ERROR',

    # Other keyword arguments are passed unchanged to the Raven Client
    # object.  The following are interesting: environment, auto_log_stacks,
    # and capture_locals.
}

# The name of the context to the logger to avoid logging sentry-related
# errors.
SENTRYLOGGER = object()


# A singleton
_sentry_client = None


def get_client():
    global _sentry_client
    if not _sentry_client and conf.get('dsn', Bail):
        releasetag = conf.pop('sentrylog.release-tag', '')
        if not conf.get('release'):
            from .release import version
            conf['release'] = '%s/%s' % (version, releasetag)
        transport = conf.get('transport', None)
        if transport == 'sync':
            transport = HTTPTransport
        elif transport == 'gevent':
            transport = GeventedHTTPTransport
        else:
            transport = ThreadedHTTPTransport
        conf['transport'] = transport
        _sentry_client = raven.Client(**conf)
    return _sentry_client


def patch_logging(override=True, force=False):
    '''Patch openerp's logging.

    :param override: If True suppress all normal logging.  All logs will be
           sent to the Sentry instead of being logged to the console.  If
           False, extends the loogers to sent the errors to the Sentry but
           keep the console log as well.

    :param force: Ignored.  Just to provide compat with xoeuf.

    The Sentry will only receive the error-level messages.

    '''
    import logging
    from raven.handlers.logging import SentryHandler as Base

    def _require_httprequest(func):
        def inner(self, record):
            try:
                from openerp.http import request
                httprequest = getattr(request, 'httprequest', None)
                if httprequest:
                    return func(self, record, httprequest)
            except ImportError:
                # Not inside an HTTP request
                pass
            except RuntimeError:
                # When upgrading a DB the request may exists but the bound to
                # it does not.
                pass
        return inner

    class SentryHandler(Base):
        def _emit(self, record, **kwargs):
            self.set_record_tags(record)
            request_context = self._get_http_context(record)
            if request_context:
                self.client.http_context(request_context)
            user_context = self._get_user_context(record)
            if user_context:
                self.client.user_context(user_context)
            try:
                super(SentryHandler, self)._emit(record, **kwargs)
            except:
                # We should never fail if emitting the log to Sentry fails.
                # Neither we should print the error, other programs may think
                # we have fail because of it: For instance, the mailgate
                # integrated with postfix does.
                pass
            finally:
                self.client.context.clear()

        @_require_httprequest
        def _get_http_context(self, record, request):
            urlparts = _urlparse.urlsplit(request.url)
            return {
                'url': '%s://%s%s' % (urlparts.scheme, urlparts.netloc,
                                      urlparts.path),
                'query_string': urlparts.query,
                'method': request.method,
                'data': self._get_http_request_data(request),
                'headers': dict(get_headers(request.environ)),
                'env': dict(get_environ(request.environ)),
            }

        @_require_httprequest
        def _get_user_context(self, record, request):
            return {
                'id': getattr(request, 'session', {}).get('login', None)
            }

        def _handle_cli_tags(self, record):
            import sys
            from itertools import takewhile
            tags = setdefaultattr(record, 'tags', {})
            if sys.argv:
                cmd = ' '.join(
                    takewhile(lambda arg: not arg.startswith('-'),
                              sys.argv)
                )
            else:
                cmd = None
            if cmd:
                import os
                cmd = os.path.basename(cmd)
            if cmd:
                tags['cmd'] = cmd

        @_require_httprequest
        def _handle_browser_tags(self, record, request):
            tags = setdefaultattr(record, 'tags', {})
            ua = request.user_agent
            if ua:
                tags['os'] = ua.platform.capitalize()
                browser = str(ua.browser).capitalize() + ' ' + str(ua.version)
                tags['browser'] = browser

        @_require_httprequest
        def _handle_db_tags(self, record, request):
            db = getattr(request, 'session', {}).get('db', None)
            if db:
                tags = setdefaultattr(record, 'tags', {})
                tags['db'] = db

        def _handle_fingerprint(self, record):
            from xoutil.names import nameof
            exc_info = record.exc_info
            if exc_info:
                _type, value, _tb = exc_info
                exc = nameof(_type, inner=True, full=True)
                if exc.startswith('psycopg2.'):
                    fingerprint = [exc]
                else:
                    fingerprint = getattr(value, '_sentry_fingerprint', None)
                if fingerprint:
                    if not isinstance(fingerprint, list):
                        fingerprint = [fingerprint]
                    record.fingerprint = fingerprint

        def _get_http_request_data(self, request):
            from openerp.http import JsonRequest, HttpRequest
            from openerp.http import request  # Let it raise
            # We can't simply use `isinstance` cause request is actual a
            # 'werkzeug.local.LocalProxy' instance.
            if request._request_type == JsonRequest._request_type:
                return request.jsonrequest
            elif request._request_type == HttpRequest._request_type:
                return request.params
            else:
                return None

        def can_record(self, record):
            res = super(SentryHandler, self).can_record(record)
            if not res:
                return False
            exc_info = record.exc_info
            if not exc_info:
                return res
            from odoo.exceptions import UserError
            ignored = (UserError, )
            try:
                from odoo.exceptions import RedirectWarning
                ignored += (RedirectWarning, )
            except ImportError:
                pass
            from odoo.exceptions import except_orm
            ignored += (except_orm, )
            _type, value, _tb = exc_info
            return not isinstance(value, ignored)

        def set_record_tags(self, record):
            methods = (
                getattr(self, m)
                for m in dir(self) if m.startswith('_handle_')
            )
            for method in methods:
                method(record)

    client = get_client()
    if not client:
        return

    loglevel = conf.get('report_level', 'ERROR')
    level = getattr(logging, loglevel.upper(), logging.ERROR)
    override = conf.get('sentrylog.override', override)

    def sethandler(logger, override=override, level=level):
        handler = SentryHandler(client=client)
        handler.setLevel(level)
        if override or not logger.handlers:
            logger.handlers = [handler]
        else:
            logger.handlers.append(handler)

    for name in (None, 'openerp'):
        logger = logging.getLogger(name)
        sethandler(logger)


class OdooRecordSerializer(Serializer):
    """Expose Odoos local context variables from stacktraces.

    """
    types = (models.Model, )

    def serialize(self, value, **kwargs):
        from openerp.osv import fields
        try:
            if len(value) == 0:
                return transform((None, 'record with 0 items'))
            elif len(value) == 1:
                return transform({
                    attr: safe_getattr(value, attr)
                    for attr, val in value._columns.items()
                    # NOTE: Avoid function, they could be costly.
                    if not isinstance(val, fields.function)
                })
            else:
                return transform(
                    [self.serialize(record) for record in value]
                )
        except:
            return repr(value)


def safe_getattr(which, attr):
    try:
        from xoutil.symbols import Undefined
    except ImportError:
        from xoutil import Undefined
    try:
        return repr(getattr(which, attr, None))
    except:
        return Undefined

# _manager.register(OdooRecordSerializer)
del Serializer, _manager,
