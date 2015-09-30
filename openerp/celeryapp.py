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


from xoutil import logger  # noqa
from xoutil.context import context

from kombu import Exchange, Queue

import celery.exceptions
from celery import Celery as _CeleryApp

import openerp.tools.config as config
from openerp.api import Environment
from openerp.modules.registry import RegistryManager

from psycopg2 import OperationalError, errorcodes

PG_CONCURRENCY_ERRORS_TO_RETRY = (
    errorcodes.LOCK_NOT_AVAILABLE,
    errorcodes.SERIALIZATION_FAILURE,
    errorcodes.DEADLOCK_DETECTED
)


# A context for jobs.  All jobs will be executed in this context.
CELERY_JOB = object()

# A context to explicitly avoid jobs.
AVOID_JOB = object()


class Configuration(object):
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
    CELERY_CREATE_MISSING_QUEUES = True

    CELERYD_TASK_TIME_LIMIT = 600  # 10 minutes
    CELERYD_TASK_SOFT_TIME_LIMIT = 540  # 9 minutes

    CELERY_ENABLE_REMOTE_CONTROL = True

    # Since our workers are embedded in the Odoo process, we can't turn off
    # the server without shutting the workers down.  So it's probably best to
    # keep the tasks in the broker until a worker has finished with them.
    #
    #                                .
    #                               / \
    #                              / ! \
    #                             -------
    #
    # WARNING! You may do otherwise, but then you have to consider shutting
    # down the HTTP downstream server first, wait for all jobs to finish and
    # then shutdown then server.
    CELERY_ACKS_LATE = True


app = _CeleryApp(__name__)
app.config_from_object(Configuration)


# Since a model method may be altered in several addons, we funnel all calls to
# execute a method in a single Celery task.
@app.task(bind=True, max_retries=5)
def task(self, dbname, uid, model, methodname, args, kwargs):
    with Environment.manage():
        registry = RegistryManager.get(dbname)
        with registry.cursor() as cr:
            method = getattr(registry[model], methodname)
            if method:
                # It's up to the user to return transferable things.
                try:
                    with context(CELERY_JOB, job=self):
                        return method(cr, uid, *args, **kwargs)
                except celery.exceptions.SoftTimeLimitExceeded:
                    cr.rollback()
                    raise
                except OperationalError as error:
                    cr.rollback()
                    if error.pgcode not in PG_CONCURRENCY_ERRORS_TO_RETRY:
                        raise
                    else:
                        self.retry(error)  # This raises a Retry exception
                finally:
                    # The following is a hackish and not robust way to notify
                    # the Odoo Bus about the completion of the task.
                    #
                    # Technically we're still inside the task and the result
                    # is yet to be transmitted to the backend.  In fact, the
                    # following call might fail at the DB.
                    #
                    # This will be of course removed and the bus modified so
                    # that proper completion of tasks be notified.
                    import sys
                    error = sys.exc_info()[1] if sys.exc_info() else None
                    try:
                        registry['bus.bus'].sendone(
                            cr, uid, 'celeryapp:%s' % self.request.id,
                            dict(
                                uuid=self.request.id,
                                status='success' if not error else 'failed'
                            )
                        )
                    except:
                        # Avoid having the task failed because of the failure
                        # on the notification
                        pass
            else:
                raise TypeError(
                    'Invalid method name %r for model %r' % (methodname, model)
                )


def _getargs(model, cr, uid, method, *args, **kwargs):
    from openerp.models import Model
    from openerp.sql_db import Cursor
    if isinstance(model, Model):
        model = model._name
    if isinstance(cr, Cursor):
        dbname = cr.dbname
    else:
        dbname = cr
    return (dbname, uid, model, method, args, kwargs)


def Deferred(model, cr, uid, method, *args, **kwargs):
    '''Request to run a method in a celery worker.

    The job will be routed to the 'default' priority queue.

    :param model: The Odoo model.
    :param cr: The cursor or the DB name.
    :param uid: The user id.
    :param method: The name of method to run.

    :returns: An AsyncResult that represents the job.

    '''
    args = _getargs(model, cr, uid, method, *args, **kwargs)
    return task.apply_async(queue='default', args=args)


def HighPriorityDeferred(model, cr, uid, method, *args, **kwargs):
    '''Request to run a method in a celery worker.

    The job will be routed to the 'high' priority queue.

    :param model: The Odoo model.
    :param cr: The cursor or the DB name.
    :param uid: The user id.
    :param method: The name of method to run.

    :returns: An AsyncResult that represents the job.

    '''
    args = _getargs(model, cr, uid, method, *args, **kwargs)
    return task.apply_async(queue='high', args=args)


def LowPriorityDeferred(model, cr, uid, method, *args, **kwargs):
    '''Request to run a method in a celery worker.

    The job will be routed to the 'low' priority queue.

    :param model: The Odoo model.
    :param cr: The cursor or the DB name.
    :param uid: The user id.
    :param method: The name of method to run.

    :returns: An AsyncResult that represents the job.

    '''
    args = _getargs(model, cr, uid, method, *args, **kwargs)
    return task.apply_async(queue='low', args=args)


@app.task(max_retries=0)
def long_debug_task(cycles=100):
    import time
    for _ in range(cycles):
        time.sleep(2)
