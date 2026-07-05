---
description: |
  [TOPIC] Quick start
  [DETAILS] Smallest useful example — `scitex-dev doctor` for a health check, then `scitex-dev ecosystem list` to inspect the ecosystem.
tags: [scitex-dev-quick-start]
---

# Quick start

After [installing](01_installation.md), run two commands to verify your setup
and learn the surface.

## 1. `scitex-dev doctor`

Diagnose the local environment — Python version, installed scitex packages,
relevant environment variables, optional services (orochi/MCP).

```bash
scitex-dev doctor
```

Use this as the first thing you run on a new machine, after a `pip` upgrade,
or when something behaves oddly. The output flags `ok` / `warn` / `fail`
per probe and is safe to share when reporting issues.

## 2. `scitex-dev ecosystem list`

List every scitex package the ecosystem registry knows about, with installed
version, latest published version on PyPI, and a green/red drift indicator.

```bash
scitex-dev ecosystem list
scitex-dev ecosystem list --json   # machine-readable
```

This is the entry point for ecosystem-wide work. From here you can:

- `scitex-dev ecosystem fix-mismatches --dry-run` — preview version drift fixes
- `scitex-dev ecosystem audit-skills` — audit `_skills/` directories across packages
- `scitex-dev ecosystem sync-local` — refresh editable installs

## Next steps

- Surface map: [04_cli-reference.md](04_cli-reference.md)
- Public Python API: [03_python-api.md](03_python-api.md)
- Per-workflow deep dives: see the **Workflows (10–19)** section in
  [SKILL.md](SKILL.md).
