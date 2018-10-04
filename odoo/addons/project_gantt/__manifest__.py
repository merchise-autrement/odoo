# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------
# odoo.addons.project_gantt.__manifest__
# ---------------------------------------------------------------------
# Copyright (c) 2017 Merchise Autrement [~º/~]
# All rights reserved.
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.
#
# Created on 2017-05-02

{
    'name': "Project gantt view",
    'summary': """
        Add gantt views to project tasks""",
    'description': """
        Add gantt views to project tasks
    """,
    'author': "Merchise Autrement",
    "website": "http://gitlab.lahavane.com/mercurio/xhg-autrement-operations.git",
    'category': "Hidden",
    'version': '0.1',
    'depends': ['base', 'project', 'web_gantt'],
    'data': [
        'views/views.xml',
    ],
    'auto_install': True,
}