#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------
# Copyright (c) Merchise Autrement [~º/~] and Contributors
# All rights reserved.
#
# This is free software; you can do what the LICENCE file allows you to.
#
"""Odoo Celery Application.

Integrates Odoo and Celery, so that jobs can be started from the Odoo HTTP
workers and tasks can use the Odoo ORM.

"""
import os
import contextlib
import threading

from dataclasses import dataclass
from typing import Any, Dict, Iterable, NamedTuple, Optional, Sequence, Tuple, TypeVar

import logging

logger = logging.getLogger(__name__)
del logging

from xotl.tools.context import context as ExecutionContext
from xotl.tools.objects import temp_attributes

from kombu import Exchange, Queue

from celery import Celery as _CeleryApp
from celery import Task as BaseTask


from celery.exceptions import (
    MaxRetriesExceededError,
    SoftTimeLimitExceeded,
    TimeLimitExceeded,
    WorkerLostError,
    Terminated,
)

from functools import total_ordering

from odoo import SUPERUSER_ID
import odoo.tools.config as config
from odoo.tools.func import lazy_property

from odoo.release import version_info
from odoo.api import Environment
from odoo.modules.registry import Registry
from odoo.http import serialize_exception as _serialize_exception

from psycopg2 import OperationalError, errorcodes


# The queues are named using the version info major number, ie:
# odoo-12.default, odoo-12.cdr, etc.  This is to avoid clashes with other
# systems using Celery and the same broker.  I've seen sentry tasks being
# routed to one of workers.

# TODO: Write an auto-migration of task routed to older queue names.
ROUTE_NS = f"odoo-{version_info[0]}"


def queue(name):
    """Return the fully qualified queue `name`.

    All queue names must be obtained from this function.  Passing a 'bare'
    queue name in any of the methods can be done, but it's not adviced.

    This function is idempotent::

    >>> queue(queue('x')) == queue('x')
    True

    """
    if not name.startswith(ROUTE_NS + "."):
        return "{}.{}".format(ROUTE_NS, name)
    else:
        return name


# The default pre-created queue.  Although we will allows several queues, we
# strongly advice against creating any-more than the ones defined below.  If
# unsure, just use the default queue.
#
# WARNING: You must run the workers for the non-default queues yourself.
DEFAULT_QUEUE_NAME = queue("default")
del version_info


class DeferredType(object):
    __name__ = "DeferredType"  # needed by deprecation below

    def __init__(self, **options):
        """Create a function for a deferred job in the default queue.

        :keyword allow_nested: If True, jobs created with the returning function
                               will be allowed to run nested (within the contex/t
                               of another background job).

                               The default is False.

        :keyword return_signature: If True we only return the signature of the
                 job instead of actually scheduling the job.  This allows to
                 create chains and groups of jobs.

                 Notice we always create immutable signatures.

        :keyword queue: The name of the queue.

        :keyword allow_tests: If True we will actually issue Celery jobs while
                 running the test suite.  Only do this if you can provide
                 fully integrated test environment and your tests monitor the
                 bus.  If False (the default), calling a Deferred during
                 tests, runs the method directly without issuing a Celery job.

        """
        self.__return_signature = options.pop("return_signature", False)
        self.__disallow_nested = not options.pop("allow_nested", False)
        self.__disallow_tests = not options.pop("allow_tests", False)
        options.setdefault("queue", DEFAULT_QUEUE_NAME)
        self.__options = options

    @property
    def disallow_nested(self):
        return self.__disallow_nested

    @property
    def disallow_tests(self):
        return self.__disallow_tests

    @property
    def return_signature(self):
        return self.__return_signature

    @property
    def options(self):
        return dict(self.__options)

    def __call__(self, *args, **kwargs):
        """Request to run a method in a celery worker.

        The signature is like::

           Deferred(self.search, [], limit=1)

        The first argument must be a *bound method of a record set*.  The rest
        of the arguments must match the signature of such method.

        :returns: An AsyncResult that represents the job.

        .. warning:: Nested calls don't issue sub-tasks.

           When running inside a background job, calling this function
           **won't** create another background job, but inline the function
           call.

        .. seealso: `DefaultDeferredType`:func:

        """
        signature, env = _extract_signature(args, kwargs)
        if self.disallow_nested and CELERY_JOB in ExecutionContext:
            logger.warn("Nested background call detected for model", extra=dict(args_=signature))
            return task(*signature)
        elif self.disallow_tests and _running_tests(env):
            logger.info("Running the deferred job inline in tests", extra=dict(args_=signature))
            return task(*signature)
        else:
            signature = task.signature(signature, immutable=True, **self.options)
            if self.return_signature:
                return signature
            else:
                return signature.delay()


