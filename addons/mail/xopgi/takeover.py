#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# takeover
# ---------------------------------------------------------------------
# Copyright (c) 2015 Merchise Autrement and Contributors
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

from openerp.addons.mail.mail_thread import mail_thread as _base_mail_thread
from openerp.osv.orm import AbstractModel

from xoeuf.osv.orm import get_modelname


class mail_thread(AbstractModel):
    _name = get_modelname(_base_mail_thread)
    _inherit = _name

    def _merge_history(self, cr, uid, target_thread_id, previous_threads,
                       context=None):
        'Transfer messages from previous_threads to target_thread.'
        Messages = self.pool.get('mail.message')
        ids = []
        for thread in previous_threads:
            ids.extend(m.id for m in thread.message_ids)
        if ids:
            Messages.write(
                cr, uid,
                ids,
                {'res_id': target_thread_id, },
                context=context
            )
        return True

    def _merge_attachments(self, cr, uid, target_thread_id, previous_threads,
                           context=None):
        'Transfer the attachments from previous_threads to target_thread.'
        def _get_attachments(thread_id):
            attachments = attach_obj.search(
                cr, uid,
                [('res_model', '=', self._name), ('res_id', '=', thread_id)],
                context=context
            )
            return attachments
        attach_obj = self.pool.get('ir.attachment')
        ids = []
        for thread in previous_threads:
            ids.extend(_get_attachments(thread.id))
        if ids:
            attach_obj.write(
                cr, uid,
                ids,
                {'res_id': target_thread_id, },
                context=context
            )
        return True

    def takeover_messages(self, cr, uid, target_thread_id, previous_ids,
                          context=None):
        '''Take over messages belonging to previous threads into another.

        '''
        # TODO: Verify what happens when Odoo receives a reply to a previous
        # thread and document it.
        previous_thread = self.browse(cr, uid, previous_ids, context=context)
        self._merge_history(cr, uid, target_thread_id, previous_thread,
                            context=context)
        self._merge_attachments(cr, uid, target_thread_id, previous_thread,
                                context=context)
        return True
