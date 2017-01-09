============================
 The Web Client Application
============================

.. warning:: About the accuracy of these notes.

   These note are about learning.  I need to write stuff while I'm
   learning, it let's me to fix it on my head.  At the same time,
   I believe, these notes will serve anyone (including myself)
   needing to change and/or debug the server.

   These notes may contain errors and other inaccuracies.  To the
   best of my effort I will keep them at a minimum, but they only
   show my learning process.

   You are entitled to correct me publicly.

   .. image:: http://imgs.xkcd.com/comics/duty_calls.png

   These notes are distributed in the hope that they will be
   useful, but WITHOUT ANY WARRANTY; without even the implied
   warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
   PURPOSE.


These notes gather information about the 'web' addon itself, and it
requires some inspection of the 'base' addon.  Also I include notes
about other addons like 'web_graph' and 'web_kanban' which are
automatically installed whenever 'web' is.



The goal
========

The single most important goal of the web addon is to provide a web
client for the Odoo server.

.. note:: Remember Odoo used to have two clients, the web and a
   desktop client.  Both were driven by the same code.  The server
   had the interface programmed in XML and Python, and the client
   merely draw the interface and called remote code.

This led to require to several things:

- Handlers for 'on change' events that are written and ran in the
  Python server are to be seamlessly called and integrated in the
  interface.

  This may pose a serious bottleneck in the server if 'on changes'
  handlers that are resolvable at the UI level go back to the
  server, but it allows to old code being easily executed in the
  web client.

  .. question:: Could I make a decorator ``@make_js`` so that
     Python code compatible with `py.js` be translated and sent to
     the client and executed there?

     This is, in general, not possible due to the fact that some
     handlers access the DB and to give remote proxies might make
     things worse.  But possibly a smart decorator could be
     crafted.



The libraries
=============

There are tons of third parties libraries in
``addons/web/static/lib``.  Even the JS implementation of ``qweb``
is placed there.  But I don't know if it's used (though it's
loaded).

To name a few:

- Backbone 1.1.0
- Bootstrap v3.2.0
- datejs 1.0 alpha-1
- jquery 1.8.3
- select2 3.5.1


The high-level picture
======================

At start the web client creates a instance of the result of calling
``openerp.init()``.  This basically returns a clone of the
`openerp` global and initializes (executes) every module passing
this instance.

This basically means that there can be several instances of
'openerp' around.  But I haven't found yet any applications of this
feature.  In fact, it's mostly hijacked by singletons like the
bus_.

After the initialization, the WebClient_ object is created, and
started.  This is a widget that basically manages the entire
application.



Tour of the sources in `addons/web/static/src/js/`
==================================================



..
   Local Variables:
   ispell-dictionary: "en"
   indent-tabs-mode: nil
   fill-column: 67
   End:
