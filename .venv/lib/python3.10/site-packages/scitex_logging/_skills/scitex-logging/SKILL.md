---
name: scitex-logging
description: |
  [WHAT] Enhanced Python logging + warnings + 30+ class `SciTeXError` exception hierarchy — stdlib-compatible wrapper with SUCCESS/FAIL levels, auto file output, and structured category warnings.
  [WHEN] Getting a logger, logging SUCCESS/FAIL, teeing stdout to a log file, raising a typed SciTeX error, emitting a deprecation/data-loss warning, or configuring via `SCITEX_LOGGING_LEVEL`.
  [HOW] `from scitex_logging import getLogger, configure, Tee, SciTeXError, warn_deprecated, ...` — drop-in stdlib replacement.
tags: [scitex-logging]
primary_interface: python
interfaces:
  python: 3
  cli: 0
  mcp: 0
  skills: 2
  http: 0
---

# scitex-logging

Auto-configured drop-in extension of `logging`:

## Installation & import (two equivalent paths)

The same module is reachable via two install paths. Both forms work at
runtime; which one a user has depends on their install choice.

```python
# Standalone — pip install scitex-logging
import scitex_logging
scitex_logging.getLogger(...)

# Umbrella — pip install scitex
import scitex.logging
scitex.logging.getLogger(...)
```

`pip install scitex-logging` alone does NOT expose the `scitex` namespace;
`import scitex.logging` raises `ModuleNotFoundError`. To use the
`scitex.logging` form, also `pip install scitex`.

See [../../general/02_interface-python-api.md] for the ecosystem-wide
rule and empirical verification table.

- Adds `SUCCESS` and `FAIL` levels on top of DEBUG/INFO/WARNING/ERROR/CRITICAL.
- File logging is on by default; log path via `get_log_path()`.
- Ships a SciTeX-wide **exception hierarchy** (`SciTeXError` and ~30 subclasses)
  plus a `warnings`-style API (`SciTeXWarning` etc.).
- Env var `SCITEX_LOGGING_LEVEL` picks the default level at import time.

## Sub-skills

- [01_installation.md](01_installation.md) — pip install + smoke verify
- [02_quick-start.md](02_quick-start.md) — get a logger, configure, file output, raise/warn
- [03_python-api.md](03_python-api.md) — config, levels, warnings, errors
- [10_quick-start.md](10_quick-start.md) — legacy quick-start (kept for context)
- [11_python-api.md](11_python-api.md) — legacy API notes (kept for context)

No CLI, no MCP tools.


## Environment

- [20_env-vars.md](20_env-vars.md) — SCITEX_* env vars read by scitex-logging at runtime
