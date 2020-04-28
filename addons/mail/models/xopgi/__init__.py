from . import index  # noqa
from . import takeover  # noqa

from odoo.models import AbstractModel
from odoo import api

# The index of the root message in a thread.  It seems the "last" message in
# the list is the parent message.
THREAD_ROOT = -1


# Changes the name of the message when the record name changes.
class MailThreadName(AbstractModel):
    _inherit = "mail.thread"

    @api.multi
    def write(self, vals):
        res = super(MailThreadName, self).write(vals)
        name_field = self._rec_name or "name"
        if name_field in vals:
            for thread in self:
                name = getattr(thread, name_field)
                if name and thread.message_ids:
                    thread.message_ids[THREAD_ROOT].record_name = name
        return res
