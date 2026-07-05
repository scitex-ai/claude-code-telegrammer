---
description: |
  [TOPIC] Todo
  [DETAILS] SciTeX MCP Convention — Open TODOs — see file body for details.
tags: [scitex-general-interface-mcp-TODO]
---

# SciTeX MCP Convention — Open TODOs

User-tracked items for the canonical MCP skill. Strike through (`~~item~~`) when done.

## Package sweeps — `safe_mount` is the only canonical mount

As of 2026-04-30 the spec was tightened: every umbrella bridge in
`~/proj/scitex-python/src/scitex/_mcp_tools/` must call `safe_mount(...)` from
`._compat`. Direct `mcp.mount(...)` and per-tool `@mcp.tool()` decorators are
both drift. The `audit-mcp-tools §1` check flags both.

### Hand-wrap → safe_mount conversions (22 of 26 bridges)

| File | Tools | Priority | Status |
|---|---|---|---|
| `dev.py` | 13 | high | ✅ done (2026-04-30) |
| `introspect.py` | 12 | high | ⏳ |
| `project.py` | 6 | high | ⏳ |
| `notification.py` | 5 | medium | ⏳ |
| `docs.py`, `orochi_pull.py`, `template.py`, `ui.py` | 4 each | medium | ⏳ |
| `tunnel.py` | 3 | medium | ⏳ |
| `skills.py`, `usage.py` | 2 each | low | ⏳ |
| `audio.py`, `browser.py`, `capture.py`, `clew.py`, `dataset.py`, `diagram.py`, `fr.py`, `linter.py`, `plt.py`, `social.py`, `writer.py` | 1 each | low | ⏳ |

### Direct-`mcp.mount()` → safe_mount conversion (1 bridge)

| File | Current | Migration | Status |
|---|---|---|---|
| `io.py` | `mcp.mount(io_mcp)` | `safe_mount(mcp, io_mcp)` (no namespace — tools already prefixed) | ⏳ |

For each conversion:
1. Verify the standalone exposes `mcp` at `scitex_<pkg>._mcp_server.mcp` (or `_mcp.server`). If not, add it.
2. Use `safe_mount(... namespace="<pkg>")` if standalone tools are bare; use `safe_mount(...)` (no namespace) if tools are already prefixed.
3. Replace the umbrella bridge with the `~30-line` template (see `cloud.py`).
4. Restart MCP server, verify with `ToolSearch select:mcp__scitex__<pkg>_*`.

## `audit-mcp-tools` linter — shipped (2026-04-30)

- [x] **`scitex-dev ecosystem audit-mcp-tools`** is live.

  Source: `scitex_dev/_cli_audit/_mcp_audit.py`. Tests: `tests/test_cli_audit_mcp.py`.
  Reuses every helper from `audit-cli`: registry cascade, severity tiers,
  `_filter_violations`, `_watchdog`, `_isolated_streams`, JSON/human emitters.
  Same flag surface: `--all`, `--json`, `--dry-run`, `--registry`, `--rule §X`,
  `--exclude §X`, `--severity`, `--timeout`, `--behavioral`.

  Iterates the registry; for each package tries
  `import scitex_<pkg>._mcp_server` and walks `FastMCP.list_tools()`.
  Packages without `_mcp_server.mcp` are skipped with
  `info: no _mcp_server.mcp found`.

  ### Coverage now

  | Rule | Status         | Notes                                                                  |
  |------|----------------|------------------------------------------------------------------------|
  | §1   | ✅ static      | Hand-wrap detection, double-prefix detection.                          |
  | §2   | ✅ static      | snake_case, banned synonyms (`ls`/`rm`/…), needs-noun verbs.           |
  | §3   | ✅ behavioral  | `mcp start | doctor | list-tools | show-installation` probed via `--help`. |
  | §4   | ✅ behavioral  | `-v|-vv|-vvv` monotonic check + `--json` parseability.                 |
  | §5   | ✅ static      | `<pkg>_skills_list` + `<pkg>_skills_get` (Convention A and B).         |
  | §6   | ✅ static      | Python-function-API ↔ MCP-tool parity (with prefix normalisation, classes filtered out). |

  ### Resolved design questions

  1. **Rule numbering** — kept §1–§9 from this skill, reused as-is.
  2. **Convention A vs B** — handled. Skills check accepts both prefixed
     and bare forms; parity strips `<short>_` before comparison.
  3. **Single source of truth** — defaults to per-package introspection;
     umbrella-mounted alternative deferred until cross-validation needed.
  4. **`--behavioral`** — implemented; same opt-in flag and per-subprocess
     timeout cap as `audit-cli`.

  ### Still open

  - [ ] §6 parity threshold is coarse (>50% missing → flag). A future
        `--strict` mode could flag every individual gap.
  - [ ] §1 bridge-pattern check doesn't yet detect *mixed* mount conventions
        in one bridge file (`safe_mount` call + `@mcp.tool()` decorator both present).
  - [ ] No JSON-schema arg-spec parity check for `-vvv` content yet — we
        only verify the JSON parses, not that arg names/types match the
        Python signature.

## Documentation

- [x] Split monolithic `03_interface/03_mcp.md` into per-section files (this directory).
- [x] Remove the legacy `03_interface/03_mcp.md` flat file. Parent `general/SKILL.md` now points at `03_interface/03_mcp/SKILL.md`.

## Reference example

- [ ] Auto-generate a reference shape file showing the canonical `_mcp_server.py` structure (parallel to CLI's [16_example.md](../02_cli/16_example.md)). Source: `~/proj/scitex-audio/src/scitex_audio/_mcp_server.py`.

## Design questions

- [ ] Should `mcp doctor` exit 1 on degradation or always 0? Current spec says "0 healthy / 1 degraded / 2 critical" — consistent with `audit-cli` severity tiers.
- [ ] Should the umbrella `scitex` itself expose `dev_audit-mcp-tools` once the linter ships, or only via `scitex-dev`?
- [ ] Cleanup of vendored `scitex._dev._rename`, `scitex._dev._mcp` modules — they're now unused after the dev.py mount refactor. Delete in a follow-up PR after confirming no callers remain.
