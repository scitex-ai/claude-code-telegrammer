---
description: |
  [TOPIC] Python API
  [DETAILS] Logger config, levels, warnings, guards, and SciTeXError exception hierarchy.
tags: [scitex-logging-python-api]
---

<!-- 02_python-api.md -->

# scitex-logging — Python API

## Levels

Integers added to stdlib logging, ordered most → least severe (within usual levels):

```
CRITICAL, FAIL, ERROR, WARNING, SUCCESS, INFO, DEBUG
```

All are exported as module attributes.

## Loggers

| Symbol | One-liner |
|--------|-----------|
| `getLogger(name)` | Same as stdlib `logging.getLogger`, but returns a `SciTeXLogger` with `.success()` and `.fail()` methods. |
| `Tee`, `tee` | Duplicate stdout/stderr to a file handle. |
| `log_to_file` | Context manager: redirect logging into a file for a block. |

## Configuration

| Symbol | One-liner |
|--------|-----------|
| `configure(level, enable_file, enable_console, capture_prints)` | Full (re)configuration. |
| `set_level`, `get_level` | Adjust or query the root level. |
| `enable_file_logging`, `is_file_logging_enabled` | Toggle / query file handler. |
| `get_log_path` | Absolute path to the current log file. |

Environment variable: `SCITEX_LOGGING_LEVEL`
(`DEBUG|INFO|WARNING|ERROR|CRITICAL|SUCCESS|FAIL`).

## Warnings (`warnings`-style)

Warning classes: `SciTeXWarning`, `UnitWarning`, `StyleWarning`,
`SciTeXDeprecationWarning`, `PerformanceWarning`, `DataLossWarning`.

Functions: `warn`, `filterwarnings`, `resetwarnings`,
`warn_deprecated`, `warn_performance`, `warn_data_loss`.

## Errors (exception hierarchy rooted at `SciTeXError`)

Config: `ConfigurationError`, `ConfigFileNotFoundError`, `ConfigKeyError`.

I/O: `IOError`, `FileFormatError`, `SaveError`, `LoadError`.

Scholar: `ScholarError`, `SearchError`, `EnrichmentError`, `PDFDownloadError`,
`DOIResolutionError`, `PDFExtractionError`, `BibTeXEnrichmentError`.

Other: `TranslatorError`, `AuthenticationError`, `PlottingError`,
`FigureNotFoundError`, `AxisError`, `DataError`, `ShapeError`, `DTypeError`,
`PathError`, `InvalidPathError`, `PathNotFoundError`, `TemplateError`,
`TemplateViolationError`, `NNError`, `ModelError`, `StatsError`, `TestError`.

Validation helpers: `check_path`, `check_file_exists`, `check_shape_compatibility`.

## Submodule: `llm`

`scitex_logging.llm` — LLM-session log helpers. See `scitex_logging/llm/`
for the exported API; kept separate so plain logging does not depend on it.

See `scitex_logging/_*.py` for concrete signatures. The module is
auto-configured on import, so most users just need `getLogger`.
