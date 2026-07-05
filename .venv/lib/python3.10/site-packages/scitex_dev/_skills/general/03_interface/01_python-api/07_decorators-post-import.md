---
description: |
  [TOPIC] Interface Python Api Decorators
  [DETAILS] Apply `@supports_return_as` (and similar cross-cutting decorators) at the import boundary in `__init__.py`, not inside the implementation file. Recommended-where-applicable, not required — leaf packages without scitex-dev dep can skip. Conditional application via try/except. Preserves single decorator-stack inspection point.
tags: [scitex-general-interface-python-api-decorators-post-import]
---

# Decorators (Post-Import Application)

## The pattern

```python
# scitex_io/__init__.py
from scitex_dev import supports_return_as

from ._save import save
from ._load import load
from ._load_configs import load_configs

# Apply cross-cutting decorators at the import boundary
save = supports_return_as(save)
load = supports_return_as(load)
load_configs = supports_return_as(load_configs)
```

Wrap **after** `from ._save import save`, not inside `_save.py` itself.

scitex-dev is a hard runtime dep for every SciTeX standalone (deps: `scitex-config` + conditional `tomli` — negligible), so no `try/except ImportError` guard is needed around the import.

## Why post-import, not in the implementation file

1. **One inspection point.** A reader opens `__init__.py` and sees the full decorator stack for every public function in one place. No need to grep across `_save.py`, `_load.py`, ... .
2. **Conditional application.** The decorator depends on `scitex-dev`. If the standalone package is installed alone (no scitex-dev), the bare implementation still works — wrapping inside `_save.py` would force `scitex-dev` as a hard dep.
3. **Easy to audit.** `scitex-dev introspect api <pkg>` can list which functions are wrapped — straightforward when the wrapping is in `__init__.py`.
4. **Easy to disable.** A test or debug session can re-bind `save = save.__wrapped__` if needed; no monkey-patching across modules.

## `@supports_return_as` — what it does

Adds a `return_as` keyword to a function so callers (especially LLM agents and the MCP layer) can pick the response shape:

```python
# Without decorator — function returns native Python:
result = scitex_stats.run_test(g1, g2)   # dataclass or dict

# With decorator — caller picks shape:
result = scitex_stats.run_test(g1, g2, return_as="dataframe")  # pd.DataFrame
result = scitex_stats.run_test(g1, g2, return_as="json")       # str (JSON)
result = scitex_stats.run_test(g1, g2, return_as="latex")      # str (LaTeX)
```

Stable across scitex-io and scitex-stats today. **Recommended** where return-type polymorphism is genuinely useful (test results, structured data); **not required** where it isn't (`load_configs` returns a `DotDict` and that's the obvious shape).

## When to apply, when to skip

| Function class                         | Apply `@supports_return_as`?       |
|----------------------------------------|------------------------------------|
| Statistical test results               | ✅ yes (`dataframe`, `dict`, `latex`)  |
| File I/O (`save`, `load`)              | ✅ yes (return path-as-str vs Path)    |
| Configuration loading                  | optional                            |
| Pure compute returning array           | ❌ skip (return type is fixed)         |
| Side-effect functions returning None   | ❌ skip                                |

## When you genuinely don't want the decorator

The decorator is **recommended-where-applicable**, not mandatory. For functions where return-type polymorphism doesn't make sense (pure compute, side-effect-only, fixed return type), just skip the wrap:

```python
from ._compute import process    # not wrapped — fixed return type
__all__ = ["process"]
```

scitex-dev is still imported elsewhere in the file (for `try_import_optional` and similar) so there's no dependency cost to leaving some functions unwrapped.

## Anti-patterns

```python
# ❌ Decorating in the implementation file
# _save.py
from scitex_dev import supports_return_as

@supports_return_as
def save(obj, path):
    ...
```

Forces `scitex-dev` as a hard dep. Hides the decoration in a non-obvious file.

(historical) Earlier ecosystem versions wrapped the decorator import in `try/except ImportError` because scitex-dev was optional. As of the convention here, scitex-dev is a hard runtime dep, so the bare `from scitex_dev import supports_return_as` is canonical. If you find old try/except wrapping in a package, migrate it.

```python
# ❌ Conditional inside the implementation
# _save.py
def save(obj, path, return_as=None):
    if return_as == "json": ...
    elif return_as == "dict": ...
    ...
```

Reinventing the decorator inline. Loses the single inspection point and the consistent return_as semantics.

## Audit

```bash
python -c "import scitex_io; help(scitex_io.save)"
# Look for: 'supports_return_as' in __wrapped__ chain.
# Failure: bare function without the decorator (when applicable).
```
