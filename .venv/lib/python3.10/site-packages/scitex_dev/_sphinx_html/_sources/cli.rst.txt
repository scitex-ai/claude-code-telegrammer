CLI Mixin
=========

Each SciTeX package can add a standardized ``docs`` subcommand with
minimal boilerplate using ``scitex-dev``'s CLI mixin.

Usage
-----

.. code-block:: bash

   # List available doc pages
   scitex-writer docs --list

   # Get structured JSON (LLM-friendly)
   scitex-writer docs --json

   # Quick-start summary (< 20 lines)
   scitex-writer docs --tldr

   # Specific page
   scitex-writer docs --page api

   # Specific format
   scitex-writer docs --format json

Integration (argparse)
----------------------

.. code-block:: python

   from scitex_dev.cli import register_docs_subcommand

   parser = argparse.ArgumentParser()
   subparsers = parser.add_subparsers()
   register_docs_subcommand(subparsers, package="scitex-writer")

Integration (Click)
-------------------

.. code-block:: python

   from scitex_dev.cli import docs_click_group

   @click.group()
   def cli():
       pass

   cli.add_command(docs_click_group(package="scitex-writer"))

API
---

.. autofunction:: scitex_dev.cli.register_docs_subcommand
   :no-index:
.. autofunction:: scitex_dev.cli.docs_click_group
   :no-index:
