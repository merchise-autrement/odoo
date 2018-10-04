==================================
 Loading modules and the registry
==================================

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


Models, addons and the registry
===============================

.. note:: Naming things.

   The Odoo nomenclature has evolved over the years, but the code still uses
   several names for the same concept.  For instance, the registry it's called
   pool at times.

   The most confusing are the names given to 'addon': 'module', and 'package'.

   We'll try to keep things clearer and give specific meaning to all of these
   words:

   .. glossary::

      module

        It's Python 'module' concept. Most of the time this matches a file in
        the file system.

      package

        It's Python 'package' concept, i.e a group of modules and possible
        sub-packages.  Most of the time it matches to a directory in the file
        system which contains a ``__init__.py`` file.

      addon

        It's an Odoo concept that allows customization of the system.  They
        are implemented as `packages <package>`:term:, whose directory must
        have a ``__openerp__.py`` file containing the addon's manifest.

It seems that one of the major restrictions posed to the addon feature it's
that of the isolation of several DBs in a single system.  Each DB may have
it's own set of addons installed, and while the same addon has the same code
and DB-related structured across many DBs, different DBs may differ in the
addons to be invoked when accessing a given Model.

This is key to understand why need to access the Models via the Registry
instead of importing them.

Let's say addon A defines model M, which is then extended (i.e ``_inherit =
_name``) in addon B, which of course depends on addon A.  If DB1 has installed
addon A but not B, then for DB1 the Registry will return a class that only
what's defined in addon A.  If DB2 has installed addons B, then a Registry of
it will return a class that has both definitions loaded.

When defining a Model::

  >>> class Model(openerp.Model):
  ...     # all you need here like the _name, _inherit, etc
  ...     pass

Odoo refrains from doing anything but to keep a record that this class is
defined in addon X.

When instantiating a Registry for a given DB, Odoo first needs to know which
addons are installed in this DB.

The right way to a reference to a Registry is by calling
``RegistryManager.get(dbname)``.  Underneath, it calls ``RegistryManager.new``
if needed.  And ``new`` calls ``openerp.modules.load_modules`` to load the
addons and fill the registry with the proper models.

The process to fill the registry with the models is split between modules
``openerp/models.py``, ``openerp/modules/loading.py``,
``openerp/modules/graph.py`` and ``openerp/addons/base/module/module.py``.

Here we only give major points:

- A Graph instance is used to keep dependencies between addons.  Inside this
  module, an addon is a `node` inside this graph, but sometimes the use the
  words `package` and `module` to refer to addons.

  The main interface of the graph is the ``add_modules`` and ``add_module``
  methods.  Nevertheless, the loading process may affect the graph by changing
  the DB via the ``ir.module.module`` model.  (For this to be possible the
  loading must first load the "base" addon.)

- The ``loading_modules``, creates a new Graph and adds the module "base".
  This will setup the 'ir.module.module' model, and having that, the loading
  process updates the addon list in the DB.  Afterwards, all the addons are
  loaded in a topological order according to the dependency graph.


When installing a single addon into the registry we must collect all the Model
class and combine them to produce a single class for the model.  That's what
the Registry keeps.  That's the job of ``Registry.load()`` and
``BaseModel._build_model``.

``BaseModel._build_model`` class-method builds a new class and injects the
bases according to ``_inherit`` and ``_inherits`` and the *current* state of
the registry (called `pool`).  Notice that for a any given *model* there will
be at least two classes:

- The class that *defines* (part of) the structure of the model.

- The class to which a registry will have a singleton copy that represents
  that model for the registry's DB.

  This class will call it the Model Class.  Whereas the first type of class
  we'll call it a Model Definition class.  An instance of a Model Class is a
  Model.

  .. note:: The `xoeuf.osv.orm.get_modelname` function deals with Model
     Definition Classes, but trying to import from 'xoeuf.models.proxy' try to
     get a registry and thus deals with Models (i.e instances of a Model
     Class).

  Model Classes are never stored in a global state like ``sys.modules``.  The
  registry holds a reference to an *instance* of the Model Class, and that
  instance is the only one having a reference to the Model Class.  If the
  registry goes away or deletes a model the Model Class can be reclaimed by
  the garbage collector, but the Model Definition Classes stay attached to the
  Python modules ready to be used again.

.. warning:: Your extensions mixins may be disregarded.

   This is best explained by a concrete example:

   The addon `mail` defines the 'mail.thread' model.  Many other addons like
   `product`, `sale`, etc depend on `mail` and use the 'mail.thread' model as
   a mixin (i.e ``_inherit = ['mail.thread']``).  If you create an addon that
   extends 'mail.thread', the only logical dependency you have is `mail`, but
   then Odoo is free to load you addon at any point after loading `mail`, if
   your addon loads after `product`, then the model defined in `product` won't
   see your extensions to 'mail.thread', since your Model Definition class has
   not yet being loaded into 'mail.thread'.
