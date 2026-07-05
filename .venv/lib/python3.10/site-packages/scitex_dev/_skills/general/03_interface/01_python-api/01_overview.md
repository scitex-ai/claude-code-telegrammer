---
description: |
  [TOPIC] Interface Python Api Overview
  [DETAILS] Design principles for every SciTeX package's Python API — minimal public surface, no logic duplication, `__init__.py` as the contract, hide internals behind `_`, decorators applied at import boundary, optional features fail soft.
tags: [scitex-general-interface-python-api-overview]
---

# Overview

## Design principles

1. **`__init__.py` is the contract.** If a name isn't exported there (and listed in `__all__`), it's not part of the public API. Subpath imports (`scitex_io._save.save`) are tolerated but unsupported.
2. **Minimal public surface.** Default to `_`-prefix; promote a name only when a user has a real reason to call it. Smaller surface = easier `dir()`, cleaner tab-completion, less to deprecate.
3. **No logic in `__init__.py`.** Imports, decorator wrapping, and `__all__` only. Implementation lives in `_<name>.py` modules.
4. **No third-party in `__all__`.** Internal use of `numpy`, `pandas`, `torch` is fine and expected — type hints reference them, implementations import them. Source files freely use the underscore-alias pattern (`import numpy as _np`) to keep the alias out of `dir()` while still using the library. The rule is narrow: don't bare-re-export third-party names in **your** `__all__`. `__all__ = ["save", "load"]` not `["save", "load", "ndarray"]`. Users import third-party types directly from their home modules; you don't take ownership of their public surface. *Exception:* a **scitex-owned type** built from third-party building blocks is allowed in `__all__` — it's your conceptual type, even though its members live upstream. The canonical example is `scitex_types.ArrayLike`, a `Union[list, tuple, np.ndarray, pd.Series, pd.DataFrame, xr.DataArray, torch.Tensor]` assembled dynamically based on which optional deps are installed. That's *your* type, broader than `numpy.typing.ArrayLike` (which only covers numpy-coercible inputs). See [02_naming-and-visibility.md](02_naming-and-visibility.md) §"Underscore-alias for third-party imports".
5. **Optional features fail soft via `try_import_optional`.** Use the canonical helper from scitex-dev: `X = try_import_optional("._mod", "X", extra="...", pkg="scitex-io")`. Returns the object or `None`; never crashes import. (See [04_lazy-imports-and-optional-deps.md](04_lazy-imports-and-optional-deps.md).)
6. **Decorators applied at the import boundary.** Wrap with `@supports_return_as` (or similar) in `__init__.py` after import, not inside the implementation file. Keeps the decorator stack visible in one place.

## Canonical `__init__.py` shape

```python
# src/scitex_io/__init__.py
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from scitex_dev import try_import_optional, supports_return_as

try:
    __version__ = version("scitex-io")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

from ._save import save
from ._load import load
from ._load_configs import load_configs
from ._registry import register_saver, register_loader, list_formats
from ._glob import glob, parse_glob

# Optional features — return None when extras are not installed
H5Explorer   = try_import_optional("._h5_explorer",   "H5Explorer",   extra="h5",   pkg="scitex-io")
ZarrExplorer = try_import_optional("._zarr_explorer", "ZarrExplorer", extra="zarr", pkg="scitex-io")

# Cross-cutting decorators applied at the import boundary
save = supports_return_as(save)
load = supports_return_as(load)

__all__ = [
    "__version__",
    "save", 
    "load", 
    "load_configs",
    "register_saver", 
    "register_loader", 
    "list_formats",
    "glob", 
    "parse_glob",
    "H5Explorer", 
    "ZarrExplorer",
]
```

`scitex-dev` is a hard runtime dependency for every standalone (deps: `scitex-config` + `tomli` on Python <3.11 — negligible). It hosts the cross-cutting helpers (`try_import_optional`, `supports_return_as`, `ErrorCode`) so the ecosystem stays consistent.

Each line of this template is justified in one of the sub-skills. If you change one, check the section it came from.

## Sub-skills relationship

```
01_overview.md            (principles + canonical shape — start here)
├── 02_naming...           (which names are public)
├── 03_version...          (the __version__ block)
├── 04_lazy-imports...     (the try/except ImportError block)
├── 05_docstring...        (what each function carries)
├── 06_type-hints...       (annotations on every signature)
├── 07_decorators...       (the @supports_return_as wrap)
├── 08_submodule...        (when to expose `scitex_io.formats` etc.)
├── 09_error-handling...   (what exceptions to raise)
├── 10_introspection...    (CLI parity: list-python-apis)
└── 11_import-conventions  (umbrella vs standalone in user code)
```
