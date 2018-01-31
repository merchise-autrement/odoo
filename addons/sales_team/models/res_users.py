# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    sale_teams = fields.Many2many(
        'crm.team',
        string="Sales Teams",
        relation='sale_member_rel',
        column1='user_id',
        column2='team_id',
        help="Sales Teams the user is member of."
    )
