---
description: |
  [TOPIC] Interface Cli Mcp Parity
  [DETAILS] SciTeX CLI ↔ MCP tool parity — same logical name, args, JSON shape. Documented in package SKILL.md.
tags: [scitex-general-interface-cli-mcp-parity]
---

# §7. MCP tool parity

When a CLI command has an MCP tool counterpart:

- Same logical name (close match between subcommand and tool).
- Same argument names and types.
- Same JSON output shape.
- Document parity in the package's `SKILL.md`.

## Naming convention

CLI subcommand `<noun> <verb>` (or `<verb>-<noun>`) → MCP tool `<pkg>_<verb>_<noun>` (snake_case, package-prefixed).

| CLI invocation                        | MCP tool name              |
|---------------------------------------|----------------------------|
| `scitex-io save <obj> <path>`         | `io_save`                  |
| `scitex-io list-formats`              | `io_list_formats`          |
| `scitex-io mcp list-tools`            | `io_list_tools`            |
| `scitex-stats run-test --kind ttest`  | `stats_run_test`           |

## JSON shape parity — concrete contract

`<cli> <subcommand> --json` and the matching MCP tool MUST return JSON whose **top-level keys are identical** and whose **value types match**. Field order and whitespace don't matter; key sets and types do.

```bash
# CLI side
$ scitex-io save data.csv ./out.csv --json
{"path": "./out.csv", "format": "csv", "bytes": 4096, "ok": true}

# MCP side — same call via the tool
io_save(obj=data, path="./out.csv")
→ {"path": "./out.csv", "format": "csv", "bytes": 4096, "ok": true}
```

Allowed differences:

- MCP results MAY include MCP-specific envelope fields (`tool`, `request_id`) **outside** the parity-checked payload — keep the payload itself identical.
- CLI MAY add human-readable fields under a `_human` key when `--json` is omitted; that key must NOT appear in `--json` output (per §8 [14_stdout-stderr.md](14_stdout-stderr.md)).

## Auditor hook (TODO)

A future check: invoke `<cli> list-python-apis --json` and `<cli> mcp list-tools --json`, then assert each public API has a corresponding MCP tool name. See coverage matrix in [07_audit-cli.md](07_audit-cli.md).
