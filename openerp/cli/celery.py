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

from __future__ import (division as _py3_division,
                        print_function as _py3_print,
                        absolute_import as _py3_abs_import)


from . import Command


class Celery(Command):
    def run(self, cmdargs):
        import logging
        import openerp
        from openerp.jobs import app  # noqa: discover the app
        from openerp.sentrylog import get_client
        from celery.bin.celery import main as _main
        from raven.contrib.celery import register_signal, register_logger_signal
        client = get_client()
        if client:
            # register a custom filter to filter out duplicate logs
            register_logger_signal(client)
            # The register_logger_signal function can also take an optional
            # argument `loglevel` which is the level used for the handler created.
            # Defaults to `logging.ERROR`
            register_logger_signal(client, loglevel=logging.INFO)
            # hook into the Celery error handler
            register_signal(client)
            # The register_signal function can also take an optional argument
            # `ignore_expected` which causes exception classes specified in
            # Task.throws to be ignored
            register_signal(client, ignore_expected=True)
        openerp.evented = False
        # Some addons (specially report) think they live inside a cozy and
        # warm HTTP worker.  This is not True for jobs inside the celery
        # worker; in fact, this process is not a multi_process (with regards
        # to Odoo).
        openerp.multi_process = False
        _main(argv=['celery', ] + cmdargs)
