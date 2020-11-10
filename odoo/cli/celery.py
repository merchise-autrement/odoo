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
import sys
import signal
import atexit
import logging

import click

from celery.bin.celery import celery
from celery.bin.base import CeleryCommand

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
        from odoo.jobs import app  # noqa: discover the app
        from celery.bin.celery import celery as celerycli
        from raven.contrib.celery import register_signal, register_logger_signal
        from odoo.sentrylog import get_client

        client = get_client()
        odoo.evented = False
        odoo.multi_process = True
        if client:
            register_logger_signal(client)
            register_signal(client)
        celerycli(args=cmdargs)


# TODO: Add all possible Flower options.
@celery.command(cls=CeleryCommand)
@click.option("--port", default=5555)
@click.option(
    "--logging",
    default="info",
    type=click.Choice(["info", "debug", "error", "warn"]),
)
@click.option(
    "--basic-auth",
    type=str,
    multiple=True,
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
    from tornado.options import options
    from flower.app import Flower
    from flower.urls import settings

    kwargs["basic_auth"] = list(kwargs["basic_auth"])
    for option, value in kwargs.items():
        setattr(options, option, value)
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


celery.add_command(flower)
