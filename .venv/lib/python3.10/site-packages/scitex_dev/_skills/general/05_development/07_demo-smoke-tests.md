---
description: |
  [TOPIC] Demo smoke tests — drive every `_demo_*.py` and `__main__`-bearing `_test_*.py` via `python -m` in tmp_path
  [DETAILS] Adopted 2026-05 after scitex-stats. Many SciTeX packages ship runnable demos as `_demo_<name>.py` siblings (or as `if __name__ == "__main__":` blocks at the bottom of `_test_<name>.py`). These are typically ~50-200 LOC each, ship to users as worked examples, and were collectively ~1500 LOC of zero-coverage dead weight before this pattern. A single parametrised pytest file (`tests/integration/test_demos.py`) walks every demo module via `subprocess.run([sys.executable, "-m", mod], cwd=tmp_path, check=True)` and verifies it runs end-to-end. Combined with the subprocess-coverage wiring (see leaf 06), this lifts coverage by 10-20 points in one stroke and catches real bugs (NameError, removed API calls, tuple-unpack mistakes) that pure unit tests miss.
tags: [scitex-general-package-demo-smoke-tests]
---

# Demo smoke tests

## What's a demo?

A "demo" in the SciTeX convention is a self-contained, runnable example
that ships inside `src/<pkg>/.../`. Two flavours coexist:

- **Sibling files**: `src/<pkg>/correct/_demo_correct_holm.py` next to
  `_correct_holm.py`. Pure demo, no test assertions.
- **Embedded `__main__` blocks**: at the bottom of `src/<pkg>/.../_test_<name>.py`,
  an `if __name__ == "__main__":` block that calls `run_main()`. The
  test logic above is the real test; the `__main__` block is a runnable
  example.

Both are user-facing — they're the "hello world" anyone runs first.
Both are usually 50-200 LOC each. Across a typical SciTeX package they
collectively add up to 1000-2000 LOC.

## The problem

Without a smoke test, these demos:

- Don't contribute to coverage (CI never executes them).
- Silently rot — a removed API, a renamed kwarg, a tuple-vs-scalar
  return change breaks them at the next `python -m` someone runs.
- Hide real bugs: `NameError: name 'stx' is not defined`,
  `AttributeError: 'DataFrame' object has no attribute 'applymap'`,
  `TypeError: cannot unpack non-iterable…`

scitex-stats had ~1500 LOC of demos at 0% coverage and seven latent
real bugs in them when the smoke test was first wired up.

## The pattern

One file, `tests/integration/test_demos.py`, that parametrises every
demo module:

```python
"""Smoke-test every _demo_*.py and __main__-bearing _test_*.py module.

Each demo is run as `python -m <module>` in an isolated tmp_path so the
caller-anchored I/O routing (scitex.io creates `_out/` siblings) lands
in a disposable dir, not the repo. Failure modes caught here include:

- NameError / AttributeError from drift against the library.
- ValueError from a kwarg the function never supported.
- Crash on import (e.g. pandas 2.2 removed Styler.applymap).
"""
from __future__ import annotations

import subprocess
import sys

import pytest

# Two-bucket list. Sibling demos go in the first bucket; in-source
# __main__ blocks in the second. Splitting them keeps the rationale
# greppable when someone adds a new demo and wonders which bucket fits.
SIBLING_DEMOS = [
    "<pkg>.correct._demo_correct_bonferroni",
    "<pkg>.correct._demo_correct_holm",
    # ...
]

EMBEDDED_DEMOS = [
    "<pkg>.tests.kendall._test_kendall",
    "<pkg>.tests.spearman._test_spearman",
    # ...
]

DEMOS = SIBLING_DEMOS + EMBEDDED_DEMOS


@pytest.mark.parametrize("module", DEMOS, ids=lambda m: m.rsplit(".", 1)[-1])
def test_demo_runs(module, tmp_path):
    """Execute the demo end-to-end in an isolated working directory."""
    result = subprocess.run(
        [sys.executable, "-m", module],
        cwd=tmp_path,
        check=False,
        timeout=180,
        capture_output=True,
    )
    if result.returncode != 0:
        # Surface stderr in the pytest failure so the real error
        # (NameError line, API mismatch, etc.) is visible without
        # re-running locally.
        raise AssertionError(
            f"{module} exited {result.returncode}\n"
            f"--- stdout ---\n{result.stdout.decode()}\n"
            f"--- stderr ---\n{result.stderr.decode()}"
        )
```

