# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


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

    @api.model
    def create(self, vals):
        # Assign the new user in the sales team if there's only one sales team of type `Sales`
        user = super(ResUsers, self).create(vals)
        if user.has_group('sales_team.group_sale_salesman') and not user.sale_teams:
            teams = self.env['crm.team'].search([('team_type', '=', 'sales')])
            if len(teams.ids) == 1:
                user.sale_teams |= teams
        return user
