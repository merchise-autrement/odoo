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
            pos = argv.index('--')
        except ValueError:
            args, cmdargs = [], argv
        else:
            args, cmdargs = argv[:pos], argv[pos + 1:]
        odoo.tools.config.parse_config(args=args)
        from odoo.jobs import app  # noqa: discover the app
        from celery.bin.celery import main as _main
        odoo.evented = False
        odoo.multi_process = True
        _main(argv=['celery', ] + cmdargs)