Deferred = DeferredType()
T = TypeVar("T")


def terminate_task(task_id, *args, **kwargs):
    """Terminates a task which may be in the queue or running.

    Since `task_id` could be publicly sent by HTTP, you must be sure to call
    this method passing the original arguments used to the issue the task
    (just be sure not share those args).

    For example, if you created a job with:

       >>> result = Deferred(recordset.some_method, arg1, arg2)

    You SHOULD call `~terminate_task`:func: like this:

       >>> terminate_task(result.id, recordset.some_method, arg1, arg2)

    If the arguments provided don't match the

    If possible, we send a report to notify the cancellation of the task.

    """
    task_record = TaskRecord.find(task_id)
    if task_record.matches_signature(args, kwargs):
        task_record.cancel()
    else:
        logger.warning(
            "Ignoring request to cancel job %s, because the provided arguments don't match", task_id
        )


def terminate_task_with_env(task_id, env):
    """Terminate a tasks if it matches the user in the environment.

    This is weaker than requiring a whole match of the arguments provided to
    create the background job but at least requires the user to be the same.

    """
    task_record = TaskRecord.find(task_id)
    if task_record.matches_env(env):
        task_record.cancel()


def iter_and_report(
    iterator: Iterable[T], start=0, valuemax=None, report_rate=1, messagetmpl="Progress: {progress}"
) -> Iterable[T]:
    """Iterate over 'iterator' while reporting progress.

    In the context of a background (celery) job you may wish to iterate over a
    sequence of objects and, at the same time, report progress.

    Return a generator that consumes and produces the same values as
    `iterator`.

    Report progress is disabled if `valuemax` is not a positive integral
    value.

    `report_rate` regulates the rate at which reports are issued: Reports are
    issued only when then progress is an integral multiple of `rate` (or when
    it's zero).

    When the `iterator` is fully consumed, despite the value of `report_rate`,
    we issue a final report making progress=valuemax (i.e. 100%).

    The `messagetmpl` is a string template to format the message to be
    reported.  The allowed keywords in the template are 'progress' and
    'valuemax' (the provided argument).

    .. rubric:: Co-routine behavior

    At each step if you send back a value, it should be a string with a new
    message template.

    """
    if not all(isinstance(x, int) for x in (valuemax, report_rate, start)):
        raise TypeError("valuemax, start and step must be integers")
    if not isinstance(messagetmpl, str):
        raise TypeError("messagetmpl must a string")
    for progress, x in enumerate(iterator, start):
        if valuemax and progress % report_rate == 0:
            report_progress(
                message=messagetmpl.format(progress=progress, valuemax=valuemax),
                progress=progress,
                valuemax=valuemax,
                valuemin=start,
            )
        msg = yield x
        if msg and isinstance(msg, str):
            messagetmpl = msg
    if valuemax and valuemax % report_rate != 0:
        report_progress(progress=progress)


def iter_at_savepoint(self, items: Iterable[T]) -> Iterable[T]:
    """Iterate over `items` yielding elements at a SAVEPOINT boundary.

    Enclose each iteration within a SAVEPOINT so that callers may choose to
    stop at each *complete* step.

    This is specially important if you're going to consume this generator with
    `until_timeout` or any other `until` variant.

    `self` must an object with an attribute `env` of type Environment.

    """
    processing = True
    while processing:
        with self.env.cr.savepoint():
            # Notice that we yield outside.  This is so the SAVEPOINT does
            # not leak to the outside of this method.  The caller may be
            # responsible to either commit or rollback but only on
            # discrete points we need to satisfy.
            try:
                item = next(items)
            except StopIteration:
                processing = False
            if processing:
                yield item


