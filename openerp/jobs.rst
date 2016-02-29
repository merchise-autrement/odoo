=======================
 Odoo backgrounds jobs
=======================

This document describes both the current state and plans for the
implementation of the integration of Odoo and Celery Task Queue.

We have use the `jobs` name because Celery is a means to an end, not the
"thing" we're trying to do.


Implementation details
======================

The idea is to have a single task definition that simply allows the execution
of any method in a model.

There are three queues defined:

- The `default` queue.  For jobs that need the standard level of response.

- The `high` priority queue.  For jobs that need to be processed as soon as
  possible.

- The `low` priority queue.  For jobs that may wait in a queue.

.. warning::  This priorities are not actually enforced.

   We simply configured (by default) more processes that consume jobs from the
   `high` priority queue than processes that consume jobs from the `low`
   priority queue.

   Therefore if the application is queuing jobs to the `high` priority queue
   at rate faster than the workers can process them while the are few jobs in
   the `low` priority queue; high priority jobs will actually get a worse
   throughput.

   The programmer is expected to coordinate about the priority of a job.  As
   rule of thumb is to always use the `default` queue first.


Usage
=====

In this example use the ``bin/xoeuf shell`` to test the current features.

First run the server **using the preforking server**.  Celery workers won't be
spawned automatically unless in preforking mode::

  bin/xoeuf --workers=2

You should see some logs about the workers being started::

    INFO ? openerp.service.server: Worker DefaultCeleryWorker (9396) alive
    INFO ? openerp.service.server: Worker HighPriorityCeleryWorker (9397) alive
    INFO ? openerp.service.server: Worker LowPriorityCeleryWorker (9398) alive

If you don't see that something has gone bad or your configuration has
disabled the workers.  If you see that, then you may start to send jobs to the
workers (use the shell).

High level API
--------------

The ``openerp.jobs`` module exposes three functions to request backgrounds
jobs:

- ``Deferred``
- ``HighPriorityDeferred``
- ``LowPriorityDeferred``

They put the background job request in the one of the queues we mentioned
above.


  >>> from openerp.jobs import Deferred
  >>> for i in range(1000):
  ...     res = Deferred('res.users', 'mercurio', 1, 'search', [])


Now you should see your CPUs burning while processing all the 1000 jobs.  You
may watch the whole story using ``flower``::

  bin/celery flower

It will create a nice dashboard to monitor the Celery Workers.


Creating new types of deferreds
-------------------------------

The high level API does not allow to pass any options the celery job (see the
`async_apply` method for calling tasks in celery).  If you need to pass
options, for instance, to delay a job until (ETA or countdown), you may use
one of these instead.

- ``DefaultDeferredType``
- ``HighPriorityDeferredType``
- ``LowPriorityDeferredType``

For instance you may delay the execution of the task by passing a countdown::

  >>> from openerp.jobs import DefaultDeferredType
  >>> for i in range(1000):
  ...     res = DefaultDeferredType(countdown=i + 10)('res.users', 'mercurio',
  ...                                                 1, 'search', [])



Reporting progress
------------------

The UI may be waiting for a job to complete.  The addon ``web_celery``
provides a simple ``WAIT_FOR_JOB`` client action that will show a progress bar
and a message.

You may report progress changes by using the function
``openerp.jobs.report_progress``.  It is documented, so read the
documentation.



Best practices for background jobs writing
==========================================

As demonstrated in the Usage_ section any method from a model can be delegated
to a background job.  However, some rules and best practices should be
honored:

- If the method returns a value that is not serializable in JSON the result
  couldn't be retrieved afterwards (I haven't tested what happens.)

- You MUST NEVER override an existing method to make it a background job.

  Yes, I did this in the `web_celery` addon, but only to be able to test the
  main concept, I ensure to override the method only when ``debug_mode`` is
  on.

  The way to go would be the to make methods specifically designed to work on
  the background and call normal methods from there and change the UI to call
  the new methods.

- You SHOULD make `progress reports <Reporting progress>`_ only from methods
  that are by themselves backgrounds jobs.  Keeping a sane progress report
  over several methods is very difficult.

- Only use the ``openerp.addons.web_celery.WAIT_FOR_JOB`` return value when
  you're absolutely certain the user needs to wait the job to complete.  If
  not sure, make the user happy by making him/her believe you have done what
  he/she requested.

  Fact: When you remove a project from gitlab it says: "Ok, I'm done".  But
  the truth is it hasn't, it will remove the project after 15 minutes.

- You SHOULD NOT rely on testing for `CONTEXT_JOB`.  This is considered an
  implementation detail not part of the API.


..
   Local Variables:
   ispell-dictionary: "en"
   End:
