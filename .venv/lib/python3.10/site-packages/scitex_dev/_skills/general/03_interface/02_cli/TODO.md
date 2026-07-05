---
description: |
  [TOPIC] Todo
  [DETAILS] SciTeX CLI Convention — Open TODOs — see file body for details.
tags: [scitex-general-interface-cli-TODO]
---

# SciTeX CLI Convention — Open TODOs

User-tracked items for the canonical CLI skill.
Strike through (`~~item~~`) when done.


## Package sweeps

- [ ] Replace bare `completion` subcommand with `install-shell-completion` / `print-shell-completion`
      across all `scitex-*` packages.

- [ ] Replace bare `version` subcommand with `--version` / `-V` flag
      across all `scitex-*` packages.

- [ ] Revise `scitex-plt` / `figrecipe` so its actual CLI matches the reference example
      in [16_example.md](16_example.md).

- [ ] Triage the 1067 warnings in [DRIFT_REPORT.md](DRIFT_REPORT.md).
      Highest-leverage sweeps:
      - §4 (486 hits) — add `Example:` epilogs.
      - §2 (368 hits) — add `--json` / `--dry-run` / `--yes` decorators.
      - §6b (24 hits) — config-path docs in root `--help`.


### Open: tool UX & ergonomics

- [ ] **Cache audit results**
      keyed on (package, version) so repeated runs in CI are fast.

### Open: companion tool — `audit-mcp-tools`

- [x] **`scitex-dev ecosystem audit-mcp-tools`** shipped.
      Lives in `_cli_audit/_mcp_audit.py`. Reuses the registry cascade,
      severity tiers, filter helpers, watchdog, and stream-isolation from
      `audit-cli`. Same flag surface (`--all` / `--json` / `--dry-run` /
      `--registry` / `--rule` / `--exclude` / `--severity` / `--timeout` /
      `--behavioral`).

      Static checks: §1 (hand-wrap detection, double-prefix), §2 (naming +
      synonyms + needs-noun), §5 (skills tools), §6 (Python-API parity,
      function-only). Behavioral: §3 (subcommand presence) and §4 (ladder +
      `--json`). Tests live in `tests/test_cli_audit_mcp.py`.

      Spec doc: [03_interface/03_mcp/08_audit-mcp-tools.md](../03_mcp/08_audit-mcp-tools.md).


### Open: package fixes & stale state

- [ ] **`scitex-tunnel`** — installed editable but `scitex_tunnel.cli` module is missing.
      Investigate; not an auditor bug.

- [ ] **`scitex-canvas`** — entry point points at `scitex.canvas.mcp_server`,
      but module not installed.
      Likely stale registration after a rename.
      Either reinstall or remove from the registry.


### Open: catalog & vocabulary growth

- [ ] **§1d hits (25 across ecosystem) need triage.**

      Some are real typos;
      others are legitimate domain nouns that should join the canonical catalog
      in [06_noun-verb-catalog.md](06_noun-verb-catalog.md).

      Walk the per-package warning files in `/tmp/cli-drift/`
      and split into "fix in package" vs "add to catalog".


### Open: implementation hygiene

- [ ] **Argparse adapter only captures the first `parse_args` call.**

      Multi-parser CLIs (rare but possible) lose the rest.
      Document the limitation; add a config-driven override if a real package needs it.

## Reference example

- [ ] Auto-generate [16_example.md](16_example.md)
      from a real package's `--help-recursive` output
      rather than hand-maintaining it.

      Avoids drift.


## Design questions

- [ ] Should `sync` ever stand alone, or always require an object (`sync-ecosystem`)?
      Currently §1d says always require — confirm with real-world usage.

- [ ] `tag` is currently verb-only.
      Confirm no package needs `tag` as a noun (e.g. `tag list`).

- [ ] Where do package-bootstrap flows (`scitex new`, `scitex create-project`) belong —
      in this canonical skill or in a separate "scaffolding" skill?
