#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# web_celery
# ---------------------------------------------------------------------
# Copyright (c) 2015-2017 Merchise Autrement [~º/~] and Contributors
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
        tag='wait_for_background_job',
        params=dict(
            uuid=job.id,
            next_action=next_action,
        )
    )
