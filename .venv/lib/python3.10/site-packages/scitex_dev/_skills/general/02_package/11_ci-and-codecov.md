---
description: |
  [TOPIC] CI and Codecov Setup for SciTeX Packages
  [DETAILS] Adopted 2026-05. Documents the GitHub Actions test.yml shape, codecov-action@v5 invocation, the `if: always() && matrix.python-version == 'X'` upload pattern (so coverage uploads even when tests fail), the `.[all,dev]` install line (so optional-dep loaders actually run), the canonical codecov.yml ignore patterns (_sphinx_html, _skills, _completion.py, tests, examples), the `codecov.branch: develop` line that points the unbranched badge at develop (since main is just a release-mirror), CODECOV_TOKEN secret setup (sourced from ~/.dotfiles/.../codecov.txt via 000_ACCESS_TOKENS.src), and the two-row badge layout that exposes it on README. Use when wiring coverage on a new SciTeX peer or debugging why a badge shows "unknown" / a stale number.
tags: [scitex-general-package-ci-codecov]
---

# CI and Codecov Setup

## Reference package

`scitex-io` is the canonical example. When wiring coverage on a new peer,
mirror these three files verbatim and substitute the import name:

- `.github/workflows/test.yml`
- `codecov.yml`
- README badge block (two-row layout, see below)

Do not invent a different shape — every package in the ecosystem should look
the same so a single grep across repos keeps the convention enforceable.

## test.yml workflow shape

Matrix over Python 3.10 / 3.11 / 3.12 / 3.13. Install with a fallback chain
so packages that don't declare `[all]` still build. Upload coverage exactly
once per workflow run, gated on the 3.12 row and `if: always()` so a failing
test row still ships its `coverage.xml`.

```yaml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[all,dev]" || pip install -e ".[dev]" || pip install -e .
      - name: Run tests
        run: |
          pytest --cov=src/<import_name> --cov-report=xml --cov-report=term
      - name: Upload coverage to Codecov
        if: always() && matrix.python-version == '3.12'
        uses: codecov/codecov-action@v5
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          files: ./coverage.xml
          fail_ci_if_error: false
```

The `if: always()` is the critical bit. Without it, GitHub Actions implicitly
evaluates `success()` and skips the upload whenever any prior step (including
pytest) fails — which is exactly when you most want coverage visible.

## codecov.yml

Drop this at repo root. Adjust the `<import_name>` token but keep everything
else identical across packages:

```yaml
codecov:
  require_ci_to_pass: false
  # Treat develop as the de-facto default branch — main is a stable
  # release mirror that only fast-forwards from develop, so develop
  # is where coverage uploads land. This makes the unbranched badge
  # endpoint (/graph/badge.svg) follow develop's value.
  branch: develop

coverage:
  status:
    project:
      default:
        target: auto
        threshold: 1%
    patch:
      default:
        target: 80%

ignore:
  - "src/<import_name>/_sphinx_html/**"
  - "src/<import_name>/_skills/**"
  - "src/<import_name>/_completion.py"
  - "src/<import_name>/_cli/_completion.py"
  - "tests/**"
  - "examples/**"

comment:
  layout: "diff, files"
  require_changes: true
```

Rationale:

- `codecov.branch: develop` — the codecov page's headline number and
  the unbranched `/graph/badge.svg` follow develop. Without this, the
  badge points at `main` (the release-mirror branch) and shows the
  stale number from the last release-cut while develop has long since
  moved on. Every SciTeX peer uses this.
- `_sphinx_html/` is generated HTML; never covered.
- `_skills/` is markdown documentation; not executable.
- `_completion.py` (and `_cli/_completion.py`) are shell-completion shims —
  pure boilerplate, no real logic to test.
- `tests/` and `examples/` shouldn't count toward their own coverage.

### README badge URL

For belt-and-suspenders robustness against any codecov-side config
drift, the README badge can also pin develop explicitly:

```markdown
[![Coverage (develop)](https://codecov.io/gh/<org>/<repo>/branch/develop/graph/badge.svg)](https://codecov.io/gh/<org>/<repo>/branch/develop)
```

This always renders develop's number regardless of dashboard
settings. Recommended in addition to `codecov.branch: develop`.

## CODECOV_TOKEN secret

Three steps, in order:

1. **Token file** lives at
   `~/.dotfiles/src/.bash.d/secrets/access_tokens/codecov.txt`
   (one line, the upload token from codecov.io account settings).

2. **Shell export** — add a `CODECOV_TOKEN_PATH` block to
   `~/.dotfiles/src/.bash.d/secrets/000_ACCESS_TOKENS.src`, mirroring the
   existing `GITHUB_TOKEN` / `HUGGINGFACE_TOKEN` / `SLACK_TOKEN` entries
   (load-if-exists guard, then `export CODECOV_TOKEN="$(cat …)"`). This makes
   `gh secret set` work from any shell without copy-paste.

