---
description: |
  [TOPIC] Ecosystem Environment Variables
  [DETAILS] Canonical environment-variable naming convention for every SciTeX package — `SCITEX_<MODULE_NAME>_*` prefix rule (never bare `SCITEX_*` except the ecosystem-wide `SCITEX_DIR` relocator), per-package `SCITEX_<PKG>_CONFIG` override, adapter pattern for framework-owned vars (Django/Postgres/Vite settings translate inside their own config — never let framework names leak into SciTeX-owned code), and the mandate that every package document its own env vars in an `NN_env-vars.md` leaf inside its `_skills/`. Use when adding a new env var, auditing drift, or wiring an external-tool adapter.
tags: [scitex-general-ecosystem-environment-variables]
---

# Environment Variable Naming

All SciTeX packages MUST use the `SCITEX_<MODULE_NAME>_*` prefix for environment variables to avoid namespace collisions.

| Package | Prefix | Example |
|---------|--------|---------|
| scitex-notification | `SCITEX_NOTIFICATION_` | `SCITEX_NOTIFICATION_DEFAULT_BACKEND` |
| scitex-cloud | `SCITEX_CLOUD_` | `SCITEX_CLOUD_HOST` |
| scitex-audio | `SCITEX_AUDIO_` | `SCITEX_AUDIO_BACKEND` |
| scitex-writer | `SCITEX_WRITER_` | `SCITEX_WRITER_OUTPUT_DIR` |
| scitex-scholar | `SCITEX_SCHOLAR_` | `SCITEX_SCHOLAR_EMAIL_FROM` |

## Rules

- Primary prefix: `SCITEX_<MODULE>_*` — always checked first
- Backward-compatible fallbacks (e.g., `SCITEX_NOTIFY_*`) are acceptable but the primary prefix takes precedence
- Never use bare `SCITEX_*` without a module name — reserved for **ecosystem-wide framework-level config**
- Show `$ENV_VAR_NAME` in CLI help defaults, not resolved values
- Configuration is external (env vars, config files) — never hardcode secrets or defaults that should be user-configurable

### Reserved bare `SCITEX_*` vars (ecosystem-wide)

These do not belong to any single package and apply across the whole ecosystem. Adding a new bare `SCITEX_*` is a breaking-change-class decision — discuss before adding.

| Variable | Purpose |
|---|---|
| `SCITEX_DIR` | Single lever that relocates the user-scope root from `~/.scitex` to anywhere else. See [`01_ecosystem/06_dot_scitex_directory.md`](06_dot_scitex_directory.md) §6. |

## Feature Flags

All SciTeX feature flags follow the **opt-out** pattern (default enabled, explicitly disable):

| Pattern | Example | Meaning |
|---------|---------|---------|
| `SCITEX_<MODULE>_DISABLE=true` | `SCITEX_OROCHI_DISABLE=true` | Disable a module entirely |
| `SCITEX_MCP_USE_<MODULE>=0` | `SCITEX_MCP_USE_PLT=0` | Disable MCP tool group |

**Convention:**
- Features are **enabled by default** (opt-out)
- Set `DISABLE=true` or `USE_*=0` to turn off
- Never require users to opt-in for core functionality
- Enforce with code (guards, exit), not documentation

### Exceptions (opt-in)

Some features require explicit opt-in due to external dependencies or resource costs:

| Variable | Reason |
|----------|--------|
| `SCITEX_OROCHI_TELEGRAM_BRIDGE_ENABLED` | Telegram bridge connects to external Bot API; must be intentional |
| `SCITEX_SCHOLAR_OPENATHENS_ENABLED` | External authentication service; security-sensitive |
| `SCITEX_NOTIFICATION_TELEGRAM_POLLING_ENABLED` | Long-polling is resource-intensive; opt-in to avoid waste |

These use `_ENABLED=true` to activate. The rule: if a feature touches external services, auth, or consumes resources when idle, it may use opt-in instead.

## Mandatory per-package `NN_env-vars.md` leaf

Every SciTeX package that reads one or more `SCITEX_*` env vars at import or
runtime **MUST** ship an `NN_env-vars.md` leaf inside its
`src/<pkg_snake>/_skills/<pkg>/` directory (next free `NN_`). The leaf lists
every env var the package's source actually reads, as a table:

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_<PKG>_FOO` | One-line purpose | `default` or `—` (required) | string / int / bool / path |

For boolean flags, add a **Feature flags** subsection distinguishing opt-out
(`DISABLE=true` / `USE_*=0`, default enabled) from opt-in (`_ENABLED=true`,
default disabled; justify why).

**Rule:** `NN_env-vars.md` is mandatory for any package that reads one or more
`SCITEX_*` env vars. Link it from the package's `SKILL.md` sub-skill list.

**One-line audit** (run per package, exclude tests / archive):

```bash
grep -rhoE 'SCITEX_[A-Z0-9_]+' scitex-<pkg>/src/ | sort -u
```

Cross-check against the leaf; any var present in source but missing from the
table is a release blocker (see `09_quality/02_checklist.md` §15).

## Quick Checklist (env vars)

- [ ] Every package-owned env var uses the `SCITEX_<MODULE>_*` prefix.
- [ ] No bare `SCITEX_*` without a module name except entries in the reserved-vars table above (currently only `SCITEX_DIR`).
- [ ] Feature flags follow the opt-out pattern (`DISABLE=true` / `USE_*=0`) by default; opt-in (`_ENABLED=true`) only when the feature touches external services, auth, or consumes resources idle.
- [ ] CLI `--help` shows `$ENV_VAR_NAME` as the default placeholder, not the resolved value (avoids leaking secrets).
- [ ] Package ships a `NN_env-vars.md` skill leaf if it reads any `SCITEX_*` env var.
- [ ] The leaf table matches `grep -rhoE 'SCITEX_[A-Z0-9_]+' src/` exactly — every var in source appears in the table.
- [ ] Framework-owned vars (Django/Postgres/Vite/etc.) are translated *inside the framework's own settings file* from canonical `SCITEX_<PKG>_*` vars; framework names never leak into SciTeX-owned code.
