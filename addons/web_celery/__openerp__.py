#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# ---------------------------------------------------------------------
# web_celery
# ---------------------------------------------------------------------
# Copyright (c) 2015 Merchise Autrement [~º/~] and Contributors
# All rights reserved.
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.
#
# Created on 2015-09-28

dict(
    name='Celery Integration',
    category='Hidden',
    description='Web API for Celery Integration',
    summary='Web API for Celery Integration',
    depends=['web', 'bus'],
    data=['views/assets.xml', ],
    qweb=['static/src/xml/*.xml', ],
    auto_install=True,
    installable=True,
    application=False,
)
