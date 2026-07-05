---
description: |
  [TOPIC] scitex-logging Python API
  [DETAILS] Public callables grouped — logger factory, levels, configuration, file output, warnings, ~30 SciTeXError subclasses, validation helpers.
tags: [scitex-logging-python-api]
---

# Python API

## Imports

```python
from scitex_logging import (
    # Logger
    getLogger, llm,
    # Levels
    DEBUG, INFO, WARNING, ERROR, CRITICAL, SUCCESS, FAIL,
    # Configuration
    configure, set_level, get_level,
    enable_file_logging, is_file_logging_enabled, get_log_path,
    # File output
    Tee, tee, log_to_file,
    # Warnings (stdlib `warnings`-style)
    SciTeXWarning, UnitWarning, StyleWarning,
    SciTeXDeprecationWarning, PerformanceWarning, DataLossWarning,
    warn, filterwarnings, resetwarnings,
    warn_deprecated, warn_performance, warn_data_loss,
    # Errors (~30 typed exceptions)
    SciTeXError,
    ConfigurationError, ConfigFileNotFoundError, ConfigKeyError,
    IOError, FileFormatError, SaveError, LoadError,
    ScholarError, SearchError, EnrichmentError,
    PDFDownloadError, DOIResolutionError, PDFExtractionError,
    BibTeXEnrichmentError, TranslatorError, AuthenticationError,
    PlottingError, FigureNotFoundError, AxisError,
    DataError, ShapeError, DTypeError,
    PathError, InvalidPathError, PathNotFoundError,
    TemplateError, TemplateViolationError,
    NNError, ModelError,
    StatsError, TestError,
    # Validation helpers
    check_path, check_file_exists, check_shape_compatibility,
)
```

## Logger

| Symbol | Purpose |
|---|---|
| `getLogger(name)` | Standard stdlib-compatible logger with SUCCESS / FAIL methods |
| `llm` | Pre-configured logger for LLM session traces |

## Levels

DEBUG / INFO / WARNING / ERROR / CRITICAL plus the SciTeX additions
**SUCCESS** (between INFO and WARNING) and **FAIL** (alias of ERROR
with distinct color/format). Set the default with
`SCITEX_LOGGING_LEVEL`.

## Configuration

| Symbol | Purpose |
|---|---|
| `configure(level=..., enable_file=...)` | One-shot setup at process start |
| `set_level(level)` / `get_level()` | Runtime adjust |
| `enable_file_logging(path=None)` | Toggle file sink |
| `is_file_logging_enabled()` | Bool predicate |
| `get_log_path()` | Currently-active log file path |

## File output

| Symbol | Purpose |
|---|---|
| `Tee(path)` | Context manager that tees stdout into a file |
| `tee(path)` | Function form |
| `log_to_file(path)` | Re-route the root logger to `path` for the with-block |

## Warnings (`warnings`-style API)

`warn`, `filterwarnings`, `resetwarnings` mirror the stdlib API but
default to SciTeX warning categories:

`SciTeXWarning`, `UnitWarning`, `StyleWarning`,
`SciTeXDeprecationWarning`, `PerformanceWarning`, `DataLossWarning`.

Convenience emitters: `warn_deprecated`, `warn_performance`,
`warn_data_loss`.

## SciTeXError hierarchy

Single root `SciTeXError`. ~30 typed subclasses grouped by area:
configuration, IO, scholar, plotting, data shape, paths, templates,
NN/models, stats. Use them so callers can `except SubclassError` precisely.

## Validation helpers

| Symbol | Purpose |
|---|---|
| `check_path(p)` | Raise `InvalidPathError` if not a valid path string |
| `check_file_exists(p)` | Raise `PathNotFoundError` if missing |
| `check_shape_compatibility(a, b)` | Raise `ShapeError` on mismatch |

## Two import paths

```python
import scitex_logging        # standalone
import scitex.logging        # umbrella (requires `pip install scitex`)
```
