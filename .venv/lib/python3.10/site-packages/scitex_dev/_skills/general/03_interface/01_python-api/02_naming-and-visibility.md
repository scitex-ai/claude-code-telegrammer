---
description: |
  [TOPIC] Interface Python Api Naming
  [DETAILS] Underscore-prefix rule for private modules, `__all__` discipline (only public names listed), no re-export of third-party symbols, naming conventions for public functions vs private helpers.
tags: [scitex-general-interface-python-api-naming-and-visibility]
---

# Naming and Visibility

## Underscore prefix is the visibility primitive

Every implementation file is **`_<name>.py`**. Public functions are imported into `__init__.py` from these private modules.

```text
src/scitex_io/
├── __init__.py        ← exports the public API
├── _save.py           ← implementation (private)
├── _load.py           ← implementation (private)
└── _registry.py       ← implementation (private)
```

Why:

- `dir(scitex_io)` returns a clean list — no `_save`, `_load`, `_registry` clutter.
- Interactive tab-completion shows only what users should call.
- Renaming a private module is a non-breaking change (no public callers by definition).
- Sphinx autodoc skips `_`-prefixed members by default — docs stay focused on the public surface.

## `__all__` is mandatory and exhaustive

Every `__init__.py` declares `__all__`. **Every public name appears in `__all__`. Nothing else does.**

```python
__all__ = [
    "__version__",
    "save", 
    "load", 
    "load_configs",
    "register_saver", 
    "register_loader", 
    "list_formats",
]
```

Rules:

- Include `__version__` if you expose it (you should).
- Order: dunders first, then alphabetical *or* logical clusters (e.g. all I/O verbs together). Either is fine — pick one and stick with it.
- Do **not** include private helpers, even if some downstream code imports them. If they need to be public, drop the `_` prefix and add to `__all__`.
- Do **not** include third-party symbols (`numpy`, `pandas`). Users import those directly.

## No re-export of third-party symbols

```python
# ❌ Don't
from numpy import ndarray
__all__ = ["ndarray", ...]

# ✅ Do
# Let users import numpy themselves; document type hints with ndarray in signatures.
```

Why: re-exporting third-party types couples your package's public surface to an upstream's release schedule. When `numpy` deprecates `ndarray`, your downstream users get the warning even if they never wrote `numpy` themselves.

## Public function naming

- **Verb-first for actions**: `save`, `load`, `register_saver`, `enrich_bibtex`. Read as imperatives.
- **Noun-only for queries that return data**: `list_formats()` is borderline — `formats` (a property) would also work, but the function form is clearer about the side effect of enumeration.
- **No `get_` prefix**: `get_version()` is anti-pattern; use `version` or `__version__`. `get_X` reads as a Java-ism in Python.
- **No type in name**: `save_dataframe()` is wrong; dispatch on input type. `save(df)` and `save(arr)` should both work.
- **Lowercase + underscore**: `load_configs`, never `loadConfigs` or `LoadConfigs`.

## Class naming

- **CapWords** as PEP 8 mandates: `RecordingFigure`, `PathManager`, `DotDict`.
- Public classes go in `__all__` like functions.
- Private classes stay in `_<name>.py` and are not re-exported.

## Underscore-alias for third-party imports (`import numpy as _np`)

Within a module, you can prefix an alias with `_` to keep the imported name out of `dir()` and out of `from <mod> import *` star-imports:

```python
import numpy as _np
import pandas as _pd
```

Two flavours of guidance:

- **In implementation files (`_save.py`, `_load.py`, ...): use the standard alias** (`as np`, `as pd`). The file itself is `_`-prefixed and never re-exported; nothing leaks. `np.array(...)` reads more naturally than `_np.array(...)` for anyone fluent in scientific Python.
- **In `__init__.py`: prefer `as _np` if you must import numpy/pandas at all.** Per rule #3, `__init__.py` shouldn't carry logic; the rare exception is a module-level type alias or a constant computed from a third-party value. In that case, the underscore alias keeps the name out of `dir(scitex_io)` so users don't mistake `numpy` for part of the package's surface.

```python
# __init__.py — only if genuinely needed
import numpy as _np
import pandas as _pd
import xarray as _xr
# Build a scitex-owned type from third-party building blocks.
# Canonical example: scitex_types.ArrayLike (wider than numpy.typing.ArrayLike).
ArrayLike = Union[list, tuple, _np.ndarray, _pd.Series, _pd.DataFrame, _xr.DataArray]
__all__ = ["ArrayLike", ...]   # the underscore aliases themselves are NOT exported
```

The point: `_np`, `_pd`, `_xr` are private to the module (their `_` prefix keeps them out of `dir()` and out of `__all__`), but the **scitex-owned type** built from them — `ArrayLike` — *is* part of the public surface. That's not "third-party re-export" because the type is genuinely yours; users importing `from scitex_types import ArrayLike` get a richer union than `numpy.typing.ArrayLike` would give them.

This is a soft preference, not a lint rule — `import numpy as np` in `__init__.py` is also accepted when no leakage concern exists.

## Constants

- **UPPER_CASE** for module-level constants: `DEFAULT_TIMEOUT`, `SUPPORTED_FORMATS`.
- Goes in `__all__` if part of the public API.
- Convention: configuration loaded via `stx.io.load_configs()` is bound to an UPPER_CASE name (`CONFIG`) — see linter rule **S007**.

## Audit

```bash
scitex-dev introspect api scitex_io        # lists __all__ contents
scitex-dev introspect api scitex_io --strict  # warn on names not in __all__ but reachable
```

Failure modes (linter-checkable):

- Public name (no `_`) imported into `__init__.py` but missing from `__all__` → S00x (planned).
- `__all__` entry that doesn't resolve to an imported name → typo / dead entry.
- Third-party name in `__all__` → re-export anti-pattern.
