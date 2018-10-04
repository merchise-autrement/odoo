#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# takeover
# ---------------------------------------------------------------------
# Copyright (c) 2015-2017 Merchise Autrement and Contributors
# All rights reserved.
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.
#
# Created on 2015-05-25

'''Implements the transfer of messages from one thread to another.

'''

from __future__ import (division as _py3_division,
                        print_function as _py3_print,
                        absolute_import as _py3_abs_import)

from odoo import api
from odoo.models import AbstractModel


class mail_thread(AbstractModel):
    _inherit = "mail.thread"

    @api.model
    def _merge_history(self, target_thread, previous_threads):
        'Transfer messages from previous_threads to target_thread.'
        Messages = self.env['mail.message']
        messages = Messages.browse(list({
            message.id
            for thread in previous_threads
            for message in thread.message_ids
        }))
        if any(messages):
            messages.write({'res_id': target_thread.id})
        return True

    @api.model
    def _merge_attachments(self, target_thread, previous_thread):
        'Transfer the attachments from previous_threads to target_thread.'
        def _get_attachments(thread_id):
            attachments = attach_obj.search(
                [('res_model', '=', self._name), ('res_id', '=', thread_id.id)],
            )
            return attachments
        attach_obj = self.env['ir.attachment']
        attachments = list({
            attachment
            for thread_id in previous_thread
            for attachment in _get_attachments(thread_id)
        })
        if any(attachments):
            attach_obj.write({'res_id': target_thread.id})
        return True

    @api.model
    def takeover_messages(self, target_thread, previous_threads):
        '''Take over messages belonging to previous threads into another.

        This should be used only to merge objects and:

        - Have the whole history from original objects merged in the target.

        - Have all attachments from original objects merged in the target.

        - Update the mail reference index so that references pointing to the
          original objects are properly redirected to the target.

        '''
        self._merge_history(target_thread, previous_threads)
        self._merge_attachments(target_thread, previous_threads)
        self._merge_index(target_thread, previous_threads)
        return True
