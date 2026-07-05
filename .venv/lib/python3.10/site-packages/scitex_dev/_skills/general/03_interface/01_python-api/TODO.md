---
description: |
  [TOPIC] Todo
  [DETAILS] Python API skill — open TODOs — see file body for details.
tags: [scitex-general-interface-python-api-TODO]
---

<!-- ---
!-- Timestamp: 2026-04-30 15:30:00
!-- Author: ywatanabe
!-- File: /home/ywatanabe/proj/scitex-python/src/scitex/_skills/general/03_interface/01_python-api/TODO.md
!-- --- -->

# Python API skill — open TODOs

Strike (`~~item~~`) when done. Foundations shipped in scitex-dev `feat-python-api-auditor` are listed once at top, not repeated per-section.

## Shipped foundations (scitex-dev)

- `from scitex_dev import try_import_optional, last_install_hint, InstallHint` — optional-import helper.
- `from scitex_dev import ScitexError, ErrorCode, classify_exception` — canonical structured exception.
- `scitex-dev ecosystem audit-python-apis <dist> [--json] [--rule PA-101 …]` — auditor with 9 rules: PA-101–104 (§1), PA-201–203 (§2), PA-301 (§3), PA-501 (§5). Mirrors `list-python-apis`; sits next to `audit-cli` and `audit-mcp-tools` under `ecosystem`.

## Drift to fix in existing packages

- [ ] **scitex-cloud**: replace custom `_get_version()` with `importlib.metadata.version("scitex-cloud")`.
- [ ] Audit Pattern B (conditional `__all__.append`) — likely scitex-stats, figrecipe.
- [ ] Submodule `__all__` — every exposed submodule should declare its own.
- [ ] `@supports_return_as` placement — must be in `__init__.py`, not `_<name>.py`.
- [ ] Migrate inline `try/except ImportError` to `try_import_optional` across standalones. Rule code reserved: **PA-302** (impl deferred — auditor `_audit.py` needs split before adding; pattern: AST `Try` node whose `body` contains a non-stdlib `Import`/`ImportFrom` plus an assignment `<NAME>_AVAILABLE = True` and whose `ImportError` handler assigns `<NAME>_AVAILABLE = False`). Progress: scitex-io `_load_modules/_optuna.py` + `_save_modules/_optuna_study_as_csv_and_pngs.py` migrated 2026-05-11; 8 sibling packages migrated 2026-05-11 (scitex-io, writer, agent-container, audio, scholar, python, dev, dsp).
- [ ] **PA-303** — Test files MUST wrap module-top imports of optional third-party deps in `pytest.importorskip(...)`. Pattern: AST scan under `tests/` for `Import`/`ImportFrom` at module scope where the imported root is NOT in `[project] dependencies` AND no preceding `pytest.importorskip("<dep>")` exists. Why: an unguarded import that fails at collection aborts ALL tests in the run, masking everything else; coverage upload is then skipped, and Codecov shows a stale or missing number. Real-world incident: scitex-io was stuck at 79% on Codecov for weeks because `import optuna` in two test modules silently blocked test collection.
- [ ] Drop `try/except ImportError: pass` around `from scitex_dev import …` — scitex-dev is hard dep now.
- [ ] **scitex-io**: 15+ bare `except:` blocks (`_load_modules/_catboost.py`, `_H5Explorer.py`, `_glob.py`, `_save_modules/_{hdf5,csv,image,excel,zarr}.py`).
- [ ] **scitex-cloud**: 15+ per-service custom Exception classes — collapse to `ScitexError(code=…)`.

## Ecosystem-wide

- [ ] Make scitex-dev a hard runtime dep for every standalone (`pyproject.toml dependencies`).
- [ ] Reserve E1xx/E2xx/E3xx ErrorCode ranges per package; document in scitex-dev skill.
- [ ] Document warning channel: `warnings.warn(..., UserWarning, stacklevel=2)` for soft notices, `logger.warning(...)` for telemetry, never `print()` in library code (CLI/examples exempt).

## Umbrella migration (separate branch)

- [ ] Decommission `scitex.errors` deprecation shim (currently → `scitex_logging._errors.SciTeXError`); repoint to `scitex_dev.errors`.
- [ ] Re-export `ScitexError` + `ErrorCode` from `scitex/__init__.py`.
- [ ] Delete `scitex_logging/_errors.py` (26-class hierarchy: `SciTeXError`, `ConfigurationError`, `IOError`, `SaveError`, `LoadError`, `ScholarError`, `SearchError`, `PlottingError`, `DataError`, `ShapeError`, `PathError`, `TemplateError`, `NNError`, `StatsError`, …) after porting callers.
- [ ] Audit case-sensitive `SciTeXError` → `ScitexError` callers.

## `audit-api` — deferred rules

- [ ] Registry cascade (`--registry`, `$SCITEX_DEV_REGISTRY`, project/user/bundled YAML) — copy from `_cli_audit`.
- [ ] `--all` / `--exclude` / `--severity` / `--timeout` flags + `RULE_SEVERITY` table.
- [ ] **§4** docstring grammar (numpydoc parser; warn-only first).
- [ ] Behavioral probe — run `<cli> list-python-apis --json`, compare to `<pkg>.__all__`, spot-call `inspect.signature(obj)`.
- [ ] **§6** decorator placement (cross-file AST scan).
- [ ] **§7** submodule `__all__` declarations.
- [ ] **§9** introspection ladder (`-v|-vv|-vvv` exists + behaves per spec).
- [ ] **§11** PA-1101 — stdlib-name aliasing (`import os as scitex_os`).
- [ ] **§12** cross-interface parity — separate `audit-ecosystem` command vs. inlined.
- [ ] PA-502+ `Any` tolerance with `# audit: polymorphic` suppression marker.
- [ ] PA-901–904 (§9 errors): custom Exception subclasses outside scitex-dev; bare `except:`; `raise … as e` without `from e`; `print(...)` at library scope.

## scitex-dev follow-ups

- [ ] `scitex_dev.introspect.api.render(items, verbosity, as_json)` — helper referenced in §10 for `<pkg> list-python-apis` parity, not yet shipped.
- [ ] `is_available(name)` sugar — defer until ≥3 packages need it.
- [ ] Promote `_LazyModule` → `scitex_dev._lazy_module.LazyModule` — defer (1 consumer; doc says "umbrella owns it").

## Reference example

- [ ] Auto-generate canonical `__init__.py` reference shape (parallels CLI's `16_example.md`). Source: `~/proj/scitex-io/src/scitex_io/__init__.py`.

## Open design questions

- [ ] `__all__` ordering — alphabetical vs logical clusters; pick one for new packages.
- [ ] `__version__` as `version()` function form too?
- [ ] `inspect.signature(obj)` failure on `None`-due-to-missing-extra: warning, error, or silent skip?

## From user

- [ ] Can scitex-python be written more cleanly without per-submodule directories for re-exporting?
- [ ] Same question for MCP.
- [ ] Same question for CLI commands.
