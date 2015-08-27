=====================
 The threaded server
=====================

.. warning:: About the accuracy of these notes.

   These note are about learning.  I need to write stuff while I'm learning,
   it let's me to fix it on my head.  At the same time, I believe, these notes
   will serve any one (including myself) needing to change and/or debug the
   server.

   These notes may contain errors and other inaccuracies.  To the best of my
   effort I will keep them at a minimum, but they only show my learning
   process.

   You are entitle to correct me publicly.

   .. image:: http://imgs.xkcd.com/comics/duty_calls.png


The threaded server
===================

The threaded server is quite simple.  For instance, we it doesn't have nothing
like ``limit-time-cpu`` for limiting the running time a thread may spent in a
single request.
