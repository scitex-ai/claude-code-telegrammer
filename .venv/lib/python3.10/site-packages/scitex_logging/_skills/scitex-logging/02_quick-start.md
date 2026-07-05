---
description: |
  [TOPIC] scitex-logging Quick start
  [DETAILS] Get a logger, log at SUCCESS / FAIL, configure file output, raise SciTeXError, emit deprecation warning.
tags: [scitex-logging-quick-start]
---

# Quick Start

## Get a logger

```python
from scitex_logging import getLogger

log = getLogger(__name__)
log.info("starting")
log.success("trained 10 epochs")        # custom level
log.fail("dataset missing")              # custom level
log.warning("low memory")
```

## Configure once at startup

```python
from scitex_logging import configure

configure(level="INFO", enable_file=True)   # also writes to ./logs/<...>
```

`configure()` is idempotent — call it from your `main()` entry point.

## Log to a file

```python
from scitex_logging import Tee

with Tee("run.log"):
    print("captured into run.log too")   # tees stdout
```

## Raise a typed SciTeX error

```python
from scitex_logging import SciTeXError, ConfigKeyError

try:
    raise ConfigKeyError("missing 'database.url'")
except SciTeXError as e:
    log.fail(str(e))
```

## Emit a structured warning

```python
from scitex_logging import warn_deprecated, warn_data_loss

warn_deprecated("old_api will be removed in 2.0")
warn_data_loss("converting float64 → float32")
```

## Next

- [03_python-api.md](03_python-api.md) — full surface
- [20_env-vars.md](20_env-vars.md) — `SCITEX_LOGGING_LEVEL` and friends
