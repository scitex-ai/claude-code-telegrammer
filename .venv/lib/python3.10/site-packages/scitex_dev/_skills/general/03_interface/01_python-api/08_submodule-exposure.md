---
description: |
  [TOPIC] Interface Python Api Submodule Exposure
  [DETAILS] When to expose a submodule (e.g. `scitex_stats.tests`, `scitex_io.formats`) versus keeping it private (`_utils`). Heuristics, not strict rules — the answer depends on whether users address the submodule by name in their code. Research deferred — convention crystallizing.
tags: [scitex-general-interface-python-api-submodule-exposure]
---

# Submodule Exposure

> **Status:** convention crystallizing. Patterns vary across the ecosystem. This file documents the heuristic; the canonical rule will firm up after a second pass.

## The question

When does a package's `__init__.py` re-export a submodule alongside individual functions?

```python
# Pattern A: only flat functions (scitex-io)
from ._save import save
from ._load import load
__all__ = ["save", "load"]

# Pattern B: also expose submodule (scitex-stats)
from . import tests, descriptive, auto
from ._run_test import run_test
__all__ = ["run_test", "tests", "descriptive", "auto"]
```

## Heuristic: expose when users address by name

Expose the submodule when user code wants to write:

```python
import scitex_stats as sst
sst.tests.t_test_paired(g1, g2)
sst.descriptive.summary(df)
```

…rather than only:

```python
from scitex_stats import t_test_paired   # flat
```

Indicators that exposure is justified:

- The submodule has **its own coherent identity** — `tests` is "all statistical tests", `descriptive` is "all descriptives". Users learn the namespace once, then tab-complete inside it.
- The flat function count would be **overwhelming** — scitex-stats has ~25 tests; flattening puts 25 names in `dir(sst)`.
- The submodule has **its own docs page** in Sphinx, separate from the package overview.

## Heuristic: hide when it's an implementation detail

Keep `_`-prefixed when:

- Users never need to address the submodule by name.
- The contents are helper functions assembled elsewhere into the public API.
- The internal organization is likely to change (`_utils.py` is a graveyard for "stuff").

```python
# scitex_io/_utils.py — private, no re-export
def _normalize_path(p): ...
def _detect_extension(p): ...
```

## Pattern in practice (current ecosystem)

| Package         | Submodules exposed                                     | Notes                                          |
|-----------------|--------------------------------------------------------|------------------------------------------------|
| scitex-io       | (none — flat)                                          | ~10 verbs, all flat                            |
| scitex-stats    | `tests`, `descriptive`, `auto`, `correct`              | ~25 tests + helpers; submodules earn weight    |
| scitex-dev      | `rename`, `ecosystem`, `mcp_docs`                      | Each subdomain has its own CLI noun, mirrors   |
| scitex-cloud    | flat                                                   | Mostly thin wrappers over HTTP                 |
| figrecipe       | `colors`, `units`, `presets`                           | Each has a coherent identity                   |
| scitex-scholar  | flat                                                   | Single-purpose package                         |

No hard rule — package author picks based on the heuristic above.

## When you do expose

```python
# scitex_stats/__init__.py
from . import tests
from . import descriptive
from . import auto

__all__ = [
    # Flat functions
    "run_test", "describe",
    # Submodules (also part of the contract)
    "tests", "descriptive", "auto",
]
```

The submodules go in `__all__` like any other public name.

## Anti-patterns

```python
# ❌ Exposing _-prefixed module
from . import _utils   # NEVER — promotes a private name to public
__all__ = ["_utils"]

# ❌ Exposing without listing in __all__
from . import tests   # imported but not in __all__
__all__ = ["run_test"]   # users find tests via dir() — inconsistent contract
```

## Deferred

- Should every "category" submodule (tests, descriptive, ...) carry its own `__all__`? Probably yes for the same reasons; tracked in [TODO.md](TODO.md).
- Whether to standardize a fixed set of submodule names across packages (e.g. `tests`, `helpers`, `formats`) — currently each package picks its own.
