=========
 Prefork
=========

.. warning:: About the accuracy of these notes.

   These note are about learning.  I need to write stuff while I'm learning,
   it let's me to fix it on my head.  At the same time, I believe, these notes
   will serve anyone (including myself) needing to change and/or debug the
   server.

   These notes may contain errors and other inaccuracies.  To the best of my
   effort I will keep them at a minimum, but they only show my learning
   process.

   You are entitled to correct me publicly.

   .. image:: http://imgs.xkcd.com/comics/duty_calls.png

   These notes are distributed in the hope that they will be useful, but
   WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
   or FITNESS FOR A PARTICULAR PURPOSE.



Notes about the preforking implementation in Odoo
=================================================

The server
----------

- Creates a pipe to allow `select` unblock if interrupted (EINTR).

  .. note:: See the `PreforkServer.sleep()` method.

- The server process creates a socket and binds it to the XMLRPC address.

- It then makes the socket to listen.  The backlog is eight times the number
  of workers.

  .. note:: For an explanation of the backlog under Linux see
     http://veithen.github.io/2014/01/01/how-tcp-backlog-works-in-linux.html

- Then workers are forked.  Each worker child will inherit the socket and will
  accept connections from it, as if all of the were listening to the same
  port.

  This is different from the "accepting and then forking" cycle we see in
  other servers (call it simply forking).  When "forking" is employed the
  parent process accepts all incoming connections and then forks children that
  handle that connection.  In HTTP this is rather wasteful.

  This pre-forking opens the listening socket and then forks several workers
  children.  This means that the listening socket FD is shared by all workers.
  All accept connections.  Calling `accept(2)`:man: from several process makes
  all threads/process to block until a connection is established (the 3WHS is
  done).  In older Linuxes, this could lead to a `Thundering Herd`__ (this is
  not actually applicable since the number of workers in our case is limited
  and known); newer linuxes don't suffer from this.

__ http://uwsgi-docs.readthedocs.org/en/latest/articles/SerializingAccept.html


The worker (class and process)
------------------------------

Initialization (before forking):

1. Creates a watchdog pipe to allow `select` unblock if interrupted (EINTR).
   The pipe file descriptors will be inherited by the real worker process
   afterwards.

   The server will poll (actually it uses select to support Windows) the read
   fd of the pipe and the worker will periodically write a single dot ('.').


Loop (after forking):

1. Process limits and kill itself if needed (`Integrity`_).
2. Sends a byte over the watchdog pipe.


Questions
---------

- Just after the worker is forked from its parent process, it modifies the
  socket fd with FD_CLOEXEC.  Why?

  I guess is to support the _reexec().

  But, normally I would send the SIGHUP to the parent to make it reload.

  Does the SIGHUP in the parent kill the childs?


Integrity
---------

``Worker.process_limit``

  - All workers watch over their the parent, if the parent changes its PID
    (the parent died), workers commit suicide.

  - All workers check themselves for several bounds:

    a) Number of requests.
    b) Memory consumption.
    c) CPU time.

    If any bounds are trespassed the worker kill itself.




Signals
-------

It seems that pressing Ctrl-C on the terminal sends the SIGINT to all the
processes workers and servers.  Can't be sure.


Increase the numbers of workers on-the-fly::

   kill -TTIN `cat var/run/xoeuf.pid`


There's an intention in the code for decreasing the number of workers
on-the-fly, but in my tests it does not work::

  kill -TTOU `cat var/run/xoeuf.pid`

Sending the SIGUSR2 signal to a worker process will make to start collecting
profiling data (see the Python profile module).  Sending it again will stop
the profiling and save the data in ``/tmp/odoo.stats<PID>.txt``.  In any case
the profiling will stop after 5 minutes after activation.


Sketch
------

- Windows XP does not have a ``select.poll`` object.

..
   Local Variables:
   ispell-dictionary: "en"
   End:
