---
description: |
  [TOPIC] scitex-dev linter Python API
  [DETAILS] Top-level public callables — list_rules; richer surface (check_source/check_files/Rule) via internal modules and MCP.
tags: [scitex-dev-linter-python-api]
---

# Python API

The top-level public surface re-exported from `scitex_dev.linter` is
intentionally small; most use is via the CLI or the MCP tool layer.

## Top-level

| Name           | Purpose                                                       |
|----------------|---------------------------------------------------------------|
| `__version__`  | Installed package version                                     |
| `list_rules`   | Return all rules (built-in + plugin), optional `category=`    |

```python
from scitex_dev import linter

scitex_dev.linter.list_rules()               # every Rule
scitex_dev.linter.list_rules(category="io")  # filter
```

## Richer surface (internal modules)

| Symbol                              | Purpose                                  |
|-------------------------------------|------------------------------------------|
| `scitex_dev.linter._linter.check_source`| Check a Python source string             |
| `scitex_dev.linter._linter.check_files` | Check a list of file paths               |
| `scitex_dev.linter._rules.ALL_RULES`    | Dict of built-in rule definitions        |
| `scitex_dev.linter._plugin_loader.load_plugins` | Discover entry-point plugins     |

These are stable enough to use from scripts but live under
underscore-prefixed modules; long-term, prefer the CLI / MCP layer.

## MCP tools

See `11_mcp-tools.md` — the `linter_check`, `linter_check_source`, and
`linter_list_rules` tools wrap the Python surface for AI agents.

## flake8 plugin

Installing `scitex-dev linter` registers an `STX` flake8 plugin
(`scitex_dev.linter.flake8_plugin:SciTeXFlake8Checker`).