Key choices:

- **`cwd=tmp_path`** — demos that write `_out/` siblings via scitex.io
  caller-anchored routing land in a disposable dir. Without this, demos
  litter the repo with `_demo_X_out/` directories and trip PS-103
  (top-level junk).
- **`python -m`** — runs the module exactly as a user would. Imports go
  through the normal site-packages path, so no test-only monkey-patches
  hide regressions.
- **`timeout=180`** — generous default. Most demos finish in <10s;
  cap exists only so a hung demo doesn't wedge the whole suite.
- **`check=False` + manual surface** — `check=True` raises
  `CalledProcessError` whose message just says "exited with code 1",
  swallowing the real Python traceback. Capturing stderr and including
  it in the AssertionError makes failures actionable from the CI log.
- **`ids=lambda m: ...`** — the parametrise id is the last dotted
  component, so pytest output shows `test_demo_runs[_demo_correct_holm]`
  not `test_demo_runs[<pkg>.correct._demo_correct_holm]`.

## File location: tests/integration/

Put this file under `tests/integration/test_demos.py`, **not** under
`tests/<pkg>/.../`. Reason: PS-204 (orphan test file) expects every
file under `tests/<pkg>/` to mirror a `src/<pkg>/` sibling 1:1.
A multi-module parametrised smoke test has no single mirror.

Add `tests/integration/__init__.py` (empty) so pytest's rootdir-import
mode disambiguates basename collisions.

## Pairs with subprocess-coverage wiring

This pattern only earns coverage *if* the subprocess-coverage wiring
from leaf 06 is in place. Without it, the children write their
`.coverage.*` shards to a tmp dir that `coverage combine` never sees.

The two leaves are designed to land together: add the wiring first,
then this smoke test will start contributing to the Codecov number.

## Bug classes this catches

From scitex-stats's first run of this pattern:

- **Umbrella-import drift**: demo's `run_main()` references `stx` but
  never imports `scitex as stx`. PA-304 compliant fix is a
  *function-scoped* `import scitex as stx` inside `run_main`, not at
  module top.
- **Removed library APIs**: pandas 2.2 removed `Styler.applymap` →
  `df.style.map`. Demo was the first thing to crash.
- **Phantom kwargs**: `convert_results(return_as="excel")` was never
  supported; demos called it and crashed. Fix is to switch to
  `df.to_excel(path)` directly.
- **Tuple-vs-scalar return**: `test_anova_2way(plot=True)` returns
  `(result, fig)` but `_demo_anova_2way` unpacked it as if scalar.
- **Missing import**: `_demo_shapiro.run_main()` used `plt` without
  importing matplotlib.pyplot.
- **Dead duplicate file**: `_correct_fdr_.py` (trailing underscore)
  alongside the real `_correct_fdr.py`; the package always imported
  from the real one, so the duplicate silently rotted. The smoke test
  attempts to import it and fails immediately.

## What about xfail / skip?

Don't. If a demo is broken, fix the demo (or fix the library the demo
is exercising). The whole point of the smoke test is that it cannot be
muted — any xfail is a workaround that lets the next regression slip
through. See `09_quality/01_failure-playbook.md` "real fix, never xfail".

## Audit interaction

- **PS-204** (orphan test file mirror): satisfied by placing the file
  under `tests/integration/`, not `tests/<pkg>/`.
- **PS-505** (notebook tests): unrelated — that one's for `examples/*.ipynb`
  via `jupyter nbconvert --execute`. Both patterns share the
  subprocess-coverage wiring (leaf 06).

## Related skills

- `05_development/06_subprocess-coverage.md` — the wiring that makes
  these smoke tests contribute to coverage.
- `02_package/11_ci-and-codecov.md` — overall codecov setup.
- `09_quality/01_failure-playbook.md` — no-cut-corners / no-xfail rule.
