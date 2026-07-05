Unified Search
==============

Search across the entire SciTeX ecosystem — Python APIs, CLI commands,
MCP tools, and documentation pages.

Query Syntax
------------

Google-like query operators:

.. list-table::
   :header-rows: 1

   * - Syntax
     - Meaning
     - Example
   * - ``word``
     - Optional term (boosts score)
     - ``search("save figure")``
   * - ``+word``
     - Required term (must match)
     - ``search("+ttest stats")``
   * - ``-word``
     - Excluded term (must NOT match)
     - ``search("stats -deprecated")``
   * - ``"phrase"``
     - Exact phrase match
     - ``search('"save figure"')``

Scopes
------

.. list-table::
   :header-rows: 1

   * - Scope
     - Searches
   * - ``all``
     - Everything (default)
   * - ``api``
     - Python API functions, classes, methods
   * - ``cli``
     - CLI subcommands (console_scripts entry points)
   * - ``mcp``
     - MCP tool names and descriptions
   * - ``docs``
     - Documentation page titles and content

API
---

.. autofunction:: scitex_dev._docs.search.search
.. autofunction:: scitex_dev._docs.search.parse_query
.. autofunction:: scitex_dev._docs.search.score_text
