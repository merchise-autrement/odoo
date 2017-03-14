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
        import openerp
        from openerp.jobs import app  # noqa: discover the app
        from openerp.sentrylog import get_client
        from celery.bin.celery import main as _main
        openerp.evented = False
        # Some addons (specially report) think they live inside a cozy and
        # warm HTTP worker.  This is not True for jobs inside the celery
        # worker; in fact, this process is not a multi_process (with regards
        # to Odoo).
        openerp.multi_process = False
        _main(argv=['celery', ] + cmdargs)
