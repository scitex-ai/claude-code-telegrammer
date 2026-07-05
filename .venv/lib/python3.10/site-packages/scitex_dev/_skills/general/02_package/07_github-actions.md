---
description: |
  [TOPIC] Github Actions
  [DETAILS] Canonical GitHub Actions workflows that every SciTeX repo ships — test matrix across supported Python versions, PyPI publish via trusted-publisher OIDC (no API tokens), CLA-bot, reusable workflow patterns, artefact caching, the `pip install -e ".[dev]"` rule, dep-hygiene gotchas (test imports must use the standalone module name not the umbrella shim), and release-gate checks that guard the main branch. Use when creating a new scitex-* repo, auditing CI drift across the ecosystem, or debugging a red workflow.
tags: [scitex-general-package-github-actions]
---

# GitHub Actions (SciTeX)

## Test job — install with the `[dev]` extra

CI runners start clean: no `pytest`, no `pytest-cov`, no `pytest-asyncio`, no project deps. The single canonical install line in every test workflow is:

```yaml
- name: Install
  run: pip install -e ".[dev]"
```

The `[dev]` extra in `pyproject.toml` MUST cover everything the test suite imports:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov",
    "pytest-asyncio>=0.21",   # only if any test uses @pytest.mark.asyncio
    # … any other dev-time-only dep (mypy, ruff for the CI lint job, etc.)
]
```

Common breakage modes:

| Symptom in CI logs | Root cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pytest'` | bare `pip install -e .` | switch to `pip install -e ".[dev]"` |
| `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio` then test counted as fail | `pytest-asyncio` missing from `[dev]` | add it |
| `ModuleNotFoundError: No module named 'click'` while running CLI | runtime dep declared only under `[dev]` | move to `dependencies = [...]` |

## Test imports — use the standalone module name, not the umbrella shim

**Rule.** Inside a standalone `scitex-X` package's `tests/`, always import via `scitex_X` directly:

```python
# YES — works in any environment that has scitex-X installed
from scitex_template import clone_template_from_cache
from scitex_template._mcp.handlers import list_templates_handler

# NO — only works when the scitex umbrella + its sys.modules alias shim
# are both installed. Fresh CI venv installs scitex-X alone, so this raises
# ModuleNotFoundError at collection time:
from scitex.template import clone_template_from_cache
from scitex.template._mcp.handlers import list_templates_handler
```

The same rule applies to internal imports inside `src/scitex_X/`. The umbrella shim path is only for users discovering the API via `scitex.X.…`; it is never a runtime path the package itself should rely on.

**Quick sed to fix a broken test suite after extraction:**

```bash
grep -rl "from scitex\.<name>\." tests/ \
  | xargs sed -i 's/from scitex\.<name>\b/from scitex_<name>/g'
```

## Downstream-dep hygiene in CI

A standalone `scitex-X` package SHOULD install cleanly without the `scitex` umbrella present (general/01_ecosystem/02 §"Dependency Hygiene"). This is enforced in CI by running the test job in a fresh venv that installs ONLY `pip install -e ".[dev]"` — no `scitex`. If any test imports `scitex.…` (the umbrella) it will fail; that's the intended signal.

