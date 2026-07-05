---
description: |
  [TOPIC] Env Vars
  [DETAILS] Environment variables read by `scitex-dev linter` (engine, formerly `scitex-dev linter`) at import / runtime. Prefix is `SCITEX_DEV_LINTER_` — the legacy `SCITEX_LINTER_` prefix is still accepted for one release with a `DeprecationWarning`. Follows the SCITEX_<MODULE>_* convention — see general/10_arch-environment-variables.md.
tags: [scitex-dev-linter-env-vars]
---

# scitex-dev linter — Environment Variables

Canonical prefix: **`SCITEX_DEV_LINTER_`**. The engine accepts the legacy
`SCITEX_LINTER_` prefix for the soft-migration window (one release) and
emits a `DeprecationWarning` naming the canonical replacement.

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_DEV_LINTER_DISABLE` | Disable the linter entirely (opt-out). | `false` | bool |
| `SCITEX_DEV_LINTER_ENABLE` | Comma-separated list of rule IDs to force-enable. | unset | string (CSV) |
| `SCITEX_DEV_LINTER_SEVERITY` | Minimum severity surfaced (`error` / `warning` / `info`). | `warning` | string |
| `SCITEX_DEV_LINTER_EXCLUDE_DIRS` | Directories skipped during linting (no rules fire on files inside). | unset | string (paths) |
| `SCITEX_DEV_LINTER_NON_SCRIPT_DIRS` | Directories whose `.py` files are *not* scripts — script-only rules (S001 `@stx.session` decorator, S002 `__main__` guard) are skipped here. Was `SCITEX_LINTER_LIBRARY_DIRS`; the old name was ambiguous against `EXCLUDE_DIRS`. | unset | string (paths) |
| `SCITEX_DEV_LINTER_LIBRARY_PATTERNS` | Glob patterns matching library files. | `src/**/*.py` | string (glob CSV) |
| `SCITEX_DEV_LINTER_SCRIPT_DIRS` | Directories classified as "script code" (relaxed ruleset — allows top-level side effects). | unset | string (paths) |
| `SCITEX_DEV_LINTER_REQUIRED_INJECTED` | Comma-separated names the `@stx.session` injection rule must enforce. | `CONFIG,plt,logger` | string (CSV) |

## EXCLUDE_DIRS vs NON_SCRIPT_DIRS

Two related concepts that previously shared an ambiguous name:

| | `EXCLUDE_DIRS` | `NON_SCRIPT_DIRS` |
|---|---|---|
| Lint runs on files? | **No** — skipped entirely | **Yes** — file is linted |
| Which rules fire? | None | All except script-only (S001/S002/S003/S004/S005) |
| Typical entries | `__pycache__`, `.git`, `node_modules`, `.venv` | `src/`, `tests/`, `apps/`, `config/` |

## Deprecation aliases

The following legacy names are still read but emit a `DeprecationWarning`:

| Legacy | Canonical |
|---|---|
| `SCITEX_LINTER_*` (any suffix) | `SCITEX_DEV_LINTER_*` |
| `SCITEX_DEV_LINTER_LIBRARY_DIRS` | `SCITEX_DEV_LINTER_NON_SCRIPT_DIRS` |
| `SCITEX_LINTER_LIBRARY_DIRS` | `SCITEX_DEV_LINTER_NON_SCRIPT_DIRS` |

## Feature flags

- **opt-out:** `SCITEX_DEV_LINTER_DISABLE=true` turns the linter off globally.
- No opt-in flags.

## Audit

```bash
grep -rhoE 'SCITEX_(DEV_)?LINTER_[A-Z0-9_]+' $HOME/proj/scitex-dev/src/scitex_dev/linter/ | sort -u
```
