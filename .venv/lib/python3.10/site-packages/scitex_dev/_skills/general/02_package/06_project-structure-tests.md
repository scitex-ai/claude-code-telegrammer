---
description: |
  [TOPIC] Package Tests
  [DETAILS] `./tests/` for a SciTeX package — pytest-driven, controlled by `pyproject.toml`. The mandatory `tests/<pkg>/` parent (1:1 mirror of `src/<pkg>/`), allowed sibling subdirs (scripts/examples/skills/agentic/integration/e2e/github_actions/coverage/results/logs/reports/custom), public/private filename convention with double-underscore for private (`test__foo.py` mirrors `_foo.py`), the small set of "meta tests" allowed at `tests/` root, the `audit-project` rules (PS-201–PS-206, PS-302), and the historical `sync_tests_with_source.sh` precedent. Drop the source-as-comments pattern — it's noise.
tags: [scitex-general-package-project-structure-tests]
---

# `./tests` — pytest-driven, mirrors `./src`

> Sibling leaves: [`./root`](01_project-structure-root.md) · [`./src`](02_project-structure-src.md) · [`./scripts`](03_project-structure-scripts.md) · [`./scripts/makefile`](04_project-structure-makefile.md) · [`./examples`](05_project-structure-examples.md)

## Mandatory `tests/<pkg>/` parent

Every package has a `tests/<pkg>/` parent that mirrors `src/<pkg>/` 1:1. **Even when most tests are flat-by-submodule, the `<pkg>` parent must exist.** Audit rule: `PS-201`.

```
src/<pkg>/                          tests/<pkg>/
├── __init__.py                     ├── test___init__.py        (only if needed)
├── foo.py                          ├── test_foo.py             (public → single _)
├── _bar.py                         ├── test__bar.py            (private → double __)
├── _Baz.py                         ├── test__Baz.py            (PascalCase preserved)
└── sub/                            └── sub/
    ├── __init__.py                     ├── test_X.py
    ├── X.py                            └── test__Y.py
    └── _Y.py
```

## Public / private filename convention

A leading underscore in the source marks the module **private**. The mirroring test uses **double underscore** between `test` and the basename to echo the source's leading `_` — making the public/private status visible at a glance. PS-205 enforces this.

| Source | Test |
| :--- | :--- |
| `foo.py` | `test_foo.py` |
| `_foo.py` | `test__foo.py` |
| `BarClass.py` | `test_BarClass.py` |
| `_BarClass.py` | `test__BarClass.py` |
| `__init__.py` | (usually no test; `test___init__.py` only if you have a real reason) |

## Allowed `tests/` subdirectories

Tests are organized into a **fixed set of literal subdirectories**. Anything else triggers `PS-302`. Only `<pkg>` is variable; everything else is a literal name:

| Subdir | Tracked? | Mirrors / contains |
| :--- | :--- | :--- |
| `tests/<pkg>/` | ✅ | 1:1 mirror of `src/<pkg>/` (the bulk of unit tests) |
| `tests/scripts/` | ✅ | mirror of `./scripts/` |
| `tests/examples/` | ✅ | one `test_<example-stem>.py` per file in `./examples/` |
| `tests/develop/` | ✅ | **canonical** home for auto-generated scitex-dev gate tests (audit conformance + skills quality). Replaces the deprecated `tests/skills/`. |
| `tests/skills/` | deprecated | legacy structural tests for shipped `_skills/` — migrate into `tests/develop/`. `tests/integration/test_audit_conformance.py` was a duplicate of the develop-gate audit and has been **deleted**. |
| `tests/agentic/` | ✅ | agentic-trigger tests — LLM invokes the skill / MCP tool / CLI and we assert the right path fires |
| `tests/integration/` | ✅ | Python-level cross-module / cross-package tests |
| `tests/smoke/` | ✅ | **fast (<60s)** subprocess-driven CLI happy-path tests; marker `smoke`; runs on every PR (PS-211) |
| `tests/e2e/` | ✅ | **mandatory** end-to-end workflows against real subsystems; marker `e2e`; **runs on every PR by default** — NOT gated by `RUN_E2E=1`. Per-test `pytest.mark.skipif` only when a specific subsystem (apptainer, fastmcp, GPU, NAS) is missing on the runner. (PS-212) |
| `tests/github_actions/` | ✅ | local GitHub Actions runner config (`act`/Apptainer) |
| `tests/coverage/` | gitignored | HTML / XML coverage reports (replaces a top-level `./htmlcov/`) |
| `tests/results/` | gitignored | general test-run artifacts spanning topics (coverage data files, captured payloads, fixture output) |
| `tests/logs/` | gitignored | pytest run logs, captured stdout/stderr |
| `tests/reports/` | optional | agent-generated test summaries |
| `tests/custom/` | ✅ | legacy: tests with no source counterpart |

