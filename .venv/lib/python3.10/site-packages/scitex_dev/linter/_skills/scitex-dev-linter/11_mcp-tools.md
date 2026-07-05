---
description: |
  [TOPIC] Mcp Tools
  [DETAILS] MCP tools for AI agents — check code, list rules.
tags: [scitex-dev-linter-mcp-tools]
---

# MCP Tools

| Tool | Description |
|------|-------------|
| `linter_check` | Lint a file or directory; returns per-violation `(rule_id, line, message)` |
| `linter_check_source` | Lint an in-memory Python source string (no file needed) |
| `linter_list_rules` | Browse the 47-rule catalog, optionally filtered by `category` (I/IO/P/PA/S/FM/ST) |

## Typical usage

```
linter_list_rules(category="IO")   # show STX-IO* rules
linter_check(path="src/")           # lint a whole tree
linter_check_source(source="...")   # lint a snippet before committing
```

Each violation pairs with a rule ID (e.g. `STX-IO001`); look it up with
`linter_list_rules` to get the full rationale and fix guidance.