When a few legacy code paths still need umbrella access (e.g. the cloner's remote-clone fallback that uses `scitex.git`), declare a separate optional extra:

```toml
[project.optional-dependencies]
legacy = ["scitex"]
```

…and gate the imports with `try/except ImportError`. The default `[dev]` install must NOT pull `[legacy]`; otherwise the dep-hygiene check is meaningless.

## SciTeX-Specific CLA Allowlist

```yaml
# cla.yml — <username> (committer) is always in the allowlist for SciTeX packages
allowlist: bot*,<username>
```

## scitex-python Transitional Pattern

scitex-python is transitioning from monorepo to standalone packages; use path-filtered reusable workflows where modules remain in-tree.

```yaml
# test-stats.yml (module-specific caller)
on:
  push:
    paths: [src/scitex/stats/**, tests/scitex/stats/**]
jobs:
  test:
    uses: ./.github/workflows/_test-module.yml
    with:
      module: stats
```

The reusable `_test-module.yml` calls `./scripts/test-module.sh ${{ inputs.module }}`.

## Module-Specific Workflows Table

| Workflow file | Module | Path filter |
|---------------|--------|-------------|
| `test-io.yml` | io | `src/scitex/io/**` |
| `test-plt.yml` | plt | `src/scitex/plt/**` |
| `test-stats.yml` | stats | `src/scitex/stats/**` |
| ... | ... | ... |

## PyPI publish — OIDC trusted publisher only

```yaml
# publish-pypi.yml
on:
  push:
    tags: ['v*']
jobs:
  publish:
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/<pkg-name>     # MUST match exact PyPI project name
    permissions:
      id-token: write                        # required for OIDC
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

Trigger: push a `v0.1.0`-style tag. The first publish requires a one-time browser configuration at https://pypi.org/manage/account/publishing/ — bind the GitHub repo + workflow name + environment name. After that, every tag triggers an automatic release. **Never** store `PYPI_API_TOKEN` in repo secrets.

Naming patterns:
- Tag-based publish: used by most scitex-* packages (push `v*` tag).
- Release-based publish: used by scitex-python (GitHub Release published).

## Weekly quality audit

Every package inheriting from `scitex-minimal-template` carries `.github/workflows/scitex-quality.yml`. Runs `scitex-dev quality {audit-cli, audit-frontmatter, audit-docs, audit-lines, audit-scope}` on a Monday cron + on push/PR. Warn-only (`continue-on-error: true`) until the package is clean; flip individual steps to fail-the-build once green.

## Per-package audit: `scitex-dev ecosystem audit-all <pkg>` is mandatory

Every `scitex-*` repo MUST run `scitex-dev ecosystem audit-all <pkg>` on every push and PR. This is the only ecosystem-wide gate that composes:

- `audit-cli` (§1–§11 click compliance)
- `audit-mcp-tools` (§1–§6 MCP compliance, including the §3 four-subcommand check)
- `audit-skills` (skill leaf shape, frontmatter, line budgets)
- `audit-python-apis` (Python API parity with CLI/MCP surfaces)
- `audit-project` (PS-101–PS-134 project-structure rules — readme, sphinx, version pins, CHANGELOG, license, etc.)

Without this gate, drift accumulates silently — packages can ship help text that contradicts the click tree, MCP tools that don't trace back to a Python API, missing CHANGELOG entries, or stale skill leaves. The §5b umbrella-passthrough rule is enforceable only when both the umbrella and the standalone run audit-all on the same commit.

### Wiring: a normal test, not a separate workflow

Audit-all rides on the package's existing test infrastructure — no
dedicated `.github/workflows/audit.yml`. The package's test workflow
imports the shared helper from scitex-dev and asserts a clean run:

```python
# tests/develop/test_audit.py — generated by `write-audit-test`
import shutil
import pytest


def test_audit_all_clean():
    if shutil.which("scitex-dev") is None:
        pytest.skip(
            "scitex-dev not installed — add `scitex-dev[cli-audit]` "
            "to [project.optional-dependencies.dev]"
        )
    from scitex_dev.testing import audit_all_for_package

    audit_all_for_package("<pkg-short-name>")
```

Where `<pkg-short-name>` matches the entry in `scitex_dev._ecosystem._core.ECOSYSTEM` (e.g. `scitex-io`, `scitex-cloud`, `scitex-hpc`, plus branded packages like `socialia` and `figrecipe`).

The helper runs `scitex-dev ecosystem audit-all <pkg>` as a
subprocess and raises `AssertionError` on nonzero exit. The full
stdout+stderr are captured into the test report so the failing rule,
its skill-tree pointer, and the escalation path are all visible
without re-running the audit by hand. Local `python -m pytest .`
gives the developer the same signal CI does.

### Required dependency: pin scitex-dev in `[dev]`

Every PyPI release of `scitex-dev` may add new audit rules; an
unpinned install makes a previously-green test go red overnight
without any change to the package being audited. Each package's
`pyproject.toml [project.optional-dependencies.dev]` MUST include:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "scitex-dev[cli-audit]==<X.Y.Z>",   # pin the version that's currently green
    # ...
]
```

To upgrade: `pip install -U scitex-dev`, then re-run
`scitex-dev ecosystem write-audit-test <pkg> --force` (the test stub
itself doesn't change, but you'll bump the pin in `pyproject.toml`
manually as part of the same change).

### Failure policy

The exit code is the single source of truth:

| Sub-auditor exit | Severity present                  | audit-all exit |
|------------------|-----------------------------------|----------------|
| 0                | none, or warn-only                | 0 (green)      |
| 1                | at least one error-severity rule  | 1 (red)        |
| 2                | not-auditable / install error     | 1 (red)        |

The test fails on any nonzero exit. As of 2026-05-06 every actionable
audit rule is `error` severity, so a violation = failed test = red CI.
Use the existing test workflow's branch-protection settings to gate
merges; no `continue-on-error` is involved.

### Per-package adoption

Use the helper to materialise the canonical test stub:

```bash
scitex-dev ecosystem write-audit-test <pkg-short-name>
```

Writes `tests/develop/test_audit.py` (force-required to overwrite),
plus `tests/develop/__init__.py` and an empty `tests/conftest.py`
when missing.

### Bypass — exceptions and temporal remedy

The audit gate is mandatory in steady state, but two situations
legitimately call for a temporary skip:

1. **Remediation in flight.** A package is mid-cleanup of pre-existing
   violations and the noise is blocking unrelated test runs.
2. **Local dev without the audit corpus.** A developer working on a
   feature on a machine where `scitex-dev[cli-audit]` isn't installed.

Both bypass via the environment variable:

```bash
SCITEX_DEV_SKIP_AUDIT=1 python -m pytest .
```

When set, `audit_all_for_package` calls `pytest.skip()` instead of
running the audit subprocess. The skip line shows up clearly in the
report so it's never silent.

**Hard rule.** CI for `main`/`develop` MUST NOT set
`SCITEX_DEV_SKIP_AUDIT`. The variable is for ephemeral local sessions
and short-lived cleanup branches only — every push to a release-track
branch must run the audit. If a package needs a sustained exemption
from a specific rule, demote that rule to `warn` in scitex-dev (with a
documented false-positive history) instead of muting the whole gate.

### Why this is mandatory, not optional

`scitex-dev ecosystem audit-all` is the *only* place where umbrella-side rules (§5b passthrough) and standalone-side rules (§3 mcp subcommands, §1a tab completion, §10 positional ordering) are checked together. Running individual `audit-cli` or `audit-mcp-tools` invocations from local shells doesn't catch the cross-package drift that's already cost the ecosystem ~16 packages × multiple commits to clean up (the 2026-05-06 sweeps).

## Release-gate checklist

Before tagging `v*`:

1. CI green on `main` (the test workflow + scitex-quality both passing).
2. `CHANGELOG.md` updated with the new version section.
3. Version bumped in `pyproject.toml` AND any `__version__.py`.
4. Local fresh-venv probe: `pip install -e ".[dev]"` then `pytest` — must mirror what CI sees.
5. `pip install` from a sibling dir without scitex installed (dep-hygiene self-check).
6. Tag pushed (`git push origin v0.1.0`) — triggers `publish-pypi.yml`.
