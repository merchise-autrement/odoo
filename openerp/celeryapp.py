#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# celeryapp
# ---------------------------------------------------------------------
# Copyright (c) 2015 Merchise Autrement and Contributors
# All rights reserved.
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.
#
# Created on 2015-09-26

'''Odoo Celery Application.

Integrates Odoo and Celery, so that jobs can be started from the Odoo HTTP
workers and tasks can use the Odoo ORM.


'''

from __future__ import (division as _py3_division,
                        print_function as _py3_print,
                        absolute_import as _py3_abs_import)


from kombu import Exchange, Queue

import celery.exceptions
from celery import Celery as _CeleryApp

import openerp.tools.config as config
from openerp.api import Environment
from openerp.modules.registry import RegistryManager


class DefaultConfiguration(object):
    BROKER_URL = config.get('celery.broker', 'redis://localhost/9')
    CELERY_RESULT_BACKEND = config.get('celery.backend', BROKER_URL)

    CELERY_DEFAULT_QUEUE = 'default'
    CELERY_DEFAULT_EXCHANGE_TYPE = 'direct'
    CELERY_DEFAULT_ROUTING_KEY = 'default'

    CELERY_SEND_EVENTS = True
    CELERYD_MAX_TASKS_PER_CHILD = 2000

    # TODO: Take queues from configuration.
    CELERY_QUEUES = (
        Queue('default', Exchange('default'), routing_key='default'),
        Queue('high', Exchange('high'), routing_key='high'),
        Queue('low', Exchange('low'), routing_key='low'),
    )
    CELERY_CREATE_MISSING_QUEUES = False

    CELERYD_TASK_TIME_LIMIT = 600  # 10 minutes
    CELERYD_TASK_SOFT_TIME_LIMIT = 540  # 9 minutes

    CELERY_ENABLE_REMOTE_CONTROL = True

    CELERYD_AUTOSCALER = 'celery.worker.autoscale:Autoscaler'


app = _CeleryApp(__name__)
app.config_from_object(DefaultConfiguration)


# Since a model method may be altered in several addons, we funnel all calls to
# execute a method in a single Celery task.
@app.task
def task(dbname, uid, model, methodname, args, kwargs):
    with Environment.manage():
        registry = RegistryManager.get(dbname)
        with registry.cursor() as cr:
            method = getattr(registry[model], methodname)
            if method:
                # It's up to the user to return transferable things.
                try:
                    return method(cr, uid, *args, **kwargs)
                except celery.exceptions.SoftTimeLimitExceeded:
                    cr.rollback()
                    raise
            else:
                raise TypeError(
                    'Invalid method name %r for model %r' % (methodname, model)
                )


def Deferred(*args):
    return task.apply_async(queue='default', args=args)


def HighPriorityDeferred(*args):
    return task.apply_async(queue='high', args=args)


def LowPriorityDeferred(*args):
    return task.apply_async(queue='low', args=args)
