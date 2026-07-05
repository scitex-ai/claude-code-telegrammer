---
description: |
  [TOPIC] Interface Python Api
  [DETAILS] Python API design rules for every SciTeX package — minimal public surface (`_` prefix + `__all__`), `importlib.metadata` version strategy, lazy imports for optional deps, NumPy-style docstrings, `from __future__ import annotations`, optional `@supports_return_as` decorator, scitex-dev-canonical error handling, standalone-vs-umbrella import conventions, and the `list-python-apis -v|-vv|-vvv` introspection ladder. Use when designing a new package's public API, reviewing PRs that touch `__init__.py`, or auditing an existing package before release.
tags: [scitex-general-interface-python-api-index]
---

# Python API (SciTeX) — Index

The Python API is the **single source of truth**. CLI, MCP, and HTTP all delegate to it
([general/03_interface/00_overview.md](../00_overview.md)).

## Sections

1. [01_overview.md](01_overview.md) — design principles, the canonical `__init__.py` shape
2. [02_naming-and-visibility.md](02_naming-and-visibility.md) — `_` prefix, `__all__` discipline, no third-party re-export
3. [03_version-strategy.md](03_version-strategy.md) — `importlib.metadata` canonical pattern
4. [04_lazy-imports-and-optional-deps.md](04_lazy-imports-and-optional-deps.md) — try/except ImportError, conditional `__all__`, `_LazyModule`
5. [05_docstring-standards.md](05_docstring-standards.md) — NumPy style, module vs function
6. [06_type-hints.md](06_type-hints.md) — `from __future__ import annotations`, Union/Literal/Optional
7. [07_decorators-post-import.md](07_decorators-post-import.md) — `@supports_return_as` (recommended-where-applicable)
8. [08_submodule-exposure.md](08_submodule-exposure.md) — when to expose a submodule vs hide it (research deferred)
9. [09_error-handling.md](09_error-handling.md) — `scitex_dev._errors.ErrorCode` as canonical
10. [10_introspection-commands.md](10_introspection-commands.md) — `list-python-apis -v|-vv|-vvv` + `--json`
11. [11_import-conventions.md](11_import-conventions.md) — standalone vs umbrella; `import scitex` not `as stx`
12. [12_audit-checklist.md](12_audit-checklist.md) — release-gate checklist
13. [13_imports-and-shadowing.md](13_imports-and-shadowing.md) — stdlib vs `scitex.os` / `scitex.io` resolution, aliasing rules
14. [14_numeric-literals.md](14_numeric-literals.md) — `_` thousands separators for literals ≥ 1_000 (`21_600`, not `21600`); PEP 515
15. [TODO.md](TODO.md) — open conversion items, audit-api linter design