def until_timeout(iterator: Iterable[T], on_timeout=None) -> Iterable[T]:
    """Iterate and yield from `iterator` while the job has time to work.

    Celery can be configured to raise a SoftTimeLimitExceeded exception when a
    soft time limit is reached.

    This function integrates such signal into a background job that does its
    work by yielding each *partially complete* unit of progress.

    It's expected that it will be more likely for StopTimeLimitExceeded to be
    raised while `iterator` is performing its work.  In other word, you should
    enclose as much work as possible within a single call to `until_timeout`.

    :param on_timeout: A callable that will only be called if we exit the
                       iteration because of a SoftTimeLimitExceeded error.

    Although you may call `until_timeout`:func: inside another call to
    `until_timeout`:func: we strongly advice against it.

    In a iterator pattern like::

       until_timeout(... until_timeout(...) ...)

    .. note::The ellipsis above indicate that the nesting could an indirect
       consequence of several modules of your system.

    both calls could have been provided a `on_timeout` argument.  In *linear*
    patterns the behaviour is well established: only the instances enclosing
    the point where the exceptions happens will be called its timeout.

    However in tree-like structures an automatic 'linearisation' of the tree
    nodes is performed and as such, a timeout in one branch of the tree may be
    signaled to the other branch.

    Notice that these signals are not exceptions.  Only the first
    SoftTimeLimitExceeded is an exception thrown by celery in the middle of
    running code.

    """
    from xotl.tools.context import context

    # Allow linear nested calls`: ``until_timeout(... until_timeout(...))``.
    #
    # Each call to until_timeout sets an event counter (which may be `wrapped
    # counter` of on_timeout).  We look in the execution context for a
    # 'parent' counter and chain with it.  The iterator will be consumed in a
    # context where this chain is parent counter.
    signal_timeout = _WrappedCounter(on_timeout)
    parent = context[_UNTIL_TIMEOUT_CONTEXT].get("counter")
    timed_out = parent | signal_timeout
    try:
        with context(_UNTIL_TIMEOUT_CONTEXT, counter=timed_out):
            i = iter(iterator)
            try:
                while not timed_out:
                    yield next(i)
            except StopIteration:
                # Python 3.7+ (PEP 479) does not bubbles the StopIteration,
                # but converts it to RuntimeError.  Using `return` restores
                # the <3.7 behavior.
                return
    except SoftTimeLimitExceeded:
        # At this point the local value of `timed_out` is `parent | me`, I
        # must signal both my parent and myself.
        timed_out()
    finally:
        close = getattr(iterator, "close", None)
        if close:
            close()


_UNTIL_TIMEOUT_CONTEXT = object()


# TODO (med, manu):  Should we have this in xotl.tools?
@total_ordering
class EventCounter(object):
    """A simple counter of an event.

    Instances are callables that you can call to count the times an event
    happens.

    Example::

       timed_out = EventCounter()
       until_timeout(iterable, on_timeout=timed_out)

       if timed_out:
          # the jobs has timed out.

    This event counter is **not** thread-safe.

    Instances support casting to `int` (and long in Python 2) and it's
    comparable with numbers and other counters.

       >>> e = EventCounter()
       >>> int(e)
       0

       >>> bool(e)
       False

       >>> e()

       >>> bool(e)
       True

       >>> int(e)
       1

       >>> 1 <= e < 2
       True

       >>> e > e
       False

    Two event counters can be chained together:

       >>> e1 = EventCounter()
       >>> e2 = EventCounter()
       >>> e = e1 | e2
       >>> e()

       >>> bool(e1 and e2)
       True

    However signaling one event would not reflect to the other:

       >>> e1 = EventCounter()
       >>> e2 = EventCounter()
       >>> e3 = EventCounter()
       >>> e = e1 | e2 | e3

       >>> e2()

       >>> bool(e and e2 and not e1 and not e3)

    Chaining with None is a no-op:

       >>> e1 | None is None | e1 is e1
       True

    """

    __slots__ = ("seen", "name")

    def __init__(self, name=None):
        self.name = name
        self.seen = 0

    def __bool__(self):
        return self.seen > 0

    __nonzero__ = __bool__

    def __call__(self):
        logger.debug("Signaling %r" % self)
        self.seen += 1

    def __lt__(self, o):
        return self.seen < int(o)

    def __eq__(self, o):
        return self.seen == int(o)

    def __trunc__(self):
        return self.seen

    def __or__(self, o):
        if o is None:
            return self
        else:
            return EventCounterChain(self, o)

    __ror__ = __or__

    def __repr__(self):
        name = self.name or super(EventCounter, self).__repr__()[1:-1]
        if self:
            return f'<**{name}**>'
        else:
            return f'<{name}>'


