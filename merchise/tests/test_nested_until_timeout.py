#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------
# test_nested_until_timeout
# ---------------------------------------------------------------------
# Copyright (c) 2017 Merchise Autrement [~º/~] and Contributors
# All rights reserved.
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.
#
# Created on 2017-04-20


from __future__ import (division as _py3_division,
                        print_function as _py3_print,
                        absolute_import as _py3_abs_import)


import pytest
import contextlib
from xoutil.objects import extract_attrs
from xoutil.future.collections import opendict

try:
    from odoo.jobs import (
        SoftTimeLimitExceeded,
        EventCounter,
        until_timeout,
        _UNTIL_TIMEOUT_CONTEXT,  # not a public API
    )
except ImportError:
    from openerp.jobs import (
        SoftTimeLimitExceeded,
        EventCounter,
        until_timeout,
        _UNTIL_TIMEOUT_CONTEXT,  # not a public API
    )


def job(iterator, timeout=None):
    for x in iterator:
        yield x
        if timeout and x > timeout:
            raise SoftTimeLimitExceeded


def test_inner_stops():
    producer = job(range(1000), 100)
    e1 = EventCounter()
    i1 = until_timeout(producer, on_timeout=e1)
    middleman = job(i1)
    e2 = EventCounter()
    external = until_timeout(middleman, on_timeout=e2)

    for _ in external:
        pass

    assert bool(e1 and e2) and e1.seen == 1 and e2.seen == 1


def test_outer_stops():
    producer = job(range(1000))
    e1 = EventCounter()
    i1 = until_timeout(producer, on_timeout=e1)
    middleman = job(i1, 10)
    e2 = EventCounter()
    external = until_timeout(middleman, on_timeout=e2)

    for _ in external:
        pass

    assert bool(not e1 and e2)


def test_normal_termination():
    producer = job(range(1000))
    e1 = EventCounter()
    i1 = until_timeout(producer, on_timeout=e1)
    middleman = job(i1)
    e2 = EventCounter()
    external = until_timeout(middleman, on_timeout=e2)

    for _ in external:
        pass

    assert bool(not e1 and not e2)


class Producer(object):
    def __init__(self, name=None):
        self.a = 0
        self.name = name
        self.closed = False

    def __repr__(self):
        return 'Producer(%r)' % self.name

    def __iter__(self):
        try:
            while True:
                yield self.a
                self.a += 1
                assert self.a < 10, 'Test gone wild'
        except GeneratorExit:
            self.closed = True


def test_iterator_will_be_closed():
    producer = Producer('producer')
    g = until_timeout(producer)
    next(g)  # Up to the first yield
    with pytest.raises(StopIteration):
        g.throw(SoftTimeLimitExceeded)

    assert producer.closed


# Sadly the, itertools.izip does not close the underlying iterators.
def izip(*iters):
    try:
        while True:
            # StopIteration will happen automatically but we can't use a
            # comprehesion here or it will mask it.
            res = []
            for i in iters:
                res.append(next(i))
            yield tuple(res)
    finally:
        for i in iters:
            close = getattr(i, 'close', None)
            if close:
                close()


@contextlib.contextmanager
def complex_tree(mirror=False):
    # A tree of iterators:
    #
    #     producer1     producer2          producer3
    #        |              |                |
    #   until_timeout       |                |
    #        |          until_timeout        |
    #        |              |            until_timeout
    #        |              |                |
    #        +--------------+                |
    #               |                        |
    #             izip                       |
    #         until_timeout (join12)         |
    #               |                        |
    #               +------------------------+
    #                            |
    #                          izip
    #                     until_timeout
    producer1 = Producer('1')
    g1_timeout = EventCounter('g1')
    g1 = until_timeout(producer1, on_timeout=g1_timeout)

    producer2 = Producer('2')
    g2_timeout = EventCounter('g2')
    g2 = until_timeout(producer2, on_timeout=g2_timeout)

    j12_timeout = EventCounter('j12')
    join12 = until_timeout(izip(g1, g2), on_timeout=j12_timeout)

    producer3 = Producer('3')
    g3_timeout = EventCounter('g3')
    g3 = until_timeout(producer3, on_timeout=g3_timeout)

    join_timeout = EventCounter('join')
    if not mirror:
        join = until_timeout(izip(g3, join12), on_timeout=join_timeout)
    else:
        join = until_timeout(izip(join12, g3), on_timeout=join_timeout)

    yield opendict(locals())


def test_closing_a_lone_branch():
    with complex_tree() as state:
        next(state.join)
        with pytest.raises(StopIteration):
            state.g3.throw(SoftTimeLimitExceeded)
        with pytest.raises(StopIteration):
            # Let join perform its closing stuff
            next(state.join)

        assert state.g3_timeout and state.join_timeout
        assert not state.g1_timeout and not state.g2_timeout

        # However all producers were closed.
        for p in extract_attrs(state, 'producer1', 'producer2', 'producer3'):
            assert p.closed


def test_closing_a_lone_branch2():
    with complex_tree() as state:
        next(state.join)
        with pytest.raises(StopIteration):
            state.join.throw(SoftTimeLimitExceeded)
        with pytest.raises(StopIteration):
            # Let join perform its closing stuff
            next(state.join)

        assert not state.g3_timeout and state.join_timeout
        assert not state.g1_timeout and not state.g2_timeout

        # However all producers were closed.
        for p in extract_attrs(state, 'producer1', 'producer2', 'producer3'):
            assert p.closed


@pytest.mark.xfail(reason='No way to control the flow')
def test_closing_a_lone_branch3():
    with complex_tree() as state:
        next(state.join)
        with pytest.raises(StopIteration):
            state.g1.throw(SoftTimeLimitExceeded)
        with pytest.raises(StopIteration):
            # Let join perform its closing stuff
            next(state.join)

        # This fails because of the way context managers (xoutil.context)
        # interacts with generators.  Notice that the next test is exactly the
        # same but mirrored (the important part is that izip will initialize
        # join12 before initializing g3), so the counter of g3 will become a
        # child of (((<join> | <j12>) | <g1>) | <g2>) so the signaling any of
        # g2 or g1 won't affect g3 in that case.  But as branch5 demonstrate,
        # the mirror then affects g2 when g3 is signaled.
        #
        # So in general trees of iterators are not supported.
        #
        # That would require some serious waiving.
        assert not state.g3_timeout


def test_closing_a_lone_branch4():
    from xoutil.context import context
    assert not context[_UNTIL_TIMEOUT_CONTEXT]
    with complex_tree(mirror=True) as state:
        assert not state.join_timeout
        next(state.join)
        with pytest.raises(StopIteration):
            state.g1.throw(SoftTimeLimitExceeded)
        with pytest.raises(StopIteration):
            # Let join perform its closing stuff
            next(state.join)

        assert not state.g3_timeout


@pytest.mark.xfail()
def test_closing_a_lone_branch5():
    from xoutil.context import context
    assert not context[_UNTIL_TIMEOUT_CONTEXT]
    with complex_tree(mirror=True) as state:
        assert not state.join_timeout
        next(state.join)
        with pytest.raises(StopIteration):
            state.g3.throw(SoftTimeLimitExceeded)
        with pytest.raises(StopIteration):
            # Let join perform its closing stuff
            next(state.join)

        assert not state.g2_timeout