## Allowed at `tests/` root (NOT in a subdir) — strict

`PS-203` is **strict**: the only files allowed directly at `tests/` root
are pytest infrastructure files. Every test file must live in one of the
allowed subdirectories — there is no "meta test" exemption.

```
tests/
├── __init__.py            # OK
├── conftest.py            # OK
├── <pkg>/                 # required mirror parent
├── examples/              # cross-cutting tests live here
├── integration/
├── e2e/
└── ...
```

Where the old "meta tests" go now:

| Old `tests/test_*.py` | New home |
| :--- | :--- |
| `test_examples.py` | `tests/examples/test_run_all.py` |
| `test_integration.py` | `tests/integration/test_<name>.py` |
| `test_skills_quality.py` | `tests/develop/test_quality.py` (canonical; `tests/skills/` is deprecated) |
| `test_cli.py`, `test_api.py`, `test_server.py` | `tests/<pkg>/test_<name>.py` (mirror the src module being driven) |
| `test___version__.py`, `test___main__.py` | `tests/<pkg>/test___version__.py` etc. (they mirror `__version__.py` / `__main__.py`) |
| `test__install_guide.py`, `test__optional_deps.py` | `tests/integration/` or `tests/<pkg>/` depending on what they actually exercise |

If a legitimate exception comes up that doesn't fit any subdir, propose
extending the allowed-subdirs list rather than letting drift back into
`tests/` root — the strict rule keeps the layout reviewable.

## Other artefacts

- Large/long tests should target a remote/HPC runner via `dev_test_hpc*` MCP tools rather than blocking local dev.
- `pytest.ini` / `[tool.pytest.ini_options]` lives in `pyproject.toml`.
- `conftest.py` at `tests/` root is fine; subdir-scoped `conftest.py` files (`tests/<pkg>/conftest.py`) are also fine.

## Integration tests (`_real.py`)

The `_real` suffix denotes integration tests that exercise real I/O
against the same src module that `test_X.py` covers with mocks. PS-204
sees `test_X_real.py` as an orphan because no `_X_real.py` source file
exists, but this is by design.

**Canonical placement** — keep them out of the PS-204 mirror scope:

```
tests/integration/<mirror>/test_X_real.py       # mirrors src/<pkg>/<mirror>/_X.py
```

PS-204 only scans `tests/<pkg>/<mirror>/`, so `tests/integration/`
is silently skipped while `pytest tests/` still collects it.

Each subdirectory of `tests/integration/` needs an `__init__.py` so
pytest's rootdir-import mode disambiguates basename collisions when
two integration files share the same name (e.g. one
`test__zarr_real.py` under `_load_modules` and another under
`_save_modules`).

## Module-top imports of optional deps must `pytest.importorskip`

Any unguarded `import <optional-dep>` at the top of a test file fails
at **collection** if the dep is absent — pytest aborts the run, no
coverage is uploaded, and Codecov shows a stale or empty number.

Required pattern:

```python
import pytest
h5py = pytest.importorskip("h5py")
```

Rule code: **PA-303** (planned). Real-world incident: scitex-io
sat at 79 % on Codecov for weeks because `import optuna` at the top of
two test modules silently blocked collection. Once removed, the
underlying coverage moved 12 pp.

## Layered testing convention — `tests/smoke/` and `tests/e2e/`

The four test layers form a pyramid; each has a distinct role, speed
budget, and CI trigger:

| Layer | Speed | Trigger | What it tests |
| :--- | :--- | :--- | :--- |
| `tests/<pkg>/` | very fast | every PR | unit-level behaviour (mocked I/O OK where guarded) |
| `tests/integration/` | fast/medium | every PR | Python-level cross-module wiring (real objects, no subprocess) |
| `tests/smoke/` | **<60s total** | every PR | subprocess-driven CLI happy paths — `subprocess.run(["<cli>", "...", "--help"])` etc. |
| `tests/e2e/` | slow (minutes) | **every PR** (mandatory) | full workflows against real subsystems (network, GPU, NAS, …); per-test `skipif` only for missing subsystems |

### Naming + budget

- `tests/smoke/test_*.py` — keep tight; **≤8 smoke tests per package** is a
  good ceiling. Smoke is for "the binary launches and the obvious paths
  don't crash", not feature coverage.