class _WrappedCounter(EventCounter):
    """An event counter that wraps another callable.

    Example:

       >>> def evented():
       ...     print('The event happened')

       >>> e = _WrappedCounter(evented)
       >>> e()
       The event happened

    If the first argument is already an event counter return the same event
    counter unchanged:

        >>> e = EventCounter()
        >>> _WrappedCounter(e) is e
        True

    If provided argument is None, creates an EventCounter instead:

        >>> type(_WrappedCounter(None)) is EventCounter
        True

    """

    __slots__ = ("_target",)

    def __new__(cls, what, name=None):
        if isinstance(what, EventCounter):
            return what
        elif what is None:
            return EventCounter(name=name)
        else:
            return super(_WrappedCounter, cls).__new__(cls, what, name=name)

    def __init__(self, what, name=None):
        super(_WrappedCounter, self).__init__(name=name)
        self._target = what

    def __call__(self):
        super(_WrappedCounter, self).__call__()
        self._target()

    def __repr__(self):
        return "_WrappedCounter(%r, name=%r)" % (self._target, self.name)


class EventCounterChain(object):
    __slots__ = ("events",)

    def __init__(self, e1, e2):
        self.events = e1, e2

    def __call__(self):
        for e in self.events:
            e()

    def __bool__(self):
        return any(self.events)

    __nonzero__ = __bool__

    def __or__(self, o):
        if o is None:
            return self
        else:
            return type(self)(self, o)

    __ror__ = __or__

    def __repr__(self):
        return "(%s)" % " | ".join(repr(e) for e in self.events)


def report_progress(message=None, progress=None, valuemin=None, valuemax=None, status=None):
    """Send a progress notification to whomever is polling the current job.

    :param message: The message to send to those waiting for the message.

    :param progress: A number in the range given by `valuemin` and `valuemax`
           indicating how much has been done.

           If you can't produce a good estimate is best to send "stages" in
           the message.

    :param valuemin: The minimum value `progress` can take.

    :param valuemax: The maximum value `progress` can take.

    The `valuemin` and `valuemax` arguments must be reported together.  And
    once settle they cannot be changed.

    :param status: The reported status. This should be one of the strings
       'success', 'failure' or 'pending'.

       .. warning:: This argument should not be used but for internal (job
                    framework module) purposes.

    """
    _context = ExecutionContext[CELERY_JOB]
    job_uuid = _context.get("job_uuid")
    if job_uuid:
        if valuemin is None or valuemax is None:
            valuemin = valuemax = None
        elif valuemin >= valuemax:
            valuemin = valuemax = None
        _send(
            get_progress_channel(job_uuid),
            dict(
                status=status,
                message=message,
                progress=progress,
                valuemin=valuemin,
                valuemax=valuemax,
            ),
        )


class Configuration(object):
    broker_url = config.get(
        "celery.broker", os.environ.get("odoo_celery_broker", "redis://localhost/9")
    )

    # We don't use the backend to **store** results, but send results via
    # another message.
    #
    # However to check the job status the backend is used
    # and to be able to detect if a job was killed or finished we need to
    # configure the backend.
    #
    # This forces us to periodically clean the backend.  Fortunately Celery
    # automatically schedules the 'celery.backend_cleanup' to be run every day
    # at 4am.
    #
    # This change can allow to strengthen the usability for very short tasks.
    # This is rare in our case because even setting up the Odoo registry
    # in our main `task`:func: takes longer than the expected round-trip from
    # the browser to the server.
    result_backend = config.get("celery.backend", os.environ.get("odoo_celery_backend", broker_url))

    task_ignore_result = True

    task_default_queue = DEFAULT_QUEUE_NAME
    task_default_exchange_type = "direct"
    task_default_routing_key = DEFAULT_QUEUE_NAME

    task_queues = [
        Queue(
            task_default_queue, Exchange(task_default_queue), routing_key=task_default_routing_key
        ),
        Queue(
            queue("notifications"),
            Exchange(queue("notifications")),
            routing_key=queue(queue("notifications")),
        ),
    ]

    worker_send_task_events = True

    # Maximum number of tasks a pool worker process can execute before it’s
    # replaced with a new one. Default is 2000 and the min is 10.
    worker_max_tasks_per_child = max(int(config.get("celery.max_tasks_per_child", 2000)), 10)

    # Maximum amount of resident memory, in kilobytes, that may be consumed by
    # a worker before it will be replaced by a new worker. If a single task
    # causes a worker to exceed this limit, the task will be completed, and
    # the worker will be replaced afterwards.
    _worker_max_memory_per_child = config.get("celery.worker_max_memory_per_child")
    if _worker_max_memory_per_child:
        worker_max_memory_per_child = _worker_max_memory_per_child
    del _worker_max_memory_per_child

    # If enabled, a task-sent event will be sent for every task so tasks can be tracked before
    # they’re consumed by a worker.
    task_send_sent_event = True

    task_create_missing_queues = config.get("celery.create_missing_queues", True)

    task_time_limit = config.get(
        "celery.task_time_limit", os.environ.get("odoo_celery_task_time_limit", 600)  # 10 minutes
    )
    _softtime = config.get(
        "celery.task_soft_time_limit",
        os.environ.get(
            "odoo_celery_task_soft_time_limit", 595  # 9min 55 seconds (5 seconds to finish)
        ),
    )
    if _softtime is not None:
        task_soft_time_limit = int(_softtime)
    del _softtime

    worker_enable_remote_control = True

    enable_utc = True
    task_always_eager = False

    task_acks_late = config.get("celery.acks_late", True)

    _CELERYD_PREFETCH_MULTIPLIER = config.get("celery.prefetch_multiplier", 0)
    if not _CELERYD_PREFETCH_MULTIPLIER:
        # Avoid infinite prefetching
        pass
    else:
        worker_prefetch_multiplier = int(_CELERYD_PREFETCH_MULTIPLIER)
    del _CELERYD_PREFETCH_MULTIPLIER

    _CELERYBEAT_SCHEDULE_FILENAME = config.get("celery.beat_schedule_filename", None)
    if _CELERYBEAT_SCHEDULE_FILENAME is not None:
        beat_schedule_filename = _CELERYBEAT_SCHEDULE_FILENAME
    del _CELERYBEAT_SCHEDULE_FILENAME


