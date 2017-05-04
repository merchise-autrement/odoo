==========================================
 Notes about connections handling in Odoo
==========================================

.. warning:: About the accuracy of these notes.

   These note are about learning.  I need to write stuff while I'm learning,
   it let's me to fix it on my head.  At the same time, I believe, these notes
   will serve anyone (including myself) needing to change and/or debug the
   server.

   These notes may contain errors and other inaccuracies.  To the best of my
   effort I will keep them at a minimum, but they only show my learning
   process.

   You are entitle to correct me publicly.

   .. image:: http://imgs.xkcd.com/comics/duty_calls.png

   These notes are distributed in the hope that they will be useful, but
   WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
   or FITNESS FOR A PARTICULAR PURPOSE.


Cursors and connections
=======================

In Odoo whenever your code requests a new cursor a new connection to the DB
server *may be* opened.  This means that the two cursors operate in different
sessions and, thus, different transactions.

You may test this simply by doing::

  >>> import openerp.sql_db
  >>> from openerp.modules.registry import RegistryManager

  >>> registry = RegistryManager.get(DBNAME)  # set this beforehand
  >>> with registry.cursor() as cr1:
  ...     with registry.cursor() as cr2:
  ...         pass

  >>> # Ignore all the logs (if any)

  >>> openerp.sql_db._Pool
  ConnectionPool(used=1/count=3/max=8)

Which means you have opened 3 connections to the DB *and they're still open*::

  >>> !ps aux | grep postgres

  postgres: manu mercurio [local] idle
  postgres: manu postgres [local] idle
  postgres: manu mercurio [local] idle

Odoo has a lot of places where a new cursor is requested instead of using the
current one.  This should ONLY be done if you're never going to use that
method when you expect a single transaction.

In some places they use a 'LazyCursor' that opens a new cursor to the database
specified by 'threading.current_thread().dbname' (unless you instantiate
LazyCursor with a dbname, and that does not happen in any line of code).


..
   Local Variables:
   ispell-dictionary: "en"
   fill-column: 78
   End:
