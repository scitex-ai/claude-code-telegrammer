---
description: |
  [TOPIC] Interface Python Api Lazy Imports
  [DETAILS] Two lazy-import concerns — (1) optional deps via `try_import_optional` so a missing extra never crashes import, and (2) PEP 562 `__getattr__` so heavy required submodules don't slow down `import <pkg>` and CLI startup. Conditional `__all__` rules. The `_LazyModule` class for the umbrella's submodule attribute access. Sentinel pattern for "feature available?" checks.
tags: [scitex-general-interface-python-api-lazy-imports-and-optional-deps]
---

# Lazy Imports and Optional Dependencies

This file covers two related but distinct concerns:

1. **Optional dependencies** (sections below up to "Audit") — handling `pip install pkg[extra]` gates so missing extras don't crash `import pkg`.
2. **PEP 562 startup-time lazy imports** (final section) — making `import pkg` cheap when all required deps ARE installed but submodules transitively load heavy code.

Both are "lazy imports"; they solve different problems and use different mechanisms. Don't conflate them.

## Rule: a missing optional dep never crashes `import <pkg>`

Use the canonical helper from scitex-dev. **Shipped in `scitex_dev._imports`** (re-exported as `from scitex_dev import try_import_optional`). Signature: `try_import_optional(module_path, attr=None, *, extra=None, pkg=None, package=None)` — returns the imported object or `None` on `ImportError` / missing attribute. Failed imports record an `InstallHint` retrievable via `last_install_hint(name)`.

```python
# ✅ Canonical pattern
from scitex_dev import try_import_optional

H5Explorer   = try_import_optional("._h5_explorer",   "H5Explorer",   extra="h5",   pkg="scitex-io")
ZarrExplorer = try_import_optional("._zarr_explorer", "ZarrExplorer", extra="zarr", pkg="scitex-io")
```

Returns the imported object on success, `None` on `ImportError`. Records `(extra, pkg)` so a use-site error message can render `pip install scitex-io[h5]` without each call site hand-spelling it.

The names appear in `__all__` either way (set to `None` if unavailable). User code probes them:

```python
import scitex_io as sio
if sio.H5Explorer is None:
    raise RuntimeError("Install scitex-io[h5] to use H5Explorer")
explorer = sio.H5Explorer(...)
```

### Why a helper instead of inline `try/except`?

- Eliminates the 3-line × N-optional-deps boilerplate in every `__init__.py`.
- Standardizes the install-hint shape — `audit-api` can grep one call signature instead of parsing `try/except` ASTs.
- One place to evolve the behavior (e.g. emit a warning at import time, log to telemetry) without touching every package.
- scitex-dev is a hard runtime dep for every standalone (light: `scitex-config` + `tomli`); the helper is always importable.

### Legacy `try/except` form (still tolerated, not preferred)

```python
# Pre-helper era — still works, drift to migrate
try:
    from ._h5_explorer import H5Explorer
except ImportError:
    H5Explorer = None
```

Migrate when touching the file for other reasons; don't churn just to convert.

## Why `None`-assignment over conditional `__all__`

Two patterns exist in the wild:

| Pattern                                  | Behavior                                                                 |
|------------------------------------------|--------------------------------------------------------------------------|
| **A. `Item = None` + always in `__all__`** ⭐ | `dir()` always shows `H5Explorer`. `hasattr(pkg, "H5Explorer")` is `True`. Users probe with `is None`. |
| B. Conditional `__all__.append("Item")`  | `dir()` hides `H5Explorer` when missing. `hasattr` is `False`. Users probe with `hasattr`.            |

**Canonical: A.** Reasons:

- `dir()` output is stable across installs — easier debugging when comparing two environments.
- The name being a callable check (`is None`) is more discoverable than `hasattr`.
- Linters and IDEs can resolve the name even when the optional dep is missing.

Pattern B exists in some packages — drift to fix.

## Public availability flags

For binary "is this feature available" questions, expose a boolean alongside (opt-in — only when the optional dep gates a major feature surface):

```python
ScholarSession = try_import_optional(
    "._scholar_runtime", "ScholarSession",
    extra="scholar", pkg="scitex-scholar",
)
SCHOLAR_AVAILABLE = ScholarSession is not None

__all__ = ["ScholarSession", "SCHOLAR_AVAILABLE", ...]
```

User code:

```python
import scitex_scholar as ssch
if ssch.SCHOLAR_AVAILABLE:
    ...
```

Use these sparingly — only when the optional dep gates a major feature surface, not a single function.

## What goes in `extras_require`

- `pyproject.toml` declares optional groups: `[project.optional-dependencies]` → `h5 = ["h5py>=3"]`.
- `pip install scitex-io[h5]` installs the group.
- The skill leaf [01_ecosystem/02_dependency-and-version-pinning.md](../../01_ecosystem/02_dependency-and-version-pinning.md) covers extras naming + pinning.

## The umbrella's `_LazyModule`

`scitex/__init__.py` uses `_LazyModule` to expose `scitex.io`, `scitex.stats`, etc. without importing them eagerly:

```python
# scitex/__init__.py (abbreviated)
class _LazyModule:
    def __init__(self, dist_name, import_name):
        self._dist_name = dist_name
        self._import_name = import_name
        self._module = None

    def __getattr__(self, name):
        if self._module is None:
            try:
                self._module = importlib.import_module(self._import_name)
            except ImportError as e:
                raise ImportError(
                    f"Install {self._dist_name} to use scitex.{name}"
                ) from e
        return getattr(self._module, name)

io = _LazyModule("scitex-io", "scitex_io")
stats = _LazyModule("scitex-stats", "scitex_stats")
```

Why:

- `import scitex` stays cheap — no eager load of every standalone.
- Users who only need `scitex.io` don't pay for `scitex.stats` import.
- A missing standalone surfaces a helpful error pointing at the right `pip install`.

Per-package implementations should NOT reinvent `_LazyModule` — the umbrella owns it. Standalones use the simple `try/except ImportError` pattern above.

## Anti-patterns

```python
# ❌ Top-level import of optional dep — crashes whole package
from h5py import File   # ImportError if h5py not installed

# ❌ Importing inside a function silently ignores missing dep
def explore(path):
    import h5py   # NameError surfaces only when explore() is called
    return h5py.File(path)

# ❌ Re-raising as a different error type loses the install hint
try:
    import h5py
except ImportError:
    raise RuntimeError("h5py needed")   # User sees 'RuntimeError', not 'pip install ...'
```

## Audit

- Every `try: from ... except ImportError` that gates a public name → must assign `None`.
- Every conditional public name → must be in `__all__`.
- No top-level `import <optional_dep>` outside a try/except.
- Inline `try/except ImportError: X_AVAILABLE = False` pairs in **src** → migrate to `try_import_optional`. Rule: **PA-302** (planned).
- Unguarded `import <optional-dep>` at module top of a **test** file → wrap in `pytest.importorskip("<optional-dep>")`. Rule: **PA-303** (planned).

### Test-side counterpart of `try_import_optional`

In source: a missing optional dep returns `None` from the helper and
the gate `<NAME>_AVAILABLE = False` lets callers branch. In tests: the
same dep is gated with `pytest.importorskip("<dep>")` at the top of the
test file.

```python
# tests/scitex_io/_load_modules/test__optuna.py
import pytest
optuna = pytest.importorskip("optuna")

from scitex_io._load_modules._optuna import load_yaml_as_an_optuna_dict
```

If the dep is missing, the whole test module is skipped — pytest
collection succeeds, the rest of the suite still runs, and Codecov
sees a complete `coverage.xml`. An unguarded import fails at
collection instead, which aborts every test in the same pytest run
and silently masks the actual state of the package. PA-303 codifies
this requirement.

Linter rule (planned): **PA-007** — flag bare imports of names declared in `extras_require`.

---

## PEP 562 module `__getattr__` for startup-time speed

The patterns above solve "missing optional dep". This section solves a different problem: **even when all required deps are installed, eager submodule imports in `__init__.py` make `import <pkg>` slow.** That cost is paid by every CLI invocation, every shell tab-completion, every quick script.

### Rule

**Top-level `<pkg>/__init__.py` MUST NOT contain `from .X import a, b, c` for heavy submodules.** Public names are exposed via PEP 562 `__getattr__` and loaded on first attribute access.

A "heavy" submodule is anything that transitively imports the `scitex` umbrella, `scitex_config`, `scitex_scholar`, `figrecipe`, `torch`, `numpy`, or any package whose own import takes >50ms in a fresh interpreter.

### Why

Every Click CLI invocation pays the full `import <pkg>` cost — *before any command runs*. Shell tab-completion calls the program once per Tab press. A 9-second `import scitex_dev` made `scitex-dev <Tab>` unusable.

After lazy refactor (scitex-dev 0.10.1):

| Measurement                | Before | After  |
|----------------------------|--------|--------|
| `import scitex_dev`        | 8.4s   | 0.14s  |
| `scitex-dev --help`        | 9.4s   | 0.26s  |
| Tab press in `scitex-dev …`| ~9s    | <0.5s  |

### Pattern

```python
# pkg/__init__.py
from __future__ import annotations

# Cheap things only — no `from .X import Y` for heavy submodules.
from importlib.metadata import PackageNotFoundError, version as _v
try:
    __version__ = _v("pkg")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

# Public-name → source-submodule map. ONE row per public symbol.
_LAZY_ATTRS: dict[str, str] = {
    "wrap_as_cli": "cli_utils",
    "load_config": "config",
    "ECOSYSTEM": "ecosystem",
    # ... add a row each time you'd previously have written `from .X import Y`.
}


def __getattr__(name: str):
    """PEP 562 lazy-loader: import on first access, cache, return."""
    mod_name = _LAZY_ATTRS.get(name)
    if mod_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    attr = getattr(import_module(f".{mod_name}", __name__), name)
    globals()[name] = attr  # cache; subsequent access skips this branch
    return attr


def __dir__() -> list[str]:
    return sorted(set(_LAZY_ATTRS) | set(globals()))


__all__ = list(_LAZY_ATTRS) + ["__version__"]
```

Behavior:

- `from pkg import foo` → triggers `__getattr__("foo")` → imports submodule once, caches.
- `pkg.foo` → same path.
- `dir(pkg)` → reports all lazy names without loading them.
- `import pkg` alone → does NOT load any submodule. **This is the win.**

### Compatibility with `try_import_optional`

The two patterns compose. For an optional submodule (gated by an extra):

```python
# Eager — current pattern from earlier in this file. Costs are bounded by
# what try_import_optional touches, which should be just the import attempt.
H5Explorer = try_import_optional(
    "._h5_explorer", "H5Explorer", extra="h5", pkg="scitex-io"
)
```

`try_import_optional` is for **gating**, not for **deferring**. If the optional submodule is heavy, deferring its import via `__getattr__` is appropriate; if it's light, eager `try_import_optional` is fine.

### What this means for submodules

Submodules can keep eager imports — only the **top-level** `__init__.py` matters for CLI startup. A `pkg.config` module can `import yaml` at the top; what matters is that `import pkg` does not transitively load `pkg.skills` → `pkg.test_runner` → the umbrella.

### Common mistakes

| Anti-pattern                                         | Why it's wrong                                                      |
|------------------------------------------------------|---------------------------------------------------------------------|
| `from .skills import verify_X` at module top         | `skills/` may pull `figrecipe` or umbrella; defer to `_LAZY_ATTRS`. |
| `from .test_runner import run_local` at module top   | `test_runner` likely depends on heavy testing infra.                |
| `import scitex` at module top of any submodule consumed by the CLI | Drags the umbrella into every CLI call. |
| `from .types import Result` at module top ✓          | OK — `types.py` should be a pure-stdlib leaf module.                |

### Audit recipe

```bash
# Should be < 500ms in a fresh interpreter.
python -c "import time; t=time.perf_counter(); import <pkg>; print(f'{(time.perf_counter()-t)*1000:.0f}ms')"

# Or with breakdown of who pulls in what:
python -X importtime -c "import <pkg>" 2>&1 | sort -k2 -nr | head -20
```

If `import <pkg>` cold-start is > 500ms, top-level `__init__.py` is leaking eager imports. Convert them to `_LAZY_ATTRS` rows.

### Auditor

`scitex-dev ecosystem audit-project <pkg>` will flag heavy top-level imports as rule **PA-008** (TBD). The check measures `import <pkg>` cold-start time and fails if > 500ms; remedy points to this section.

### Audited

- `scitex-dev` 0.10.1 — refactored 8.4s → 0.14s. PR #?? (link to follow).
- `scitex` umbrella — already lazy via `_LazyModule` (see "The umbrella's `_LazyModule`" section above). Different mechanism (proxies whole subpackages by name), same intent.