app = _CeleryApp(__name__)
app.config_from_object(Configuration)


# A context for jobs.  All jobs will be executed in this context.
class CELERY_JOB(ExecutionContext):
    def __new__(cls, **options):
        context_identifier = cls
        return super(CELERY_JOB, cls).__new__(cls, context_identifier, **options)

    def __init__(self, **options):
        super(CELERY_JOB, self).__init__(**options)
        self.job = options["job"]
        self.env = options["env"]

    @lazy_property
    def request(self):
        class req(object):
            # A request-like object.
            #
            # ``bool(req())`` is always False.
            #
            # ``req().anything`` is another ``req()``, so you can do
            # ``req().x.y.z``.  This fact, combined with the previous, means
            # that ``bool(req().anything.not.shown.below)`` is always False.
            #
            # This is a technical hack to make parts of Odoo that require a
            # HTTP request in the `odoo.http.request`:object: to be available,
            # and many attributes are also freely traversed like
            # ``request.httprequest.is_spdy``...
            #
            env = self.env
            uid = env.uid
            context = env.context
            lang = context.get("lang", "en_US")
            cr = env.cr
            _cr = env.cr
            db = env.cr.dbname

            def __nonzero__(self):
                return False

            __bool__ = __nonzero__

            def __getattr__(self, attr):
                return req()

            @contextlib.contextmanager
            def registry_cr(self):
                import warnings

                warnings.warn(
                    "please use request.registry and request.cr directly", DeprecationWarning
                )
                yield (self.registry, self.cr)

        return req()

    def __enter__(self):
        from odoo.http import _request_stack

        _request_stack.push(self.request)
        return super(CELERY_JOB, self).__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        from odoo.http import _request_stack

        _request_stack.pop()
        return super(CELERY_JOB, self).__exit__(exc_type, exc_val, exc_tb)


PG_CONCURRENCY_ERRORS_TO_RETRY = (
    errorcodes.LOCK_NOT_AVAILABLE,
    errorcodes.SERIALIZATION_FAILURE,
    errorcodes.DEADLOCK_DETECTED,
)


class TaskSignature(NamedTuple):
    """The signature of the task."""

    modelname: str
    ids: Sequence[int]
    methodname: str
    dbname: str
    uid: int
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]

    @classmethod
    def from_deferred_signature(cls, args, kwargs):
        from xotl.tools.symbols import Unset
        from odoo.models import BaseModel

        method = args[0]
        self = getattr(method, "__self__", Unset)
        env = getattr(self, "env", Unset)
        if isinstance(self, BaseModel) and isinstance(env, Environment):
            cr, uid, context = env.args
            kwargs["context"] = dict(context)
            model = self
            methodname = method.__name__
            ids = self.ids
            args = args[1:]
            return cls(model._name, ids, methodname, cr.dbname, uid, args, kwargs)
        raise TypeError("Invalid signature for Deferred; args: %r; kwargs: %r" % (args, kwargs))

    def matches_completely(self, args, kwargs):
        """True if this signature is a match of the arguments to Deferred.

        If the arguments are resolved to the SUPERUSER and all other arguments
        match, we still return True.

        """
        signature = self.from_deferred_signature(args, kwargs)
        return signature == self or signature == self.sudo()

    def matches_env(self, env: Environment):
        """True if this signature is for the same DB and user.

        If the signature matches the env's DB and the env's user is the
        SUPERUSER, return True.

        """
        return self.dbname == env.cr.dbname and (env.uid == SUPERUSER_ID or env.uid == self.uid)

    def sudo(self):
        "The same task signature for the SUPERUSER."
        return type(self)(
            self.modelname,
            self.ids,
            self.methodname,
            self.dbname,
            SUPERUSER_ID,
            self.args,
            self.kwargs,
        )