3. **Repo secret**:
   ```bash
   gh -R <owner>/<pkg> secret set CODECOV_TOKEN < \
     ~/.dotfiles/src/.bash.d/secrets/access_tokens/codecov.txt
   ```

Note: codecov-action@v5 supports tokenless uploads for public repos, but the
explicit token is more reliable for badge ingestion (the first tokenless
upload on a brand-new repo sometimes lags before the badge resolves).

## Common gotchas

- **Upload skipped on test failure.** Add `if: always() && matrix.python-version == '3.12'`
  to the codecov step. Pytest writes `coverage.xml` even when tests fail; the
  upload step just needs to opt back in to running on failure.
- **Coverage stuck at ~19%.** CI is installing only `.[dev]`, so loaders
  guarded by `pytest.importorskip("h5py")` etc. get skipped. Install
  `.[all,dev]` to exercise the full scientific stack.
- **Badge shows "unknown" forever.** Repo not activated on codecov.io and/or
  `CODECOV_TOKEN` missing. Set the secret; the first successful upload
  auto-activates the repo.
- **Codecov drops uploads silently.** `fail_ci_if_error: false` swallows the
  error so CI stays green. Check the workflow step logs (search for
  "codecov") for the real cause — usually a missing token or a malformed
  `coverage.xml` path.

## Badge in README

Two-row layout. Top row = release metadata, bottom row = build health:

```markdown
[![PyPI](https://img.shields.io/pypi/v/<pkg>.svg)](https://pypi.org/project/<pkg>/)
[![Python](https://img.shields.io/pypi/pyversions/<pkg>.svg)](https://pypi.org/project/<pkg>/)
[![Read the Docs](https://readthedocs.org/projects/<pkg>/badge/?version=latest)](https://<pkg>.readthedocs.io/)

[![Tests](https://github.com/<owner>/<pkg>/actions/workflows/test.yml/badge.svg)](https://github.com/<owner>/<pkg>/actions/workflows/test.yml)
[![Install Test](https://github.com/<owner>/<pkg>/actions/workflows/install-test.yml/badge.svg)](https://github.com/<owner>/<pkg>/actions/workflows/install-test.yml)
[![codecov](https://codecov.io/gh/<owner>/<pkg>/graph/badge.svg)](https://codecov.io/gh/<owner>/<pkg>)
```

Codecov badge URL pattern: `https://codecov.io/gh/<owner>/<pkg>/graph/badge.svg`.

## Reaching ≥ 90% coverage

Honest tradeoffs — there is no shortcut:

- **Per-format loaders** (`_save_modules/`, `_load_modules/`) need real
  round-trip tests. One test per format: save → load → assert equal. This is
  the bulk of the coverage work for I/O-heavy packages.
- **CLI / MCP scaffolding** — either write smoke tests (invoke each
  subcommand with `--help` and assert exit 0) OR add to `codecov.yml` ignore
  list. Judgment call per package; smoke tests are usually cheap.
- **Pure interface code** (shell-completion shims, generated scaffolding,
  `__main__.py` thunks) — ignore in `codecov.yml`. These are not testable
  units.
- 90% is achievable **only** with real tests for the format loaders.
  Ignoring everything but the core to inflate the number is dishonest and
  will rot when someone later removes the ignores.

## Mandatory `tests/develop/test_audit.py`

Every package must ship a `tests/develop/test_audit.py` that runs
`scitex-dev ecosystem audit-all <distribution>` as a normal pytest test.
This makes audit conformance part of the failing-CI signal instead of a
separate check the team learns to ignore.

Generate it with `scitex-dev ecosystem write-audit-test` and commit. The
default body looks like:

```python
import shutil
import pytest

def test_audit_all_clean():
    if shutil.which("scitex-dev") is None:
        pytest.skip(
            "scitex-dev not installed — add scitex-dev[cli-audit] to "
            "[project.optional-dependencies.dev]"
        )
    from scitex_dev.testing import audit_all_for_package
    audit_all_for_package("<distribution>")
```

`skip_rules=(...)` is for true convention-deviations that need a fix in
the spec, not for muffling a real violation. If a rule fires, fix the
package; don't add a skip.

## Track `.scitex/dev/config.yaml`

Audit whitelists (`audit.root-whitelist.files:` etc.) live at
`<repo>/.scitex/dev/config.yaml`. The directory is gitignored by default
(`.scitex/` is runtime state for local tooling), so add a `.gitignore`
exception so CI sees the same whitelist as local:

```gitignore
# .gitignore
.scitex/*
!.scitex/dev/
.scitex/dev/*
!.scitex/dev/config.yaml
```

