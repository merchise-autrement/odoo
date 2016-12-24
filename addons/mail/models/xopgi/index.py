#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# index
# ---------------------------------------------------------------------
# Copyright (c) 2015, 2016 Merchise Autrement and Contributors
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

from openerp import SUPERUSER_ID
from openerp.models import AbstractModel, fields, Model

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

    def _get_message_index(self, cr, uid, ids, fields, arg, context=None):
        result = dict.fromkeys(ids, None)  # Make sure to returns some value
        result.update(self._message_index(cr, uid, ids, context=context))
        return result

    _columns = dict(
        thread_index=fields.function(_get_message_index, type='char',
                                     store=False)
    )

    def _merge_index(self, cr, uid, target_thread_id, previous_threads_ids,
                     samedomain=True, context=None):
        '''Make the index from previous threads point to another target thread.

        Useful when merging several threads into a single one.

        If `samedomain` is True all previous threads should belong to the same
        model of the target thread (self).  Threads from other models won't be
        merged in the index.

        '''
        assert self._name != 'mail.thread'
        params = dict(target=target_thread_id,
                      module=MODULE_NAME,
                      previous=tuple(previous_threads_ids))
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
        cr.execute(query, params)

    def _thread_by_index(self, cr, uid, threadindex, context=None):
        '''Return the message that matches the X-Thread-Index.'''
        imd = self.pool['ir.model.data']
        name = '%s.%s' % (MODULE_NAME, threadindex)
        return imd.xmlid_to_object(cr, uid, name)

    def _threadref_by_index(self, cr, uid, threadindex, context=None):
        '''Return the (model, res_id) thread that matches X-Thread-Index.'''
        imd = self.pool['ir.model.data']
        name = '%s.%s' % (MODULE_NAME, threadindex)
        return imd.xmlid_to_res_model_res_id(cr, uid, name)

    def _message_index(self, cr, uid, ids, context=None):
        '''Return a valid X-Thread-Index for the message.

        Returns a dictionary matching ids with indexes.

        '''
        query = '''
            SELECT name, res_id
            FROM ir_model_data
            WHERE model=%s AND res_id IN %s AND module=%s
        '''
        cr.execute(query, (self._name, tuple(ids), MODULE_NAME))
        return {res_id: name for name, res_id in cr.fetchall()}

    def _ensure_index(self, cr, uid, ids, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        for thread in self.browse(cr, uid, ids, context=context):
            if not thread.thread_index:
                imd = self.pool['ir.model.data']
                search = lambda r: self._thread_by_index(
                    cr, uid, r, context=context
                )
                reference = generate_reference(search)
                if reference:
                    imd.create(
                        cr, uid,
                        dict(name=reference,
                             model=self._name,
                             res_id=thread.id,
                             noupdate=True,
                             module=MODULE_NAME),
                        context=context
                    )

    def unlink(self, cr, uid, ids, context=None):
        from xoutil.types import is_collection
        imd = self.pool['ir.model.data']
        if not is_collection(ids):
            ids = tuple(ids)
        refs = imd.search(
            cr, SUPERUSER_ID,
            [('module', '=', MODULE_NAME),
             ('model', '=', self._name),
             ('res_id', 'in', ids)])
        if refs:
            imd.unlink(cr, SUPERUSER_ID, refs)
        return super(MailThreadIndex, self).unlink(
            cr, uid, ids, context=context
        )


class MailMessage(Model):
    '''Adds a thread_index to messages.

    It will be a valid index for the thread it belongs to.

    '''
    _inherit = 'mail.message'

    def _get_thread_index(self, cr, uid, ids, fields, arg, context=None):
        result = dict.fromkeys(ids, None)
        for message in self.browse(cr, SUPERUSER_ID, ids, context=context):
            if message.model:
                model = self.pool[message.model]
                record = model.browse(cr, SUPERUSER_ID, message.res_id)
                result[message.id] = record.thread_index
        return result

    _columns = dict(
        thread_index=fields.function(_get_thread_index, type='char')
    )