TASK_SIGNATURE_SIZE = len(TaskSignature.__annotations__)


@dataclass
class TaskRecord:
    """The request record.

    Provides a simple interface to govern the task.

    :id: The task UID.

    :args: A tuple with the arguments to the task.  In our case this will be
          ``(modelname, [id, ...], methodname, dbname, uid, method_args,
          method_kwargs_and_context)``.

    """

    id: str
    args: Optional[TaskSignature]
    found: bool

    @classmethod
    def find(cls, task_id) -> "TaskRecord":
        """Find the record from celery application control API.

        If the task is not found we simply return record without args.

        """

        def _find():
            matches = app.control.inspect().query_task(task_id) or {}
            for worker, data in matches.items():
                _status, record = data.get(task_id, (None, None))
                if record is not None:
                    yield record

        data = next(_find(), None)
        if data:
            args = data.get("args", ())
            if len(args) == TASK_SIGNATURE_SIZE:
                return cls(task_id, TaskSignature(*args), True)
            else:
                return cls(task_id, None, True)
        else:
            return cls(task_id, None, False)

    def matches_signature(self, args, kwargs):
        """Return True if the task matches the signature to Deferred.

        If the task record was not *found* by `find`:meth:, return True.

        """
        return not self.found or not self.args or self.args.matches_completely(args, kwargs)

    def matches_env(self, env: Environment):
        """Return true if the task matches the DB and user of the environment.

        If the task record was not *found* by `find`:meth:, return True.

        """
        return not self.found or not self.args or self.args.matches_env(env)

    def cancel(self):
        """Broadcast a cancel request for the task.

        Optimistically report the cancellation of the task by the bus.

        """
        app.control.terminate(self.id)
        self.report_cancelled()

    def report_cancelled(self):
        """Report the cancellation of the task by the bus"""
        if self.args is not None:
            _report_cancelled.delay(self, self.args.dbname, self.args.uid, self.id)


def _extract_signature(args, kwargs):
    """Extract the task' signature and environment.

    """
    from xotl.tools.symbols import Unset

    method = args[0]
    self = getattr(method, "__self__", Unset)
    env = getattr(self, "env", Unset)
    return TaskSignature.from_deferred_signature(args, kwargs), env


Unset = object()


class Task(BaseTask):
    # See the notes below on the 'Hacking' section.
    # See also: https://github.com/celery/celery/pull/3977
    Request = "odoo.jobs:Request"