- `tests/e2e/test_*.py` — **≤5 workflow tests per package**. Each test
  exercises one realistic end-to-end story.

### Pytest markers (must be registered)

Both markers MUST be declared in `pyproject.toml` so `-m smoke` / `-m e2e`
does not emit `PytestUnknownMarkWarning`:

```toml
[tool.pytest.ini_options]
markers = [
    "smoke: fast CLI happy-path tests (<60s, runs on every PR)",
    "e2e: end-to-end workflows against real subsystems (mandatory on every PR)",
]
```

Apply markers via `pytestmark = pytest.mark.smoke` at module top, or per
test with `@pytest.mark.smoke`.

### E2E skip strategy — subsystem-aware, NOT env-gated

E2E tests are **mandatory**: a bare `pytest` MUST collect and run them.
Earlier drafts of this leaf said E2E was opt-in via `RUN_E2E=1` — that
was wrong. The blanket skip-gate manufactures false confidence (CI is
green because nothing ran) and is removed.

The only legitimate skip is **per-test, keyed to a missing subsystem**:

```python
# tests/e2e/test_<workflow>.py
import shutil
import pytest

pytestmark = pytest.mark.e2e

@pytest.mark.skipif(shutil.which("apptainer") is None,
                    reason="apptainer not installed on this runner")
def test_full_pipeline_runs_against_real_container():
    ...

fastmcp = pytest.importorskip("fastmcp")  # only if dep missing
```

Acceptable skip predicates: missing CLI binary (`shutil.which`), missing
import (`importorskip`), missing GPU (`torch.cuda.is_available()`),
missing network endpoint, missing credential. NOT acceptable: a blanket
`os.environ.get("RUN_E2E")` check.

### Conftest expectations

- `tests/smoke/conftest.py` — fixtures for spinning a tmpdir / fake home;
  no network.
- `tests/e2e/conftest.py` — fixtures only; **no blanket skip gate**. May
  instantiate real clients (NAS, cloud, GPU runners) inside fixtures that
  themselves `pytest.skip(...)` when the subsystem is absent.

### Opt-out for packages without a CLI

Packages with no CLI surface (e.g. a pure-library tool) exempt themselves
from PS-211 (and implicitly PS-212) via pyproject.toml:

```toml
[tool.scitex_dev]
no_cli = true     # exempts PS-211 (and PS-212)
# no_e2e = true   # exempts PS-212 only
```

## Auditor coverage

`scitex-dev ecosystem audit-project <distribution>` enforces this layout:

- **PS-201** — missing `tests/<pkg>/` parent
- **PS-202** — `src/<pkg>/<sub>/` has files but no `tests/<pkg>/<sub>/`
- **PS-203** — *strict*: any `test_*.py` at `tests/` root (only `__init__.py` and `conftest.py` allowed)
- **PS-204** — orphan test (no matching `src/<pkg>/<path>/...`); detail
  is *enriched*: when exactly one src file shares the expected basename,
  the violation suggests the relocate target; otherwise it lists the
  files actually present in the mirror dir so you can correlate
- **PS-205** — wrong public/private prefix
- **PS-206** — placeholder-only test (no `def test_` or `class Test`)
- **PS-207** — empty test mirror directory (mirror dir exists but contains
  no `test_*.py`, while the corresponding `src/<pkg>/<sub>/` has source
  files); src-aware so it never flags fixture trees that legitimately have
  no source counterpart
- **PS-211** *(W)* — `tests/smoke/` missing OR the `smoke` pytest marker
  not registered in `pyproject.toml`. Severity warning during ecosystem
  adoption; promoted to error once all packages have a smoke layer.
  Opt-out: `[tool.scitex_dev] no_cli = true`.
- **PS-212** *(W)* — `tests/e2e/` missing OR the `e2e` pytest marker not
  registered. Severity warning during adoption.
  Opt-out: `[tool.scitex_dev] no_e2e = true` (or `no_cli = true`).
- **PS-302** — unrecognized subdir at `tests/` root
- **PS-303** — `examples/<name>` without matching `tests/examples/test_<name>.py`

## Historical: `sync_tests_with_source.sh` and source-as-comments

The legacy `tests/sync_tests_with_source.sh` script (still in `~/proj/scitex-python/`) auto-creates missing test files and mirrors the directory structure. It also **embedded source code as comments** at the bottom of every test file — that pattern is now considered too noisy and should be dropped.

The auditor (`audit-project`) is read-only — it never writes to test files. Future work: a `--fix` flag that does the mirror creation without the comment embedding.
