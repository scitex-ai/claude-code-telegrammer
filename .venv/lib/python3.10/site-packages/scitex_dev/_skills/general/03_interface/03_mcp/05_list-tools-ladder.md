---
description: |
  [TOPIC] Interface Mcp List Tools Ladder
  [DETAILS] SciTeX MCP `mcp list-tools` verbosity ladder — names → signatures → docstrings → full schema. Mirrors `list-python-apis`.
tags: [scitex-general-interface-mcp-list-tools-ladder]
---

# §4. `mcp list-tools` verbosity ladder

`<cli> mcp list-tools` accepts `-v|-vv|-vvv` and `--json`, identical in shape to `list-python-apis` (see [03_interface/01_python-api/10_introspection-commands.md](../01_python-api/10_introspection-commands.md)). Each level **adds** to the previous; never replaces.

| Level     | Output                                                                       |
|-----------|------------------------------------------------------------------------------|
| (default) | tool names only                                                              |
| `-v`      | + signature (arg names + types)                                              |
| `-vv`     | + one-line docstring summary                                                 |
| `-vvv`    | + full docstring + source module path + JSON-schema arg spec                 |
| `--json`  | machine-readable array; fields scale with the same ladder                    |

## Example (`scitex-io`)

```bash
$ scitex-io mcp list-tools
io_save
io_load
io_list_formats
io_skills_list
io_skills_get

$ scitex-io mcp list-tools -v
io_save(obj: Any, path: str) -> dict
io_load(path: str) -> dict
…

$ scitex-io mcp list-tools -vv
io_save(obj: Any, path: str) -> dict
    Save any object via scitex-io.save(); returns {path, format, bytes}.
…

$ scitex-io mcp list-tools --json | jq '.[] | .name' | head
"io_save"
"io_load"
…
```

## Why the ladder mirrors `list-python-apis`

Running both at the same level lets the auditor confirm CLI ↔ MCP ↔ Python parity in one diff:

```bash
diff \
  <(scitex-io list-python-apis -v --json | jq '.[] | .name' | sort) \
  <(scitex-io mcp list-tools     -v --json | jq '.[] | .name | sub("^io_"; "")' | sort)
```

If a public Python API has no MCP counterpart (or vice versa), this surfaces it. The future [§7 audit-mcp-tools linter](08_audit-mcp-tools.md) automates this diff.

## Required flags on these commands

In addition to the ladder:

- `--json` — machine-readable. Replaces the human format.
- `-h` / `--help` — usage with at least one example.

## Audit hooks

- [ ] `<cli> mcp list-tools` exists and exits 0.
- [ ] `-v|-vv|-vvv` produce monotonically more output (each level ⊇ previous).
- [ ] `--json` outputs a JSON array (not an object); each element has `name` at minimum.
