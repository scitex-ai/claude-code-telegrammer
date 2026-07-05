---
description: |
  [TOPIC] Environment variables
  [DETAILS] `SCITEX_DEV_*` env vars read by scitex-dev at runtime — config path, ecosystem registry, HPC test runner overrides, skills export destination.
tags: [scitex-dev-env-vars]
---

# Environment variables

scitex-dev reads a small set of `SCITEX_DEV_*` environment variables. All are
optional — sensible defaults apply when unset. CLI flags always win over env
vars (see [12_config.md](12_config.md) for the full precedence chain).

## Config & registry

| Variable | Default | Purpose |
|---|---|---|
| `SCITEX_DEV_CONFIG` | `~/.scitex/dev/config.yaml` | Path to the dev `config.yaml` |
| `SCITEX_DEV_HOSTS` | (all enabled) | Comma-separated subset of host names to enable |
| `SCITEX_DEV_GITHUB_REMOTES` | (all enabled) | Comma-separated subset of git-remote names |
| `SCITEX_DEV_REGISTRY` | bundled YAML | Override path for the ecosystem registry (used by `audit-*`) |
| `SCITEX_DEV_NO_DRIFT_WARN` | unset | Set to `1` to silence the editable-install drift warning at import time |

## HPC test runner (`SCITEX_DEV_TEST_*`)

Resolved by `scitex_config.PriorityConfig(env_prefix="SCITEX_DEV_TEST_")`.

| Variable | Default | Purpose |
|---|---|---|
| `SCITEX_DEV_TEST_HOST` | `spartan` | HPC SSH hostname |
| `SCITEX_DEV_TEST_CPUS` | `16` | CPUs per Slurm task |
| `SCITEX_DEV_TEST_PARTITION` | `sapphire` | Slurm partition |
| `SCITEX_DEV_TEST_TIME` | `00:20:00` | Slurm time limit |
| `SCITEX_DEV_TEST_MEM` | `128G` | Slurm memory request |
| `SCITEX_DEV_TEST_REMOTE_BASE` | `~/proj` | Remote project root on the HPC |

See [17_test-runner.md](17_test-runner.md) for usage.

## Skills export

| Variable | Default | Purpose |
|---|---|---|
| `SCITEX_DEV_SKILLS_DEFAULT_EXPORT_DIR` | `~/.claude/skills/scitex/` | Default destination for `scitex-dev skills export` |

## Shell completion

`_SCITEX_DEV_COMPLETE` is the click-internal completion hook (set by the
generated eval line — not user-facing). Use `scitex-dev install-tab-completion`
to wire it up.

## Verifying

```bash
scitex-dev show-config       # resolved config + provenance
scitex-dev doctor            # reports relevant env-var presence
```
