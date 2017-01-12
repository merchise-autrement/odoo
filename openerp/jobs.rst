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

If you don't see that something has gone bad or your configuration has
disabled the workers.  If you see that, then you may start to send jobs to the
workers (use the shell).


High level API
--------------

The ``openerp.jobs`` module exposes three functions to request backgrounds
jobs:

- ``Deferred``

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

The high level API does not allow to pass any options to the celery job (see
the `apply_async` method for calling tasks in celery).  If you need to pass
options, for instance, to delay a job for a given amount of time (ETA or
countdown), you may use one of these instead.

- ``DeferredType``

The signature for all of those functions is the same:

.. function:: DeferredType(**options)

   Return a function to create background jobs.  The returned function has the
   signature explained in the `Deferred`:func: function documentation.

   The `options` keyword arguments are passed to the `!apply_async`:meth:
   method the celery task class.  Any valid argument but `queue` and `args`
   can be used.  The `queue` is fixed by the type of deferred and `args` are
   properly constructed by the call to the resulting function.

   In addition you may also pass the following options which are specific of
   this API and passed to the Celery task:

   :keyword allow_nested: Whether to allow 'nested' background jobs.

      By default (``allow_nested=False``) the returned function will create a
      new background job only if not called within the context of another
      background job.

      If this argument is True, the returned function will always create a new
      background job despite the calling context.

   :type allow_nested: bool


.. function:: Deferred(model, cr, uid, method, *args, **kwargs):

   Run a method of a given model in the background.

   :param model: The name of model, a recordset (an instance of Model) or a
		 subclass of Model.

   :param cr: The cursor.  You may pass a string with the name of the
              database.

   :param uid: The user id for the background job.

   :param method: The name of the method to run as a background job.

   The rest of the arguments are the arguments to the method.


Example: Delay the execution of the task by passing a countdown::

  >>> from openerp.jobs import DeferredType
  >>> for i in range(1000):
  ...     res = DeferredType(countdown=i + 10)('res.users', 'mercurio',
  ...                                          1, 'search', [])



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
