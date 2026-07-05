---
description: |
  [TOPIC] Package Repo Layout And Structure
  [DETAILS] How a single `scitex-*` repo lives on disk — repo-root rules and allowed files, `src/<pkg>/` layout with absolute imports and public/private filename convention, `./scripts/` maintenance code, the makefile per-target dispatcher, numbered `examples/` with committed `_out/`, the `tests/<pkg>/` mirroring rules, GitHub Actions CI/PyPI/CLA workflows + workflow naming + presence + secret-env-prefix, repository-level quality, Playwright browser-automation debug capture (PA-305), per-package `.venv/` isolation, codecov wiring, the no-mocks rule (STX-NM/PA-306), the test-quality family (STX-TQ), and cron management. Use when creating, auditing, or reviewing a package's on-disk structure.
tags: [scitex-general-package-index]
---

# Package Repo Layout (SciTeX) — Index

How does *this* `scitex-*` package's repo live on disk? Audience: package
authors. Presupposes the ecosystem-wide rules
([../01_ecosystem/SKILL.md](../01_ecosystem/SKILL.md)).

## Sections

1. [01_project-structure-root.md](01_project-structure-root.md) — Repo-root rules, allowed files, forbidden top-level dirs, `./docs/`, `./templates/` wheel-vs-git, pre-release checklist
2. [02_project-structure-src.md](02_project-structure-src.md) — `src/<pkg>/` layout, absolute imports, cascade direction, public/private filename convention
3. [03_project-structure-scripts.md](03_project-structure-scripts.md) — `./scripts/` for maintenance + scientific analysis (not shipped); graduation to `examples/` or `src/`
4. [04_project-structure-makefile.md](04_project-structure-makefile.md) — `./scripts/makefile/` per-target dispatcher pattern + canonical target inventory
5. [05_project-structure-examples.md](05_project-structure-examples.md) — Numbered examples + `_out/` artefacts committed + `00_run_all.sh` + matched `tests/examples/test_*.py`
6. [06_project-structure-tests.md](06_project-structure-tests.md) — `tests/<pkg>/` mandatory parent, allowed subdirs, public/private mirroring, `audit-project` rules
7. [07_github-actions.md](07_github-actions.md) — CI, PyPI publish, CLA, reusable workflow patterns
8. [07b_workflow-presence.md](07b_workflow-presence.md) — Required-workflow presence checks
9. [08_quality.md](08_quality.md) — Repository-level quality (AGPL, Four Freedoms, README rules, GitHub setup)
10. [09_browser-automation-debugging.md](09_browser-automation-debugging.md) — Playwright debug-artifact capture for every browser-automation file (PA-305 rule)
11. [10_dev-venv-isolation.md](10_dev-venv-isolation.md) — Real isolated `<pkg-root>/.venv/` per peer; CI-parity local dev setup
12. [11_ci-and-codecov.md](11_ci-and-codecov.md) — CI test.yml + codecov.yml + badge wiring; `if: always()` so coverage uploads on failure
13. [12_no-mocks.md](12_no-mocks.md) — No `unittest.mock`/`pytest-mock`/`monkeypatch`; replacement menu; enforced by STX-NM001/002/003 + PA-306
14. [12_workflows-naming.md](12_workflows-naming.md) — Workflow file naming convention
15. [13_test-quality.md](13_test-quality.md) — TQ family — descriptive name, AAA marker comments, one assertion; enforced by STX-TQ001-007
16. [14_workflow-secret-env-prefix.md](14_workflow-secret-env-prefix.md) — Secret/env-prefix rules inside workflows
17. [15_cron-management.md](15_cron-management.md) — Cron / scheduled-task management for package maintenance
