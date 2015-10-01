#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# web_celery
# ---------------------------------------------------------------------
# Copyright (c) 2015 Merchise Autrement and Contributors
# All rights reserved.
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.
#
# Created on 2015-09-29

'''Adds facilities to request backgrounds jobs and check for their status.

Features:

- A web client action that shows the Throbber until a job is done.

- Replaces the install button of a module for a background job.

'''

from __future__ import (division as _py3_division,
                        print_function as _py3_print,
                        absolute_import as _py3_abs_import)


from xoutil.context import context

from openerp.jobs import CELERY_JOB, HighPriorityDeferred, report_progress
from openerp.models import Model
from openerp.tools.translate import _


def WAIT_FOR_TASK(job, next_action=None):
    '''The client action for waiting for a background job to complete.

    :param job:  The AsyncResult that represents the background job.
    :type job:  Any type compatible with celery's AsyncResult.

    :param next_action: The dictionary that represents the next action to
                        perform.  If None the background job is expected to
                        have returned a dictionary with the action to perform.

    .. warning:: Reloading after waiting for a background job will make the UI
                 to wait again for a job that's already finished and the UI
                 will stale.

    '''
    return dict(
        type='ir.actions.client',
        tag=('wait_for_background_job'
             if job.status in ('STARTED', 'PENDING')
             else next_action['tag']),
        params=dict(
            uuid=job.id,
            next_action=next_action,
        )
    )


# The following is just a proof of concept.
#
# This makes the install button of modules to go to a background job.  This
# will only be activated in DEBUG mode.
#
# It is STRONGLY discouraged to make existing methods go to a background job,
# other addons may break if you do this.  The recommended way is to create
# your own methods and call them from the UI.
#
class Module(Model):
    _name = _inherit = 'ir.module.module'

    def button_immediate_install(self, cr, uid, *args, **kw):
        import time
        import openerp.tools.config as config
        if CELERY_JOB in context or not config.get('debug_mode'):
            report_progress(
                message=_('Installing has begun, wait for a minute '
                          'or two to finish.'),
                progress=0,
                valuemin=0,
                valuemax=100,
            )
            for progress in range(1, 25, 4):
                report_progress(progress=progress)
                time.sleep(0.86)
            res = super(Module, self).button_immediate_install(
                cr, uid, *args, **kw
            )
            cr.commit()
            for progress in range(progress, 101, 4):
                report_progress(progress=progress)
                time.sleep(0.86)
            report_progress(progress=100)
            return res
        else:
            return WAIT_FOR_TASK(
                HighPriorityDeferred(
                    Module._name, cr, uid, 'button_immediate_install',
                    *args, **kw)
            )
