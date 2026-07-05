---
description: |
  [TOPIC] Environment Variables
  [DETAILS] SCITEX_LOGGING_LEVEL and other SCITEX_* env vars read at import/runtime.
tags: [scitex-logging-env-vars]
---

# scitex-logging — Environment Variables

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_LOGGING_LEVEL` | Default log level for all scitex loggers. | `INFO` | string (`DEBUG`/`INFO`/`WARNING`/`ERROR`) |
| `SCITEX_LOGGING_FORMAT` | Format selector: `plain`, `rich`, or `json`. | `plain` | string |
| `SCITEX_LOGGING_FORCE_COLOR` | Force ANSI color even when stderr is not a TTY. | `false` | bool |
| `SCITEX_LOG_FORMAT` | Back-compat alias for `SCITEX_LOGGING_FORMAT`. | inherit | string |
| `SCITEX_FORCE_COLOR` | Ecosystem-wide force-color flag (shared with scitex-plt, etc.). | `false` | bool |
| `SCITEX_DIR` | Base SciTeX data dir (used to locate per-session log files). | `~/.scitex` | path |

## Feature flags

- **opt-in:** `SCITEX_LOGGING_FORCE_COLOR=true` (and the ecosystem-wide
  `SCITEX_FORCE_COLOR=true`) force ANSI escapes when pipes / redirections
  would normally strip them. Off by default because most CI log stores
  display raw escapes.

## Notes

- `SCITEX_LOGGING_LEVEL` > `SCITEX_LOGGING_FORMAT` > back-compat aliases in
  precedence.
- `SCITEX_EOF` found in the grep output is a file-marker string, not an env
  var — safely ignore.

## Audit

```bash
grep -rhoE 'SCITEX_[A-Z0-9_]+' $HOME/proj/scitex-logging/src/ | sort -u
```
