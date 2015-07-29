import psycopg2

import openerp
from openerp import SUPERUSER_ID
from openerp import http


class MailController(http.Controller):
    _cp_path = '/mail'

    @http.route('/mail/receive', type='json', auth='none')
    def receive(self, req):
        """ End-point to receive mail from an external SMTP server. """
        dbs = req.jsonrequest.get('databases')
        for db in dbs:
            message = dbs[db].decode('base64')
            try:
                registry = openerp.registry(db)
                with registry.cursor() as cr:
                    mail_thread = registry['mail.thread']
                    mail_thread.message_process(cr, SUPERUSER_ID, None,
                                                message)
            except psycopg2.Error:
                pass
        return True
