=============================
 Odoo and Celery Integration
=============================

This document describes both the current state and plans for the implementation
of the integration of Odoo and Celery Task Queue.


Implementation details
======================

The idea is to have a single task definition that simply allows the execution of
any method in a model.

There are three queues defined:

- The `default` queue.  For jobs that need the standard level of response.

- The `high` priority queue.  For jobs that need to be processed as soon as
  possible.

- The `low` priority queue.  For jobs that may wait in a queue.

.. warning::  This priorities are not actually enforced.

   We simply create more processes that consume jobs from the `high` priority
   queue than processes that consume jobs from the `low` priority queue.

   Therefore if the application is queuing jobs to the `high` priority queue at
   rate faster than the workers can process them while the are few jobs in the
   `low` priority queue; high priority jobs will actually get a worse
   throughput.

   The programmer is expected to coordinate about the priority of a job.  As
   rule of thumb is to always use the `default` queue first.


Currently usage
===============

This will use the ``bin/xoeuf shell`` to test the current features.

First run the server **using the preforking server**::

  bin/xoeuf --workers=2

You should see some logs about the workers being started::

    INFO ? openerp.service.server: Worker DefaultCeleryWorker (9396) alive
    INFO ? openerp.service.server: Worker HighPriorityCeleryWorker (9397) alive
    INFO ? openerp.service.server: Worker LowPriorityCeleryWorker (9398) alive

If you don't see that something has gone bad.  If you see that, then you may
start to send jobs to the workers (use the shell)::

  >>> from openerp.celeryapp import Deferred, HighPriorityDeferred, LowPriorityDeferred
  >>> for i in range(1000):
  ...     Deferred('dbname', 1, 'res.users', 'search', args=([], ), kwargs={})


Now you should see your CPUs burning processing all the 1000 jobs.


Implementation notes
====================

We have modified the following modules:

- ``service/server.py``.

  This module implements the ``PreforkServer``.  We changed this server to
  automatically fork the Celery Workers.


Next things to do
=================

1. Integrate the GeventServer to watch for completed/failed tasks.

2. Integrate the `bus` addon to notify about completed/failed tasks.

3. Create UI stuff.



..
   Local Variables:
   ispell-dictionary: "en"
   End:
