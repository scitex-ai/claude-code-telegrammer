---
name: scitex-dev
description: |
  [WHAT] Developer utilities for maintaining the whole SciTeX ecosystem across ~15 packages — version audit and mismatch fixing, editable-install sync, per-host git pull/commit/diff via SSH, bulk rename across files + contents + directories + symlinks (with git-safety guards), aggregated docs search across all packages, a Result/ErrorCode envelope shared by CLI + MCP, DevConfig/HostConfig, a local +…
  [WHEN] Use whenever the user asks to "list scitex versions", "check for version mismatches", "fix version drift", "rename old_name → new_name across all files", "sync my changes to the HPC / laptop / servers", "run tests on the HPC via Slurm", "poll my sbatch job", "fetch HPC test output", "search the docs for save_fig", "commit remote changes on gpu01", "pull all repos", "audit the ecosystem before a…
  [HOW] See sub-skills index for entry points.
tags: [scitex-dev]
allowed-tools: mcp__scitex__dev_*
primary_interface: cli
interfaces:
  python: 2
  cli: 3
  mcp: 2
  skills: 2
  http: 0
---

# scitex-dev Skills Index

> **Interfaces:** Python ⭐⭐ · CLI ⭐⭐⭐ (primary) · MCP ⭐⭐ · Skills ⭐⭐ · Hook — · HTTP —

> These skills are distributed with the **scitex-dev** package.
> Local edits may be overwritten on update. See
> [40_distribution.md](40_distribution.md) for version and update
> instructions.

## Sub-skills

### Core (01–09)
- [01_installation.md](01_installation.md) — Install + extras + smoke verify
- [02_quick-start.md](02_quick-start.md) — `doctor` + `ecosystem list`
- [03_python-api.md](03_python-api.md) — Public Python surface
- [04_cli-reference.md](04_cli-reference.md) — CLI surface map

### Workflows (10–19)
- [10_result-types.md](10_result-types.md) — Result envelope, ErrorCode, @supports_return_as, SideEffect
- [11_cli-mcp-utils.md](11_cli-mcp-utils.md) — Adapters: CLI exit codes, MCP JSON, option factories
- [12_config.md](12_config.md) — DevConfig, HostConfig, load_config, create_default_config
- [13_versions.md](13_versions.md) — list_versions, check_versions, get_mismatches, fix_mismatches
- [14_ecosystem.md](14_ecosystem.md) — Package registry, sync_local, sync_all, sync_host, pull_local
- [15_rename.md](15_rename.md) — bulk_rename, preview_rename, execute_rename
- [16_docs-search.md](16_docs-search.md) — get_docs, build_docs, search_docs, search
- [17_test-runner.md](17_test-runner.md) — run_local, run_hpc_sbatch, poll_hpc_job, fetch_hpc_result
- [18_full-update.md](18_full-update.md) — Release pipeline phases 1–2 (pre-flight + release)
- [19_release-deploy.md](19_release-deploy.md) — Release pipeline phases 3–5 (local sync, NAS deploy, verify)

### Meta (20–29)
- [20_env-vars.md](20_env-vars.md) — `SCITEX_DEV_*` env vars
- [21_dynamic-audit.md](21_dynamic-audit.md) — Dynamic-audit design skeleton for release-gate
- [22_figure-prep-pointer.md](22_figure-prep-pointer.md) — Pointer: figure-prep playbook lives in figrecipe; ecosystem no-synthetic-data policy lives in scientific umbrella

### Architecture (30–39)
- [30_agentic-test-overview.md](30_agentic-test-overview.md) — Four-layer testing model + shared newbie-docker substrate
- [31_agentic-test-skills.md](31_agentic-test-skills.md) — Skill trigger-rate testing (Layer 2 for skills)
- [32_agentic-test-mcp.md](32_agentic-test-mcp.md) — MCP tool-call evaluation (Layer 2+3 for MCP)

### Distribution (40–49)
- [40_distribution.md](40_distribution.md) — Skill cache update mechanics + drift detection

## Quick Reference

```bash
scitex-dev ecosystem list
scitex-dev ecosystem fix-mismatches --dry-run
scitex-dev rename old_name new_name --root . --dry-run
scitex-dev search "save figure"
scitex-dev mcp start
```

```python
import scitex_dev as dev
dev.check_versions()
dev.fix_mismatches(confirm=False)
dev.preview_rename(pattern="old", replacement="new", directory=".")
```


## Environment

- [20_env-vars.md](20_env-vars.md) — `SCITEX_DEV_*` env vars read by scitex-dev at runtime
