---
description: |
  [TOPIC] Quick Start
  [DETAILS] Get a logger, log at any level (SUCCESS/FAIL included), enable file output.
tags: [scitex-logging-quick-start]
---

<!-- 01_quick-start.md -->

# scitex-logging — Quick Start

## Install

```bash
pip install scitex-logging
```

## Get a logger

```python
from scitex import logging     # re-exports scitex_logging

logger = logging.getLogger(__name__)
logger.info("starting job")
logger.success("job finished")     # custom SUCCESS level
logger.fail("job failed")          # custom FAIL level
```

`scitex_logging` is auto-configured on import: console + file logging are
enabled, level defaults to INFO (override with `SCITEX_LOGGING_LEVEL=DEBUG`).

## Find the log file

```python
from scitex import logging
print(logging.get_log_path())
```

## Reconfigure at runtime

```python
from scitex import logging

logging.configure(level="debug", enable_file=True, enable_console=True)
logging.set_level("WARNING")
```

## Raise a typed SciTeX error

```python
from scitex.logging import SciTeXError, ConfigFileNotFoundError

raise ConfigFileNotFoundError("missing ./config/default.yaml")
```

## Emit a SciTeX warning

```python
from scitex.logging import warn, PerformanceWarning

warn("slow path used", PerformanceWarning)
```
