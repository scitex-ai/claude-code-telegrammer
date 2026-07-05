---
description: |
  [TOPIC] GitHub Actions workflow presence (per package category).
  [DETAILS] Required baseline of workflow files every SciTeX package must
  ship, keyed on `[tool.scitex_dev] category`. Audited by PS-165 (severity
  W during adoption). Companion to 02_package/07_github-actions.md (canonical
  content) and 02_package/12_workflows-naming.md (filename grammar).
tags: [scitex-general-package-workflow-presence]
---

# Workflow Presence (SciTeX)

## Required baseline (all categories)

| Workflow                                               | Filename pattern (PS-164)                          | Why                                       |
|--------------------------------------------------------|----------------------------------------------------|-------------------------------------------|
| CLA Assistant                                          | `cla.yml`                                          | Pinned by the CLA bot.                    |
| pytest matrix                                          | `pytest-*-on-*.yml`                                | The unit-test gate.                       |
| Import smoke                                           | `import-smoke-*-on-*.yml`                          | `pip install` + `python -c "import X"`.   |
| PyPI publish on tag                                    | `pypi-publish-*-on-tag.yml`                        | Trusted-publisher OIDC release.           |
| scitex-dev quality audit                               | `scitex-dev-quality-audit-on-*.yml`                | Ecosystem-wide audit-all gate.            |
| Sync main → release tag                                | `sync-main-to-release-tag-on-push.yml`             | Branch-protection-friendly release shim.  |
| RTD Sphinx build *(only when `docs/` ships)*           | `rtd-sphinx-build-on-*.yml`                        | RTD docs build sanity.                    |

The RTD requirement is gated on the presence of a `docs/` tree (with
`conf.py` at `docs/conf.py` or `docs/source/conf.py`). Packages without
docs don't ship the build workflow.

## `cli-tool` category — extra workflows

Packages declaring `[tool.scitex_dev] category = "cli-tool"` additionally
ship:

| Workflow              | Filename pattern                              | Why                                                                 |
|-----------------------|-----------------------------------------------|---------------------------------------------------------------------|
| Runtime CLI smoke     | `sdk-runtime-smoke-on-*.yml` or               | Exercises the installed CLI end-to-end on a fresh runner, catching  |
|                       | `cli-smoke-on-*.yml`                          | packaging / entry-point breakage that unit tests miss.              |

Note: the `tests/smoke/` and `tests/e2e/` *pytest* layers (PS-211 / PS-212)
are a separate concern — they live inside the test suite. The CLI runtime
smoke workflow is the GitHub Actions sibling that runs the installed
console_script.

## `library` and `infrastructure` categories

No extra workflows beyond the baseline.

## Audit (PS-165)

`PS-165` (severity `W` during adoption) reads `[tool.scitex_dev] category`
from `pyproject.toml` (defaults to `library`) and verifies every required
filename pattern matches at least one file under `.github/workflows/`.
Emits one violation per missing workflow.

Promote to E once the ecosystem has converged on the baseline.
