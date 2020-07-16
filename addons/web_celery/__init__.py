#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------
# Copyright (c) Merchise Autrement [~º/~] and Contributors
# All rights reserved.
#
# This is free software; you can do what the LICENCE file allows you to.
#
"""Adds facilities to request backgrounds jobs and check for their status.

Features:

- A web client action that shows the Throbber until a job is done.

- Replaces the install button of a module for a background job.

"""
import time

import odoo
from odoo import _, api, models, http
from odoo.jobs import Deferred, CELERY_JOB, report_progress, terminate_task_with_env
from odoo.tools import config

from xotl.tools.context import context


def QUIETLY_WAIT_FOR_TASK(job, next_action=None):
    """The client action that waits quietly for a background job to complete.

    In this context *quietly* means just displaying the usual AJAX spinner.

    :param job:  The AsyncResult that represents the background job.
    :type job:  Any type compatible with celery's AsyncResult.

    :param next_action: The dictionary that represents the next action to
                        perform.  If None the background job is expected to
                        have returned a dictionary with the action to perform.

    .. warning:: Reloading after waiting for a background job will make the UI
                 to wait again for a job that's already finished and the UI
                 will stale.
    """
    if job is not None:
        return dict(
            type="web.celery.background_job",
            tag="block_no_progress",
            params=dict(uuid=job.id, next_action=next_action),
        )
    else:
        return CLOSE_FEEDBACK


def WAIT_FOR_TASK(job, next_action=None, cancellable=False):
    """The client action for waiting for a background job to complete.

    :param job:  The AsyncResult that represents the background job.
    :type job:  Any type compatible with celery's AsyncResult.

    :param next_action: The dictionary that represents the next action to
                        perform.  If None the background job is expected to
                        have returned a dictionary with the action to perform.

    :param cancellable: If True the user could cancel the background job.

    .. warning:: Reloading after waiting for a background job will make the UI
                 to wait again for a job that's already finished and the UI
                 will stale.

    """
    if job is not None:
        return dict(
            type="web.celery.background_job",
            tag="block_with_progress",
            params=dict(uuid=job.id, next_action=next_action, cancellable=cancellable),
        )
    else:
        return CLOSE_FEEDBACK


# The client action for closing the feedback mechanism we're using to show the
# user the progress of the background job.
CLOSE_FEEDBACK = None
CLOSE_PROGRESS_BAR = CLOSE_FEEDBACK


# The following is just a proof of concept.
#
# This makes the install button of modules to go to a background job.  This
# will only be activated in DEBUG mode.
#
# It is STRONGLY discouraged to make existing methods go to a background job,
# other addons may break if you do this.  The recommended way is to create
# your own methods and call them from the UI.
#
class Module(models.Model):
    _inherit = "ir.module.module"

    @api.multi
    def button_immediate_install(self):
        if CELERY_JOB in context or not config.get("dev_mode") or not odoo.multi_process:
            report_progress(
                message=_("Installation has begun, wait for a minute or two to finish."),
                progress=0,
                valuemin=0,
                valuemax=100,
            )
            for progress in range(1, 25, 4):
                report_progress(progress=progress)
                time.sleep(0.86)
            res = super(Module, self).button_immediate_install()
            for progress in range(progress, 101, 4):
                report_progress(progress=progress)
                time.sleep(0.26)
            report_progress(progress=100)
            return res
        else:
            return WAIT_FOR_TASK(Deferred(self.button_immediate_install))


class CeleryController(http.Controller):
    @http.route("/web_celery/!cancel/<uuid:identifier>", auth="user", type="json", methods=["POST"])
    def cancel_job_uid(self, identifier=None, **post):
        if identifier:
            terminate_task_with_env(identifier, http.request.env)
