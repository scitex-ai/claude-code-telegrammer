---
description: |
  [TOPIC] scitex-dev linter Quick Start
  [DETAILS] Smallest useful example — check a file or string for SciTeX-pattern violations.
tags: [scitex-dev-linter-quick-start]
---

# Quick Start

## Check a file from the CLI

```bash
scitex-dev linter check-files src/
```

Each violation prints with rule code (`STX-IO001`, ...) and a
short message; exit code is non-zero when violations are found.

## Check a snippet from Python

```python
from scitex_dev import linter

# All rules grouped by category
rules = scitex_dev.linter.list_rules()
print(len(rules), "rules total")

# Filter by category
io_rules = scitex_dev.linter.list_rules(category="io")
```

The richer programmatic surface (`check_source`, `check_files`) lives
under `scitex_dev.linter._linter` and is also exposed via MCP tools.

## Auto-fix what can be auto-fixed

```bash
scitex-dev linter format-files src/
```

## Pre-commit integration

Add a hook that calls `scitex-dev linter check-files`. See
`07_rule-catalog.md` for which rules are advisory vs blocking.

## Next steps

- `04_cli-reference.md` — full CLI summary
- `06_quick-start.md` — extended walkthrough
- `07_rule-catalog.md` — every built-in STX-* rule
- `10_cli-reference.md` — CLI option-level reference
- `11_mcp-tools.md` — MCP tools for AI agents
