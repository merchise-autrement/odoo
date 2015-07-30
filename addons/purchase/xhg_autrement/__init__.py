#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# purchase_order (xhg_autrement)
# ---------------------------------------------------------------------
# Copyright (c) 2015 Merchise Autrement and Contributors
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


from openerp.models import Model
from openerp.osv import fields


# MERCHISE: This module introduces type-level (but compatible with assumptions
# in so far our testing).
#
# We need to place this module in the core of Odoo cause otherwise DB columns
# will be overridden.  We keep other changes in our custom addons.


class Purchase(Model):
    _name = _inherit = 'purchase.order'

    def _set_minimum_planned_date(self, cr, uid, ids, name, value, arg,
                                  context=None):

        _super = super(Purchase, self)._set_minimum_planned_date

        return _super(cr, uid, ids, name, value, arg, context=context)

    def _minimum_planned_date(self, cr, uid, ids, field_name, arg,
                              context=None):
        _super = super(Purchase, self)._minimum_planned_date

        return _super(cr, uid, ids, field_name, arg, context=context)

    def _get_purchase_order(self, cr, uid, ids, context=None):
        _super = super(Purchase, self)._get_purchase_order
        return _super(cr, uid, ids, context=context)

    def _get_order(self, cr, uid, ids, context=None):
        result = {}
        for line in self.pool['purchase.order.line'].browse(cr, uid, ids,
                                                            context=context):
            result[line.order_id.id] = True
        return result.keys()

    _columns = {
        'minimum_planned_date':
            fields.function(
                _minimum_planned_date,
                fnct_inv=_set_minimum_planned_date,
                string='Expected Date',
                type='datetime',
                select=True,
                help="This is computed as the minimum scheduled date of all "
                     "purchase order lines' products.",
                store={
                    'purchase.order.line': (_get_order, ['date_planned'], 10),
                    'purchase.order': (_get_purchase_order, ['order_line'], 10)
                }
            ),
    }
