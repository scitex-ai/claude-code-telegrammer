---
description: |
  [TOPIC] Subprocess coverage wiring (parallel + COVERAGE_PROCESS_START)
  [DETAILS] Adopted 2026-05 after scitex-stats lifted Codecov ~32% → ~90%. When tests spawn child Python interpreters (subprocess.run([sys.executable, "-m", ...]), jupyter nbconvert --execute, etc.), the default pytest-cov setup throws their coverage data away because COVERAGE_FILE points to a per-test-process tmp dir before conftest.py runs. The fix is three small changes: pyproject `[tool.coverage.run] parallel = true, concurrency = ["multiprocessing", "thread"]`, conftest.py force-set (not setdefault) of COVERAGE_PROCESS_START + COVERAGE_FILE, and an idempotent `.pth` shim in site-packages that calls `coverage.process_startup()`. This single wiring is what unlocks demo smoke tests + notebook executions counting toward coverage.
tags: [scitex-general-package-subprocess-coverage]
---

# Subprocess coverage wiring

## When this matters

If your test suite ever spawns a child Python interpreter — e.g.:

- `subprocess.run([sys.executable, "-m", "pkg.module"], ...)` (demo smoke tests)
- `jupyter nbconvert --execute notebook.ipynb` (PS-505 example tests)
- `pytest-xdist` parallel workers (multiple worker processes)

…that child's coverage data is **dropped** in a default pytest-cov setup,
because `pytest-cov` sets `COVERAGE_FILE` to a per-test tmp dir before
`conftest.py` runs, and child processes don't know where to write.

Symptom: coverage stays mysteriously low despite covering "everything" in
tests; ~1500 LOC of `_demo_*.py` modules report 0% even when smoke tests
execute them end-to-end.

## The three-part fix

### 1. pyproject.toml `[tool.coverage.run]`

```toml
[tool.coverage.run]
parallel = true
source = ["<import_name>"]
concurrency = ["multiprocessing", "thread"]
```

- `parallel = true` makes every coverage process write to its own
  `.coverage.<hostname>.<pid>.<random>` file (instead of all writing to
  one and racing).
- `concurrency = ["multiprocessing", "thread"]` covers both
  `subprocess.run` (multiprocessing) and any threaded test code.
- `pytest-cov` will call `coverage combine` at session end to merge the
  shards into a single `coverage.xml`.

### 2. tests/conftest.py — FORCE-SET, not setdefault

```python
"""Module-import-time coverage wiring (parallel + subprocess support).

`os.environ.setdefault` would be a no-op here because pytest-cov has
already set COVERAGE_FILE to a tmp dir by the time conftest is loaded.
"""
from __future__ import annotations

import os
import sys
import sysconfig
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Pin coverage's data file at the repo root and point process_startup
# at our pyproject so child interpreters configure themselves correctly.
os.environ["COVERAGE_PROCESS_START"] = str(_PROJECT_ROOT / "pyproject.toml")
os.environ["COVERAGE_FILE"] = str(_PROJECT_ROOT / ".coverage")


def _ensure_subprocess_coverage_shim() -> None:
    """Drop an idempotent `.pth` file in site-packages that auto-starts
    coverage in every child Python interpreter via
    `coverage.process_startup()`.
    """
    purelib = Path(sysconfig.get_paths()["purelib"])
    pth = purelib / "_<import_name>_subprocess_coverage.pth"
    shim = (
        "import os, coverage\n"
        "if os.environ.get('COVERAGE_PROCESS_START'):\n"
        "    coverage.process_startup()\n"
    )
    try:
        if not pth.exists() or pth.read_text() != shim:
            pth.write_text(shim)
    except OSError:
        # site-packages may be read-only (e.g. system Python); silently
        # skip — local dev venvs are writable and that's where this matters.
        pass


_ensure_subprocess_coverage_shim()
```

Critical detail: **force-set, not `setdefault`**. `pytest-cov` sets
`COVERAGE_FILE` before `conftest.py` runs, so `setdefault` is a silent
no-op and the fix appears to "do nothing" — a classic foot-gun.

The `.pth` shim works because Python's site initialization imports every
`.pth` file in `site-packages` before user code runs, so by the time a
child process imports anything, coverage tracing is already on.

### 3. (Optional) .coveragerc fallback

If you don't want pyproject-based config, the same can live in
`.coveragerc`:

```ini
[run]
parallel = True
source = <import_name>
concurrency = multiprocessing,thread
```

`COVERAGE_PROCESS_START` will pick up whichever file path you point at.

## Verifying it works

Run the suite locally:

```bash
pytest -x
ls .coverage.*  # should show several .coverage.<host>.<pid> shards
coverage combine
coverage report  # should now include subprocess-only LOC
```

Before the wiring, `.coverage.*` shards are absent (children don't write)
and demo modules show 0% even though `test_demos.py` executed them.

## CI side: nothing extra

pytest-cov calls `coverage combine` automatically at session end, then
emits `coverage.xml`. The Codecov upload step doesn't need to change —
the same artifact now contains subprocess coverage.

## Gotchas

- **`COVERAGE_FILE` pinned to repo root, not tmp.** If you point it at a
  tmp dir, the per-test shards land somewhere `coverage combine` won't
  find them. Repo root is canonical.
- **Shim must be idempotent.** Test reruns will overwrite the `.pth`
  file every time without the `if not pth.exists() or pth.read_text() != shim`
  guard — minor but it adds noise to `pip list -v` output.
- **site-packages may be read-only.** Catch `OSError` and continue;
  system-Python users can't write the shim, but in practice everyone
  runs tests from a venv they own.
- **`coverage>=7` required.** Older versions don't support all the
  concurrency keys; pin `coverage>=7.0` in `[dev]` extras (already
  transitive via `pytest-cov>=4.0`).

## Related skills

- `02_package/11_ci-and-codecov.md` — overall CI / codecov.yml setup.
- `05_development/07_demo-smoke-tests.md` — the demo smoke test pattern
  that this wiring exists to instrument.
- `01_ecosystem/02_dependency-and-version-pinning.md` — `[dev]` extras
  completeness rule (the reason `nbconvert` / `ipykernel` go in `[dev]`).