A directory-level `.scitex/` exclusion blocks negation; switch to
file-level so the negation rule applies.

## Hard `--cov-fail-under` gate (optional)

The Codecov `coverage.status.project.target` setting is the primary
gate; it runs after the upload and posts a check on PRs. For an
additional pre-upload guard, add `--cov-fail-under=90` to the pytest
invocation:

```yaml
- name: Run tests with coverage
  run: |
    python -m pytest "$GITHUB_WORKSPACE/tests/" -v --tb=short --timeout=120 \
      --cov=src/${{ steps.pkg.outputs.import_name }} \
      --cov-report=xml --cov-report=term \
      --cov-fail-under=90
```

Only adopt this once the package is already ≥ 90 %; setting it earlier
just makes CI permanently red.

## Dev-bootstrap MUST install marker-providing packages

The `[dev]` extras (or whatever extras the bootstrap installs) MUST
include every package that registers a pytest marker / collector
plugin the test suite uses. The campaign found two recurring offenders:

- **`pytest-asyncio`** — without it, `@pytest.mark.asyncio` decorated
  tests emit `PytestUnknownMarkWarning` and the coroutine body never
  awaits anything (the test silently "passes" by doing nothing).
- **`fastmcp`** — without it, MCP-server tests skip via
  `pytest.importorskip("fastmcp")` and the entire MCP surface goes
  un-exercised in CI; the badge is green for the wrong reason.

Both belong in `[project.optional-dependencies].dev` (or `.test`, if
the package splits them) and must be installed by every CI workflow
that runs `pytest tests/`. Verify with:

```bash
.venv/bin/python -c "import pytest_asyncio, fastmcp; print('ok')"
```

If this fails after `pip install -e .[dev]`, the extras are missing the
package. Add it; do not paper over with a workflow-level
`pip install pytest-asyncio` — the dev-bootstrap is the source of
truth for "everything a developer needs to run the suite".

The bootstrap gap manifests as confusing
`PytestUnknownMarkWarning: Unknown pytest.mark.asyncio` lines in the
CI log; that warning is the symptom of this rule being violated.

## Test-file imports of optional deps must `pytest.importorskip`

Any `import <optional-dep>` at module top of a test file MUST be
guarded:

```python
import pytest
h5py = pytest.importorskip("h5py")
```

Otherwise the test module fails at *collection* if the optional dep is
absent, which silently aborts ALL tests in that pytest run — coverage
upload never happens, masking the real state of every other test in the
package.

This is the contract Codecov assumes. Rule code reserved: **PA-303**
(see `03_interface/01_python-api/TODO.md`).

## Merge `Test` + `Install Test` into one workflow

Two badges saying "tests pass" is redundant. Keep both jobs but
collapse them into a single `test.yml`:

```yaml
jobs:
  test:                  # the existing pytest matrix
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps: [...]

  install-check:         # what install-test.yml currently does
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: |
          python -m venv .venv
          .venv/bin/pip install -e .
          .venv/bin/python -c "import <import_name>"
```

One workflow → one badge → one re-run button. Delete the old
`install-test.yml`. Update the README badge block to remove the second
Tests row.

## `tests/integration/<mirror>/` for `_real.py` tests

PS-204 (orphan test file) flags `tests/<pkg>/<mirror>/test_X_real.py`
because there is no `src/<pkg>/<mirror>/_X_real.py` to mirror. The
`_real` suffix is the SciTeX convention for "integration test with
real I/O, no mocks" — a deliberate sibling of `test_X.py`. Two clean
ways to satisfy both conventions:

1. **Move** to `tests/integration/<mirror>/test_X_real.py`. PS-204 only
   scans `tests/<pkg>/<mirror>/`, so the orphan rule doesn't fire and
   pytest still collects them via `tests/`.
2. **Merge** the contents into `tests/<pkg>/<mirror>/test_X.py` as a
   `class TestIntegration:` block. Heavier rewrite; only worth it when
   the file is small.

Add `__init__.py` to each new `tests/integration/<mirror>/` directory
so pytest's rootdir-import mode disambiguates basename collisions
(e.g. two `test__zarr_real.py` under different mirror dirs).

## Related skills

- `02_package/07_github-actions.md` — workflow conventions, matrix shape,
  install-test workflow.
- `02_package/08_quality.md` — overall package quality bar.
- `01_ecosystem/02_dependency-and-version-pinning.md` — the `[dev]` extras
  completeness rule that makes `.[all,dev]` reliable.
- `03_interface/01_python-api/04_lazy-imports-and-optional-deps.md` —
  `try_import_optional` canonical pattern (PA-302); pairs with
  `pytest.importorskip` on the test side (PA-303).
