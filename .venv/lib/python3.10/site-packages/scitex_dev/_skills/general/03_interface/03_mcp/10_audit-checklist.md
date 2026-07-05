---
description: |
  [TOPIC] Interface Mcp Checklist
  [DETAILS] SciTeX MCP manual audit checklist — run before shipping a package's MCP server. Items marked (A) will be auto-checked by `scitex-dev ecosystem audit-mcp-tools` once it ships; the rest stay manual.
tags: [scitex-general-interface-mcp-audit-checklist]
---

# §9. Audit checklist

Run through this list before shipping a package's MCP server. Items marked **(A)** will be covered by the auditor `scitex-dev ecosystem audit-mcp-tools` ([08_audit-mcp-tools.md](08_audit-mcp-tools.md)) once it ships; until then the whole list is manual.

## Server registration

- [ ] **(A)** Single `FastMCP` instance at `scitex_<pkg>._mcp_server.mcp` (no parallel definitions).
- [ ] **(A)** Umbrella bridge `scitex/_mcp_tools/<pkg>.py` uses `safe_mount` — no `@mcp.tool()` decorators inside the bridge file (other than the `<pkg>_not_available` fallback).
- [ ] **(A)** One mount convention per package; not mixing A and B.
- [ ] **(A)** No double-prefix tool names (`<pkg>_<pkg>_*`).
- [ ] Bridge ships an `<pkg>_not_available` fallback that returns a clear "install with `pip install scitex[<pkg>]`" message.
- [ ] No imports of vendored copies (`from scitex._<pkg>._...`) in the bridge — must reach into the standalone (`from scitex_<pkg>._mcp_server import mcp`).

## Tool naming

- [ ] **(A)** Every tool name is `<pkg>_<verb>_<noun>` snake_case.
- [ ] **(A)** Hyphenated CLI names map to underscores in MCP (`bulk-rename` → `bulk_rename`).
- [ ] **(A)** No banned synonyms (`<pkg>_ls`, `<pkg>_rm`, `<pkg>_display`, ...) — match the catalog "Prefer" column from [CLI §1c](../02_cli/06_noun-verb-catalog.md).
- [ ] **(A)** No bare-noun (`<pkg>_<noun>`) or bare-verb (`<pkg>_<transitive_verb>`) tool names.

## Required CLI subcommands (§3)

- [ ] `<cli> mcp start` exists and launches stdio MCP server.
- [ ] `<cli> mcp doctor` exists, exits 0 when healthy.
- [ ] `<cli> mcp list-tools` exists, accepts `-v|-vv|-vvv` and `--json`.
- [ ] `<cli> mcp show-installation` exists, prints valid JSON for Claude Code config.

## `mcp list-tools` ladder (§4)

- [ ] **(A)** Default output: tool names only.
- [ ] **(A)** `-v` adds signatures; output ⊃ default.
- [ ] **(A)** `-vv` adds one-line docstrings; output ⊃ `-v`.
- [ ] **(A)** `-vvv` adds full docstring + source path + JSON-schema; output ⊃ `-vv`.
- [ ] **(A)** `--json` produces a JSON array; each element has at least `name`.

## Skills integration (§5)

- [ ] **(A)** `<pkg>_skills_list` exists and delegates to `scitex_dev.skills.list_skills(package=…)`.
- [ ] **(A)** `<pkg>_skills_get` exists and delegates to `scitex_dev.skills.get_skill(package=…, name=…)`.
- [ ] Both return the canonical JSON shape (`{"skills": [...]}` and `{"name", "content", "frontmatter"}`).

## Python-API parity (§6)

- [ ] **(A)** Every public Python API in `scitex_<pkg>` has a matching MCP tool.
- [ ] **(A)** Every MCP tool in `<pkg>` traces back to a public Python API (no orphans).
- [ ] **(A)** Argument names and types match between Python and MCP signatures.
- [ ] **(A)** JSON output shape matches between `<cli> --json` and the MCP tool result (top-level keys identical, value types match).
- [ ] Parity documented in the package's `SKILL.md`.

## Process & install hygiene (lessons from §8)

- [ ] After editing `_mcp_server.py`, **server process** is restarted (not just `/mcp reconnect`).
- [ ] No orphan `site-packages/<pkg>/` directory shadowing the editable install (`python -c "import <pkg>; import inspect; print(inspect.getsourcefile(<pkg>))"` → editable repo path).
- [ ] No stale `__editable__.<pkg>-*.pth` files for old versions.
- [ ] No vendored copies under `scitex._<pkg>._...` that duplicate `scitex_<pkg>...`.

## Cross-references

- [ ] CLI side has matching `mcp` subcommand entries in [CLI §1e](../02_cli/03_required-introspection-commands.md).
- [ ] Python-API side documents `<cli> mcp list-tools` as the introspection counterpart of `list-python-apis` (in [03_interface/01_python-api/SKILL.md](SKILL.md)).
