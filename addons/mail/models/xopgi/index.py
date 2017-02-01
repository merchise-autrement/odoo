#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# index
# ---------------------------------------------------------------------
# Copyright (c) 2015-2017 Merchise Autrement and Contributors
# All rights reserved.
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.
#
# Created on 2015-06-03

'''Maintains an referenced index to mail-threaded models.

The generated keys will contain only letters and digits, so you may easily
embed it using other symbol as a boundary mark.

'''

from __future__ import (division as _py3_division,
                        print_function as _py3_print,
                        absolute_import as _py3_abs_import)

from odoo.models import AbstractModel, Model
from odoo import fields, api

# NOTICE: In several methods we use the SUPERUSER_ID to make the sure the
# index works regardless of the user using the system.  BUT THIS SHOULD NOT BE
# DONE LIGHTLY.


# TODO: Move this to xoutil ?
def generate_reference(search, maxtries=4, start=1, lower=True):
    '''Generates an unused reference.

    :param search: A search callback to check if a candidate reference is
                   taken.

    :param maxtries:  How many times to try to find a reference.  This must be
                      at least 1.

    :param start: The minimum length for seeding.  This actually means how
                  many *more* UUIDs to generate at the very least.  This must
                  be at least 1.

    :param lower: If False, references will contain both upper and lower case
                  letters regarding them as different.  If True only lower
                  case letter will be used.

    References will contain only digits and letters.

    '''
    _TABLE = "0123456789abcdefghijklmnopqrstuvwxyz"
    if not lower:
        _TABLE += "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def encoder(*uuids):
        from xoutil.bases import int2str
        return ''.join(
            int2str(sum(uuid.fields), _TABLE)
            for uuid in uuids
        )

    import uuid
    ref, tries = None, 0
    if start < 1 or maxtries < 1:
        raise ValueError("Both 'start' and 'maxtries' must be at least 1")
    while not ref and (not maxtries or tries < maxtries):
        # This assumes you call create within a transaction, so we loop until
        # we find a non-used ref.  You need then to make sure the table where
        # the look up is made in a locked table or so.
        args = tuple(uuid.uuid4() for _ in range(start + tries))
        ref = encoder(*args)
        if search(ref):
            ref = None
        tries += 1
    return ref


MODULE_NAME = '__mail_threads__'


class MailThreadIndex(AbstractModel):
    '''An index from mail references to the actual model.

    We use a trick by injecting fake ir_model_data refs so that the index does
    not get lost if the addons is removed.

    This index allows, among many others:

    - To allow to avoid leaking ids in email address used by VERP and others.

    - To allow the merge of threads without loosing track of the merged
      threads.

    '''
    _inherit = "mail.thread"

    @api.multi
    def _get_message_index(self):
        for record in self:
            index = record._message_index().get(record.id, None)
            if index:
                record.thread_index = index

    thread_index = fields.Char(compute='_get_message_index', store=False)

    @api.model
    def _merge_index(self, target_thread, previous_threads,
                     samedomain=True):
        '''Make the index from previous threads point to another target thread.

        Useful when merging several threads into a single one.

        If `samedomain` is True all previous threads should belong to the same
        model of the target thread (self).  Threads from other models won't be
        merged in the index.

        '''
        assert self._name != 'mail.thread'
        params = dict(target=target_thread.id,
                      module=MODULE_NAME,
                      previous=tuple(previous_threads.ids))
        sets = 'res_id=%(target)s'
        if samedomain:
            domain = ' AND model=%(model)s'
            params.update(model=self._name)
        else:
            domain = ''
        query_template = '''
            UPDATE ir_model_data SET %(sets)s
            WHERE res_id in %%(previous)s AND module=%%(module)s %(domain)s
        '''
        query = query_template % dict(sets=sets, domain=domain)
        self.env.cr.execute(query, params)
        self.invalidate_cache()

    @api.model
    def _thread_by_index(self, index):
        '''Return the message that matches the X-Thread-Index.'''
        self.ensure_one()
        imd = self.env['ir.model.data']
        name = '%s.%s' % (MODULE_NAME, index)
        return imd.xmlid_to_object(name)

    @api.model
    def _threadref_by_index(self, index):
        '''Return the (model, res_id) thread that matches X-Thread-Index.'''
        self.ensure_one()
        imd = self.env['ir.model.data']
        name = '%s.%s' % (MODULE_NAME, index)
        return imd.xmlid_to_res_model_res_id(name)

    @api.multi
    def _message_index(self):
        '''Return a valid X-Thread-Index for the message.

        Returns a dictionary matching ids with indexes.

        '''
        query = '''
            SELECT name, res_id
            FROM ir_model_data
            WHERE model=%s AND res_id IN %s AND module=%s
        '''
        cr = self.env.cr
        cr.execute(query, (self._name, tuple(self.ids), MODULE_NAME))
        return {res_id: name for name, res_id in cr.fetchall()}

    @api.multi
    def _ensure_index(self):
        for thread in self:
            if not thread.thread_index:
                imd = self.env['ir.model.data']
                search = lambda r: self._thread_by_index(r)  # noqa: E731
                reference = generate_reference(search)
                if reference:
                    imd.create(
                        dict(name=reference,
                             model=self._name,
                             res_id=thread.id,
                             noupdate=True,
                             module=MODULE_NAME),
                    )

    @api.multi
    def unlink(self):
        imd = self.env['ir.model.data']
        refs = imd.sudo().search(
            [('module', '=', MODULE_NAME),
             ('model', '=', self._name),
             ('res_id', 'in', self.ids)])
        if refs:
            imd.unlink()
        return super(MailThreadIndex, self).unlink()


class MailMessage(Model):
    '''Adds a thread_index to messages.

    It will be a valid index for the thread it belongs to.

    '''
    _inherit = 'mail.message'

    @api.multi
    def _get_thread_index(self):
        for message in self:
            if message.model:
                model = self.env[message.model]
                record = model.browse(message.res_id)
                message.thread_index = record.thread_index

    thread_index = fields.Char(compute='_get_thread_index')
