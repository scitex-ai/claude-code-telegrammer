---
description: |
  [TOPIC] Interface Python Api Error Handling
  [DETAILS] Error-class hierarchy is canonical in `scitex_dev._errors` (ErrorCode enum, classify_exception, structured response shape). Downstream packages import + extend rather than redefining. Ecosystem-wide consistency for LLM-readable error responses. Standard library exceptions still preferred for plain Python errors.
tags: [scitex-general-interface-python-api-error-handling]
---

# Error Handling

> Canonical implementation lives in **`scitex_dev.errors`** and is re-exported at the top level: `from scitex_dev import ScitexError, ErrorCode, classify_exception` works today. Every other SciTeX package imports + extends rather than redefining its own error taxonomy. Treat scitex-dev as the ecosystem-wide developer tooling host (parallels `scitex-dev ecosystem ...` CLI commands).

## Two layers

### Layer 1 — standard library exceptions (always prefer)

```python
def save(obj, path, *, overwrite=False):
    if not overwrite and Path(path).exists():
        raise FileExistsError(f"{path} exists; pass overwrite=True")
    if not isinstance(obj, _SUPPORTED_TYPES):
        raise TypeError(f"unsupported obj type: {type(obj).__name__}")
```

Reach for:

- `FileNotFoundError`, `FileExistsError`, `PermissionError` — filesystem
- `ValueError` — bad argument value
- `TypeError` — bad argument type
- `KeyError`, `IndexError` — collections
- `RuntimeError` — generic runtime failure with no better fit

These need no SciTeX-specific scaffolding. Users handle them with normal `try/except`.

### Layer 2 — SciTeX `ErrorCode` for structured failures (LLM-facing)

When the failure mode is going to surface to an LLM through MCP or the CLI, use the canonical taxonomy:

```python
# scitex_dev/_errors.py (canonical)
from enum import Enum

class ErrorCode(str, Enum):
    E001_INVALID_INPUT = "E001"
    E002_FILE_NOT_FOUND = "E002"
    E003_PERMISSION_DENIED = "E003"
    E004_DEPENDENCY_MISSING = "E004"
    E005_TIMEOUT = "E005"
    # ... continues per-domain
    E010_GIT_STASH_FAILED = "E010"
```

Downstream usage:

```python
from scitex_dev._errors import ErrorCode, ScitexError

raise ScitexError(
    code=ErrorCode.E004_DEPENDENCY_MISSING,
    message="h5py not installed",
    remediation="pip install scitex-io[h5]",
)
```

The exception serializes to:

```json
{
  "code": "E004",
  "message": "h5py not installed",
  "remediation": "pip install scitex-io[h5]",
  "traceback": "..."
}
```

This is the shape MCP tools return on failure (consumed by Claude / agents) and what `<cli> --json` emits.

## Extending the taxonomy in a downstream package

Downstream packages add domain-specific codes by extending the enum:

```python
# scitex_io/_errors.py
from scitex_dev._errors import ErrorCode

# Reserve E1xx range for scitex-io domain codes
class IOErrorCode(str, Enum):
    E101_UNSUPPORTED_FORMAT = "E101"
    E102_PARTIAL_WRITE = "E102"
```

Conventions:

- E001–E099: ecosystem-wide (defined in scitex-dev)
- E1xx: scitex-io domain
- E2xx: scitex-stats domain
- E3xx: scitex-cloud domain
- ... (assigned in scitex-dev's registry; tracked in [TODO.md](TODO.md))

## When to use which layer

| Scenario                                          | Use            |
|---------------------------------------------------|----------------|
| Bad arg value caught in a Python script           | `ValueError`   |
| Same condition surfaced via MCP tool to an LLM    | `ScitexError(E001_INVALID_INPUT)` |
| Optional dep missing, raised in user code         | `ImportError`  |
| Same condition surfaced through CLI `--json`      | `ScitexError(E004_DEPENDENCY_MISSING)` |
| Internal invariant violation (a bug)              | `AssertionError` (don't catch) |

The boundary is **"does this failure cross a structured-output API surface?"** If yes, structured error. If no, stdlib.

## Don't redefine your own hierarchy

```python
# ❌ Anti-pattern — every package inventing its own
class IOError(Exception): ...
class IOFileError(IOError): ...
class IOFormatError(IOError): ...
```

Drives downstream callers to memorize per-package taxonomies. Use `ErrorCode` strings instead — flat namespace, single registry, machine-parseable.

## Don't catch and re-raise as a different type

```python
# ❌ Anti-pattern — loses the original cause
try:
    import h5py
except ImportError:
    raise RuntimeError("h5py missing")

# ✅ Either let it propagate, or chain explicitly
try:
    import h5py
except ImportError as e:
    raise ScitexError(
        code=ErrorCode.E004_DEPENDENCY_MISSING,
        message="h5py not installed",
        remediation="pip install scitex-io[h5]",
    ) from e
```

`from e` preserves the chain; without it, debugging the original cause is harder.

## Audit

- Every `raise` of a SciTeX exception must use `ScitexError(code=..., ...)`.
- No package-local `class FooError(Exception)` hierarchy parallels to ScitexError.
- Standard lib exceptions used for in-Python failures (`ValueError`, `FileExistsError`) — not wrapped unless they're crossing an MCP/CLI boundary.

Linter rule (planned): **PA-010** — flag custom Exception subclasses in non-`scitex-dev` packages; suggest `ScitexError(code=...)`.
