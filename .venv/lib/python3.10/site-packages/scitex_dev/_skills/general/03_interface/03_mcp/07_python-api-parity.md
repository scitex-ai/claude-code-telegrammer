---
description: |
  [TOPIC] Interface Mcp Python Api Parity
  [DETAILS] SciTeX MCP ↔ Python API parity — same logical name, same arg names/types, same JSON output shape. Concrete contract with examples.
tags: [scitex-general-interface-mcp-python-api-parity]
---

# §6. Python API ↔ MCP parity

Every MCP tool wraps a public Python API call. The two surfaces must agree.

## Naming convention

Public Python API `scitex_<pkg>.<verb>_<noun>(...)` ↔ MCP tool `<pkg>_<verb>_<noun>(...)`.

| Python                                    | MCP                       |
|-------------------------------------------|---------------------------|
| `scitex_io.save(obj, path)`               | `io_save`                 |
| `scitex_io.list_formats()`                | `io_list_formats`         |
| `scitex_stats.run_test(*groups, kind=…)`  | `stats_run_test`          |
| `scitex_dev.bulk_rename(config)`          | `dev_bulk_rename`         |

## Argument parity

Same names, same types. Don't rename `path` → `file_path` for MCP. Don't change `bool` → `int`.

```python
# Python
def save(obj: Any, path: str | Path, *, force: bool = False) -> Path: ...

# MCP wrapper — argument names match exactly
@mcp.tool()
async def io_save(obj: Any, path: str, force: bool = False) -> dict: ...
```

## JSON output shape

The MCP tool's return JSON and `<cli> --json`'s stdout must have **identical top-level keys** with **matching value types**. Whitespace and field order don't matter; key sets and types do.

```bash
# CLI side
$ scitex-io save data.csv ./out.csv --json
{"path": "./out.csv", "format": "csv", "bytes": 4096, "ok": true}

# MCP side
io_save(obj=data, path="./out.csv")
→ {"path": "./out.csv", "format": "csv", "bytes": 4096, "ok": true}
```

## Allowed differences

- MCP results MAY include MCP-specific envelope fields (`tool`, `request_id`, `idempotent`) **outside** the parity-checked payload — keep the payload itself identical.
- The CLI may add a `_human` key when `--json` is omitted; that key must NOT appear in `--json` output.
- Type coercion at the MCP boundary (e.g. `Path` → `str` in JSON) is allowed and expected.

## Why parity matters

- An agent that ran `scitex-io save data.csv ./out.csv --json` learns the output shape; calling `io_save` next should not surprise it.
- The audit linter ([08_audit-mcp-tools.md](08_audit-mcp-tools.md)) cross-checks `list-python-apis --json` and `mcp list-tools --json` to flag drift.

## Auditor hook

A future check (see [08_audit-mcp-tools.md](08_audit-mcp-tools.md)):

```bash
# For every public Python API in <pkg>:
#   assert there is an MCP tool with matching name + args
# For every MCP tool in <pkg>:
#   assert it wraps a public Python API (no orphan MCP-only logic)
```
