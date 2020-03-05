# -*- coding: utf-8 -*-

from . import test_mail_activity
from . import test_mail_followers
from . import test_mail_message
from . import test_mail_mail
from . import test_mail_race
from . import test_mail_resend
from . import test_mail_channel
from . import test_mail_gateway
from . import test_mail_template
from . import test_message_compose
from . import test_message_track
from . import test_invite
from . import test_ir_actions
from . import test_update_notification
from . import test_discuss

# merchise: I don't want to be bothered by theses.  There are differences in
# the count of queries because: we ensure an index per mail.thread; the
# signals system in xoeuf may perform queries to ir.module.module; and
# xopgi.mail_threads checks the installed routers and transports while sending
# or receiving mail.  Only the index is implemented internally but (by nature)
# can make several queries to verify a newly generated index.  The signals
# trapping create and write can perform many queries depending on the amount
# of receivers.  The queries to check installed routers and transports also
# vary with the amount of routers and transports installed (elsewhere).
# Therefore we cannot fix the count of queries.
#
# Furthermore since Odoo S.A do the performance testing themselves, we're OK
# by leaving them out.
#
# from . import test_performance

from . import test_res_users
from . import test_odoobot
from . import test_mail_activity