@app.task(base=Task, bind=True, max_retries=5, default_retry_delay=0.3)
def task(self, model, ids, methodname, dbname, uid, args, kwargs, job_uuid=Unset):
    """The actual task running all our celery jobs.

    Since a model method may be altered in several addons, we funnel all calls
    to execute a method in a single Celery task.

    The `job_uuid` argument serves to relate retries with the first request.
    Since retries have a different request ID than that of the 'actual task'
    the user is probably monitoring, we need a unique UUID that relates
    retries.

    `job_uuid` is Unset when Deferred executes the task.  `task`:func: is not
    part of the API of this module; it's an implementation detail you should
    only know if you're messing with `task` directly.

    Retries are scheduled with a minimum delay of 300ms.

    """
    from odoo.models import BaseModel

    if job_uuid is Unset:
        from uuid import uuid1

        job_uuid = self.request.id if self.request.id else str(uuid1())
    context = kwargs.pop("context", None)
    try:
        logger.info(
            "Start job (%s): db=%s, uid=%s, model=%s, ids=%r, method=%s",
            job_uuid,
            dbname,
            uid,
            model,
            ids,
            methodname,
        )
        with MaybeRecords(dbname, uid, model, ids, context=context) as r:
            method = getattr(r, methodname, None)
            if method:
                if not ids and _require_ids(method):
                    ids, args = args[0], args[1:]
                    method = getattr(r.browse(ids), methodname)
                options = dict(job=self, env=r.env, job_uuid=job_uuid)
                with CELERY_JOB(**options):
                    res = method(*args, **kwargs)
                if isinstance(res, BaseModel):
                    res = res.ids  # downgrade to ids
                _report_success.delay(dbname, uid, job_uuid, result=res)
            else:
                raise TypeError("Invalid method name %r for model %r" % (methodname, model))
    except SoftTimeLimitExceeded as e:
        # Well, SoftTimeLimitExceeded may occur anywhere in the code.  It's
        # really a signal.  When integrating with `sentrylog`, I think the
        # best option is collect this events per job: ``(model, methodname)``.
        e._sentry_fingerprint = [type(e), model, methodname]
        _report_current_failure(dbname, uid, job_uuid, e)
        raise e
    except OperationalError as error:
        if error.pgcode not in PG_CONCURRENCY_ERRORS_TO_RETRY:
            _report_current_failure(dbname, uid, job_uuid, error)
            raise
        else:
            arguments = (model, ids, methodname, dbname, uid, args, kwargs)
            keywords = dict(job_uuid=job_uuid)
            logger.info(
                "Maybe retrying task %s",
                job_uuid,
                extra=dict(arguments=arguments, keywords=keywords),
            )
            try:
                raise self.retry(args=arguments, kwargs=keywords)
            except MaxRetriesExceededError:
                _report_current_failure(dbname, uid, job_uuid, error)
                raise error
    except Exception as error:
        _report_current_failure(dbname, uid, job_uuid, error)
        raise


@contextlib.contextmanager
def MaybeRecords(dbname, uid, model, ids=None, context=None):
    __traceback_hide__ = True  # noqa: hide from Celery Tracebacks
    with OdooEnvironment(dbname, uid, context=context) as env:
        records = env[model].browse(ids)
        yield records


@contextlib.contextmanager
def OdooEnvironment(dbname, uid, context=None):
    __traceback_hide__ = True  # noqa: hide from Celery Tracebacks
    with Environment.manage():
        registry = Registry(dbname).check_signaling()
        try:
            # Several pieces of OpenERP code expect this attributes to be set in
            # the current thread.
            thread = threading.currentThread()
            with temp_attributes(thread, dict(uid=uid, dbname=dbname)), registry.cursor() as cr:
                env = Environment(cr, uid, context or {})
                yield env
        except:  # noqa
            registry.reset_changes()
            raise
        else:
            registry = Registry(dbname)  # the registry might have been replaced
            registry.signal_changes()


def _require_ids(method):
    return getattr(method, "_api", None) in (
        "multi",
        "cr_uid_id",
        "cr_uid_id_context",
        "cr_uid_ids",
        "cr_uid_ids_context",
    )


@app.task(bind=True, max_retries=5, default_retry_delay=0.1, queue=queue("notifications"))
def _report_success(self, dbname, uid, job_uuid, result=None):
    try:
        with OdooEnvironment(dbname, uid) as env:
            _send(get_progress_channel(job_uuid), dict(status="success", result=result), env=env)
    except Exception:
        logger.exception("Exception while reporting success")
        try:
            raise self.retry(args=(dbname, uid, job_uuid), kwargs=dict(result=result))
        except MaxRetriesExceededError:
            logger.exception("Max retries exceeded with reporting success")


@app.task(bind=True, max_retries=5, default_retry_delay=0.1, queue=queue("notifications"))
def _report_cancelled(self, dbname, uid, job_uuid):
    try:
        with OdooEnvironment(dbname, uid) as env:
            _send(get_progress_channel(job_uuid), dict(status="cancelled", result=None), env=env)
    except Exception:
        logger.exception("Exception while reporting success")
        try:
            raise self.retry(args=(dbname, uid, job_uuid), kwargs={})
        except MaxRetriesExceededError:
            logger.exception("Max retries exceeded with reporting success")


@app.task(bind=True, max_retries=5, default_retry_delay=0.1, queue=queue("notifications"))
def _report_failure(self, dbname, uid, job_uuid, tb=None, message=""):
    try:
        with OdooEnvironment(dbname, uid) as env:
            _send(
                get_progress_channel(job_uuid),
                dict(status="failure", traceback=tb, message=message),
                env=env,
            )
    except Exception:
        logger.exception("Exception while reporting failure")
        try:
            raise self.retry(args=(dbname, uid, job_uuid, tb), kwargs={"message": message})
        except MaxRetriesExceededError:
            logger.exception("Max retries exceeded with reporting success")


