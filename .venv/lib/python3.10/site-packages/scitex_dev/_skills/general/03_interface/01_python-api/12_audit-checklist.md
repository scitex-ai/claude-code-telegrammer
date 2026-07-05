---
description: |
  [TOPIC] Interface Python Api Audit Checklist
  [DETAILS] Release-gate checklist for a package's Python API. Run before tagging a release. Mirrors the structure of the CLI and MCP audit checklists. (A) markers indicate items the planned `audit-api` linter will automate.
tags: [scitex-general-interface-python-api-audit-checklist]
---

# Python API Audit Checklist

Run before tagging a release. Tick each item or document the deviation in the PR.

`(A)` = automated by **`scitex-dev ecosystem audit-python-apis <distribution>`** (shipped — parallels `ecosystem audit-cli`, `ecosystem audit-mcp-tools`; mirrors the `list-python-apis` introspection command).

**Shipped rules** (rule code → checklist item): PA-101 (§1 `__all__` present), PA-102 (§1 every name bound), PA-103 (§1 no `_`-prefixed in `__all__`), PA-104 (§1 no third-party re-export), PA-201 (§2 `__version__` in `__all__`), PA-202 (§2 `importlib.metadata.version()` pattern), PA-203 (§2 `"0.0.0+local"` fallback), PA-301 (§3 top-level optional import flagged unless wrapped), PA-501 (§5 `from __future__ import annotations`). Run with `--json` for machine-readable output, `--rule PA-101 --rule PA-202 ...` to scope. See [TODO.md](TODO.md) for deferred rules.

## §1 — Naming and visibility

- [ ] (A) `__all__` is present in `__init__.py`.
- [ ] (A) Every name in `__all__` is imported into `__init__.py`.
- [ ] (A) No name in `__all__` starts with `_`.
- [ ] (A) Every public name (no `_` prefix, imported) is in `__all__`.
- [ ] (A) No third-party symbol (`numpy.ndarray`, `pandas.DataFrame`) is in `__all__`.
- [ ] All implementation files are `_<name>.py`.

## §2 — Version strategy

- [ ] (A) `__version__` is in `__all__`.
- [ ] (A) `__version__` is computed from `importlib.metadata.version("<dist-name>")`.
- [ ] (A) Fallback is `"0.0.0+local"` (PEP 440 local segment), not `"unknown"`.
- [ ] No `_get_version()` function reading `pyproject.toml` directly.

## §3 — Lazy imports / optional deps

- [ ] (A) Every optional import is wrapped in `try: ... except ImportError: X = None`.
- [ ] (A) `None`-assigned names still appear in `__all__`.
- [ ] No top-level `import <optional-dep>` outside try/except.
- [ ] If a feature surface has a flag, it's named `<FEATURE>_AVAILABLE` and is `True`/`False` (not `None`/object).
- [ ] (A-planned, **PA-302**) Inline `try/except ImportError` pairs assigning `<NAME>_AVAILABLE` migrate to `scitex_dev.try_import_optional(...)`. The helper records `(extra, pkg)` so `last_install_hint(name)` can render `pip install <pkg>[<extra>]` at error sites.
- [ ] (A-planned, **PA-303**) Test files MUST wrap module-top imports of optional third-party deps in `pytest.importorskip(...)`. An unguarded `import <dep>` at the top of a test file fails at collection if the dep is absent, aborting ALL tests in the run and silently masking real failures (incident 2026-05-11: scitex-io stuck at 79 % on Codecov for weeks because `import optuna` blocked collection).

## §4 — Docstrings

- [ ] (A) Every `__all__` member has a non-empty docstring.
- [ ] (A) Every multi-arg public function has a `Parameters` block in NumPy style.
- [ ] (A) Every function with a non-`None` return has a `Returns` block.
- [ ] Top-traffic functions (`save`, `load`, `run_test`, ...) have an `Examples` block.
- [ ] Every implementation file has a module docstring with `Functionalities / IO / Dependencies` sections.
- [ ] Top-level `__init__.py` has a "Quick Start" + "Submodules" docstring.

## §5 — Type hints

- [ ] (A) `from __future__ import annotations` at the top of every `.py` file.
- [ ] (A) Every parameter on every `__all__` member has a type annotation.
- [ ] (A) Every `__all__` member has a return type annotation.
- [ ] Fixed-set string params use `Literal[...]` rather than free-form `str`.
- [ ] `mypy --strict` passes (or documented exclusions are minimal).

## §6 — Decorators

- [ ] If applicable, `@supports_return_as` is wrapped in `__init__.py`, not in the implementation file.
- [ ] The wrapping is inside a `try: from scitex_dev import ...; except ImportError: pass` block.

## §7 — Submodule exposure

- [ ] Every exposed submodule is listed in `__all__`.
- [ ] No `_`-prefixed module is re-exported.
- [ ] Each exposed submodule has its own `__all__`.

## §8 — Error handling

- [ ] No package-local `class FooError(Exception)` hierarchy parallel to `ScitexError`.
- [ ] Failures crossing MCP/CLI boundaries use `ScitexError(code=ErrorCode.Exxx, ...)`.
- [ ] Re-raises preserve cause via `raise ... from e`.

## §9 — Introspection

- [ ] `<cli> list-python-apis` exists.
- [ ] (A) Bare, `-v`, `-vv`, `-vvv` levels behave per spec.
- [ ] (A) `--json` flag emits a parseable list.
- [ ] (A) Output count matches `len(<pkg>.__all__)`.
- [ ] **JSON content parity**: every field shown in `-vvv` text appears in `--json` output (or a strict superset). The `--json` path must not fork the fetcher to a smaller payload — fetch the rich shape unconditionally, render differently. See [03_interface/02_cli/08_universal-flags.md](../02_cli/08_universal-flags.md) for the cross-interface principle.

## §10 — Import conventions in docs

- [ ] Skill and README show both standalone (`import scitex_<pkg>`) and umbrella (`import scitex.<pkg>`) forms.
- [ ] No `as stx` in shipped docs.
- [ ] Inside the package's own source, only the standalone form (`from scitex_io import ...`) is used.

## §11 — Imports and shadowing

- [ ] Bare `import os`, `import io`, `import logging`, etc. always refer to stdlib.
- [ ] Relative imports (`from . import ...`) used only for package-local navigation.
- [ ] No `from scitex import os as os` (or any stdlib-name → stdlib-name alias of a scitex submodule).
- [ ] No `import os as scitex_os` (or any stdlib → scitex-named alias).
- [ ] If the package shadows a stdlib name, README documents the side-by-side alias pattern.
- [ ] (A) `importlib.import_module` only used for genuinely-dynamic imports (computed names, reload).

## §12 — Cross-interface parity

- [ ] CLI `audit-cli` passes for this package.
- [ ] MCP `audit-mcp-tools` passes for this package (when shipped).
- [ ] Names exposed via Python API map cleanly to CLI subcommands and MCP tools (no orphans either way).

## Drift fixes (this skill — open at last audit)

- [ ] scitex-cloud: replace custom `_get_version()` with `importlib.metadata.version()`.
- [ ] (Other): see [TODO.md](TODO.md).
