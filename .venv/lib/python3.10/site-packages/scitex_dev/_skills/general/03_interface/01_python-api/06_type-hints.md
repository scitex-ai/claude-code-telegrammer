---
description: |
  [TOPIC] Interface Python Api Type Hints
  [DETAILS] `from __future__ import annotations` mandatory at top of every module. Type-hint every public function parameter and return. Use Union/Literal/Optional from typing; avoid bare Any unless genuinely polymorphic. Match docstring types with annotations — single source of truth.
tags: [scitex-general-interface-python-api-type-hints]
---

# Type Hints

## `from __future__ import annotations` — top of every `.py` file

```python
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Literal, Union, Optional
```

Why:

- All annotations become strings at runtime — no eager evaluation, no circular import grief.
- Forward references work without quoting: `def f(x: MyClass) -> MyClass` where `MyClass` is defined later.
- PEP 604 `int | str` syntax works on Python 3.9 even though the runtime would otherwise reject it.
- Standard since PEP 563 (2018); will eventually be the default. Adopting now is forward-compatible.

## Annotate every public parameter and return

```python
def save(
    obj: Any,
    path: Union[str, Path],
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> Path:
    ...
```

Rules:

- Every parameter — including `self` is fine to skip but child classes' new params get hints.
- Every return — including `None` (use `-> None` explicitly).
- Keyword-only flags (`*, dry_run`) get hints like positional ones.

## Type vocabulary

| Use                          | Pattern                                  |
|------------------------------|------------------------------------------|
| Path-like input              | `Union[str, Path]`                       |
| Optional value               | `Optional[X]` (= `Union[X, None]`)       |
| String enum                  | `Literal["dataframe", "json", "latex"]`  |
| Mapping with known keys      | `dict[str, Any]` or `TypedDict`          |
| Numeric (any)                | `float` (covers int via subtyping)       |
| Numpy array                  | `np.ndarray`                             |
| Pandas DataFrame             | `pd.DataFrame`                           |
| Truly unconstrained          | `Any` — last resort                      |

`Literal` is preferred over free-form `str` when the function accepts a fixed set:

```python
def run_test(
    data,
    test: Literal["t-test", "anova", "wilcoxon", "mann-whitney"],
    return_as: Literal["dataframe", "dict", "latex"] = "dataframe",
) -> pd.DataFrame | dict | str:
    ...
```

LLM agents construct calls more reliably when `Literal` enumerates the valid strings.

## `Any` is allowed but flagged

```python
def save(obj: Any, path: Union[str, Path]) -> Path:
    """Save a Python object — dispatches on type."""
```

Genuinely polymorphic functions (`save`, `load`, `register`) take `Any`. Document the supported types in the docstring `Parameters` section even when the annotation can't capture them.

## Annotation/docstring agreement

The annotation and the docstring `Parameters` block must agree:

```python
def save(
    obj: Any,
    path: Union[str, Path],
) -> Path:
    """
    Parameters
    ----------
    obj : Any
        ...
    path : str or pathlib.Path
        ...

    Returns
    -------
    pathlib.Path
        ...
    """
```

Drift between annotation and docstring is a maintenance trap. When changing one, update the other in the same commit.

## Class attributes and dataclasses

```python
from dataclasses import dataclass

@dataclass
class RenameConfig:
    old: str
    new: str
    summary_only: bool = False
    auto_stash: bool = False
```

Dataclass field types become both runtime annotations and docstring sources for `help(RenameConfig)`. Prefer dataclasses over `__init__`-with-kwargs for plain config objects.

## Why this matters

- **IDE / LSP support**: hover-tips, jump-to-def, parameter completion all key on annotations.
- **mypy / pyright** can statically check downstream code that consumes your API.
- **MCP tool schemas** are auto-derived from annotations (FastMCP reads them) — un-typed params surface as `Any` and lose their `Literal` guards.
- **LLM call-construction**: structured types (`Literal`, `Optional`) constrain argument generation, reducing wrong-call retries.

## Audit

```bash
mypy --strict src/scitex_io
pyright src/scitex_io
```

Linter rule (planned): **PA-009** — every public function (in `__all__`) must have annotations on all parameters and a return type.