def _report_current_failure(dbname, uid, job_uuid, error, subtask=True):
    data = _serialize_exception(error)
    if subtask:
        _report_failure.delay(dbname, uid, job_uuid, message=data)
    else:
        _report_failure(dbname, uid, job_uuid, message=data)
    logger.exception("Unhandled exception in task")


def get_progress_channel(job_uuid):
    """Get the name of the Odoo bus channel for reporting progress.

    :param job_uuid: The UUID of the job.

    """
    return "celeryapp:%s:progress" % job_uuid


def get_status_channel(job_uuid):
    """Get the name of the Odoo bus channel for reporting status.

    :param job_uuid: The UUID of the job.

    """
    return "celeryapp:%s:status" % job_uuid


def _send(channel, message, env=None):
    if env is None:
        _context = ExecutionContext[CELERY_JOB]
        env = _context["env"]
    cr, uid, context = env.args
    with Registry(cr.dbname).cursor() as newcr:
        newenv = Environment(newcr, uid, context=context)
        # The bus waits until the COMMIT to actually NOTIFY listening clients,
        # this means that all progress reports, would not be visible to clients
        # until the whole transaction commits:
        #
        # We can't commit the proper task's cr, because errors may happen
        # after a report.
        #
        # Solution a dedicated cursors for bus messages.
        newenv["bus.bus"].sendone(channel, message)


# Hacking.  The hard timeout signal is not easily captured.  The
# celery.worker.request.Request is the one that handles the hard timeout.
# However, it is not easily customized.
#
# We can totally replace the Strategy class of our task class.  But they are
# not easy to override (they say that).
#
# Our approach:  Monkey-patch the create_request_cls function.
from celery.worker.request import Request as BaseRequest


class Request(BaseRequest):
    def on_failure(self, exc_info, send_failed_event=True, return_ok=False):
        super(Request, self).on_failure(
            exc_info, send_failed_event=send_failed_event, return_ok=return_ok
        )
        exc = exc_info.exception
        if isinstance(exc, (WorkerLostError, Terminated)):
            _report_failure_for_request(self, exc)

    def on_timeout(self, soft, timeout):
        """Handler called if the task times out."""
        super(Request, self).on_timeout(soft, timeout)
        if not soft:
            _report_failure_for_request(self, TimeLimitExceeded(timeout))


def _report_failure_for_request(self, exc, delay=None):
    try:
        if self.task.name == task.name:
            data = _serialize_exception(exc)
            task_args, task_kwargs = self.message.payload[:2]
            model, ids, methodname, dbname, uid, pos_args, kw_args = task_args
            job_uuid = task_kwargs.get("job_uuid", self.id)
            if job_uuid != self.id:
                msg = ("Job failure detected. job: %s with id %s",)
                msg_args = job_uuid, self.id
            else:
                msg = "Job failure detected. job: %s"
                msg_args = (job_uuid,)
            logger.error(
                msg,
                *msg_args,
                extra=dict(
                    model=model,
                    ids=ids,
                    methodname=methodname,
                    dbname=dbname,
                    uid=uid,
                    pos_args=pos_args,
                    kw_args=kw_args,
                    payload=self.message.payload,
                ),
            )
            _report_failure.apply_async(
                args=(dbname, uid, job_uuid), kwargs=dict(message=data), countdown=delay
            )
    except Exception:  # Yes! I know what I'm doing.
        pass


if not getattr(BaseTask, "Request", None):
    # So this is a celery that has not accepted our patch
    # (https://github.com/celery/celery/pull/3977).  Let's proceed to
    # monkey-patch the Request.
    from celery.worker import request

    _super_create_request_cls = request.create_request_cls

    def create_request_cls(
        base,
        task,
        pool,
        hostname,
        eventer,
        ref=request.ref,
        revoked_tasks=request.revoked_tasks,
        task_ready=request.task_ready,
        trace=request.trace_task_ret,
    ):

        if base is BaseRequest:
            Base = Request
        else:

            class Base(base, Request):
                pass

        class PatchedRequest(Base):
            pass

        return _super_create_request_cls(
            PatchedRequest,
            task,
            pool,
            hostname,
            eventer,
            ref=ref,
            revoked_tasks=revoked_tasks,
            task_ready=task_ready,
            trace=trace,
        )

    request.create_request_cls = create_request_cls


def _running_tests(env):
    return getattr(threading.currentThread(), "testing", False) or env.registry.in_test_mode()
