#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------
# Copyright (c) Merchise Autrement [~º/~] and Contributors
# All rights reserved.
#
# This is free software; you can do what the LICENCE file allows you to.
#

dict(
    name="Celery Integration",
    author="Merchise Autrement [~º/~]",
    category="Hidden",
    description="Web API for Celery Integration",
    summary="Web API for Celery Integration",
    depends=["web", "bus"],
    data=["views/assets.xml"],
    qweb=["static/src/xml/*.xml"],
    auto_install=True,
    installable=True,
    application=False,
)
