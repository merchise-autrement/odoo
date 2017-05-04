from . import index  # noqa
from . import takeover  # noqa

from openerp.models import Model
from openerp import api, signals

# The index of the root message in a thread.  It seems the "last" message in
# the list is the parent message.
THREAD_ROOT = -1


unlink_thread = signals.Signal('unlink_thread', '''
Signal sent when a thread object is being unlinked.

The signal is sent before the unlink happens to allow logging and auditing.

Errors raised by receivers are propagated.

''')


# Changes the name of the message when the record name changes.
class MailThreadName(Model):
    _name = 'mail.thread'
    _inherit = _name

    @api.multi
    def unlink(self):
        unlink_thread.send(sender=self)
        return super(MailThreadName, self).unlink()

    @api.multi
    def write(self, vals):
        res = super(MailThreadName, self).write(vals)
        name_field = self._rec_name or 'name'
        if name_field in vals:
            for thread in self:
                name = getattr(thread, name_field)
                if name and thread.message_ids:
                    thread.message_ids[THREAD_ROOT].record_name = name
        return res
