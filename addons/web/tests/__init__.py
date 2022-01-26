# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import test_image

# merchise: Skip testing of JS core.  I have detected that sometimes the tests
# fail even in runbot.odoo.com; some tests like 'fields > relational_fields >
# FieldOne2Many: one2many and onchange (with date)' are flaky (sometimes it
# passes, sometime it fails).
#
# Let's refrain from changing JS stuff of core Odoo and let them fix their
# issues while we focus on our own addons.
#
# from . import test_js

from . import test_menu
from . import test_serving_base
from . import test_click_everywhere
from . import test_read_progress_bar
