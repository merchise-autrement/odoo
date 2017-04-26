#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# purchase_requisition (xhg_autrement)
# ---------------------------------------------------------------------
# Copyright (c) 2015-2017 Merchise Autrement and Contributors
# All rights reserved.
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.
#
# Created on 2015-07-29

from __future__ import (division as _py3_division,
                        print_function as _py3_print,
                        absolute_import as _py3_abs_import)


from odoo.models import Model
from odoo import fields


# MERCHISE: This module introduces type changes (but compatible with
# assumptions in so far our testing).
#
# We need to place this module in the core of Odoo cause otherwise DB columns
# will be overridden.  We keep other changes in our custom addons.
class Requisition(Model):
    _name = _inherit = 'purchase.requisition'

    schedule_date = fields.Datetime(
        string='Delivery Date',
        index=True,
        help=("The expected and scheduled delivery date where all the "
              "products are received")
    )


class RequisitionLine(Model):
    _name = _inherit = 'purchase.requisition.line'

    schedule_date = fields.Datetime('Scheduled Date')
