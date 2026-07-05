Quick Start
===========

Installation
------------

.. code-block:: bash

   pip install scitex-dev

Docs Aggregation
----------------

.. code-block:: python

   from scitex_dev.docs import get_docs, build_docs

   # All installed packages
   get_docs()

   # Single package
   get_docs(package="scitex-writer", format="json")

   # Build Sphinx docs
   build_docs(package="scitex-writer")

Unified Search
--------------

.. code-block:: python

   from scitex_dev.search import search

   search("save figure")                      # search everything
   search("ttest", scope="api")               # Python API only
   search('+required -excluded "phrase"')      # Google-like syntax

CLI Mixin
---------

Each package gets a ``docs`` subcommand with minimal boilerplate:

.. code-block:: bash

   scitex-writer docs --list
   scitex-writer docs --json
   scitex-writer docs --tldr
