#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------
# Copyright (c) 2017 Merchise Autrement [~º/~] and Contributors
# All rights reserved.
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.
#
# Created on 2017-01-30
import atexit
import logging
import signal
import sys

import click
from celery.bin.base import CeleryCommand
from celery.bin.celery import celery

from . import Command

logger = logging.getLogger(__name__)


class Celery(Command):
    def run(self, argv):
        import odoo

        # We need to bootstrap the Odoo logging and addons, so we must parse
        # the args.  Otherwise errors won't get logged to Sentry even if it's
        # configured.
        #
        # Use the '--' to separate Odoo arguments from Celery's:
        #
        #     odoo celery [odoo arguments --] ...
        try:
            pos = argv.index("--")
        except ValueError:
            args, cmdargs = [], argv
        else:
            args, cmdargs = argv[:pos], argv[pos + 1 :]
        odoo.tools.config.parse_config(args=args)

        from celery.bin.celery import celery as celerycli

        from odoo.jobs import app  # noqa: discover the app
        from odoo.sentrylog import setup_sentry
        setup_sentry()

        odoo.evented = False
        odoo.multi_process = True
        celerycli(args=cmdargs)


# TODO: Add all possible Flower options.
# Most of this is copied from flower's command code.
@celery.command(cls=CeleryCommand)
@click.option(
    "--debug",
    default=False,
    is_flag=True,
)
@click.option("--port", default=5555)
@click.option(
    "--logging",
    default="info",
    type=click.Choice(["info", "debug", "error", "warn"]),
)
@click.option(
    "--basic_auth",
    "--basic-auth",
    type=str,
    multiple=True,
    callback=lambda ctx, param, value: list(value),
)
@click.option(
    "--log-to-stderr",
    default=False,
    type=bool,
    is_flag=True,
)
@click.option("--url-prefix", type=str)
@click.pass_context
def flower(ctx, **kwargs):
    "Runs flower to monitor the workers"
    from flower.app import Flower
    from flower.urls import settings
    from tornado.options import options

    apply_env_options(options)
    for option, value in kwargs.items():
        setattr(options, option, value)
    extract_settings(options, settings)
    setup_logging(options)

    ctx.obj.app.loader.import_default_modules()
    flower = Flower(capp=ctx.obj.app, options=options, **settings)
    atexit.register(flower.stop)

    def sigterm_handler(signal, frame):
        logger.info("SIGTERM detected, shutting down")
        sys.exit(0)

    signal.signal(signal.SIGTERM, sigterm_handler)

    try:
        flower.start()
    except (KeyboardInterrupt, SystemExit):
        pass


def extract_settings(options, settings):
    import os

    from flower.utils import abs_path, prepend_url

    settings["debug"] = options.debug

    if options.cookie_secret:
        settings["cookie_secret"] = options.cookie_secret

    if options.url_prefix:
        for name in ["login_url", "static_url_prefix"]:
            settings[name] = prepend_url(settings[name], options.url_prefix)

    if options.auth:
        settings["oauth"] = {
            "key": options.oauth2_key or os.environ.get("FLOWER_OAUTH2_KEY"),
            "secret": options.oauth2_secret or os.environ.get("FLOWER_OAUTH2_SECRET"),
            "redirect_uri": options.oauth2_redirect_uri
            or os.environ.get("FLOWER_OAUTH2_REDIRECT_URI"),
        }

    if options.certfile and options.keyfile:
        settings["ssl_options"] = dict(
            certfile=abs_path(options.certfile), keyfile=abs_path(options.keyfile)
        )
        if options.ca_certs:
            settings["ssl_options"]["ca_certs"] = abs_path(options.ca_certs)


def apply_env_options(options):
    "apply options passed through environment variables"
    import os

    env_options = filter(is_flower_envvar, os.environ)
    for env_var_name in env_options:
        name = env_var_name.replace(ENV_VAR_PREFIX, "", 1).lower()
        value = os.environ[env_var_name]
        try:
            option = options._options[name]
        except KeyError:
            option = options._options[name.replace("_", "-")]
        if option.multiple:
            value = [option.type(i) for i in value.split(",")]
        else:
            value = option.type(value)
        setattr(options, name, value)


def is_flower_envvar(name):
    from flower.options import default_options

    return (
        name.startswith(ENV_VAR_PREFIX) and name[len(ENV_VAR_PREFIX) :].lower() in default_options
    )


def setup_logging(options):
    from logging import NullHandler

    from tornado.log import enable_pretty_logging

    if options.debug and options.logging == "info":
        options.logging = "debug"
        enable_pretty_logging()
    else:
        logging.getLogger("tornado.access").addHandler(NullHandler())
        logging.getLogger("tornado.access").propagate = False


ENV_VAR_PREFIX = "FLOWER_"

celery.add_command(flower)
