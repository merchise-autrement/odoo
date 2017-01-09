# -*- coding: utf-8 -*-

import mail_message_subtype
import mail_tracking_value
import mail_alias
import mail_followers
import mail_notification
import mail_message
import mail_mail
import mail_thread

# Needed at this point cause mail_group and other objects are injected with
# mail.thread behaviour when imported below.
from . import xopgi  # noqa

import mail_channel
import mail_template
import mail_shortcode
import res_partner
import res_users
import res_config
import update
import ir_actions
import ir_autovacuum
import html2text
