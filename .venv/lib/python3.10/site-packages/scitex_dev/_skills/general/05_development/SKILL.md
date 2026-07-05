---
description: |
  [TOPIC] Development Version Control And Release
  [DETAILS] How a `scitex-*` package is versioned, audited, and shipped — branch/tag/release-wave workflow and release gates, running `audit-all` continuously while editing (cron / tmux / agent loops + JSON contract), release automation + ecosystem sync CLI/MCP/Python API, skills self-explain quality measure, the doc-surface precedence map, subprocess coverage wiring, the demo smoke-test harness, the 30%→90% coverage-push playbook, the per-peer no-mocks + test-quality migration playbook, the package-maintenance prompt, and dependency tiers. Use when cutting a release, setting up audit loops, or pushing coverage.
tags: [scitex-general-development-index]
---

# Development (SciTeX) — Index

Version control, periodic audits, release. Audience: package authors and
ecosystem maintainers. Sits atop the docs tier
([../04_docs/SKILL.md](../04_docs/SKILL.md)).

## Sections

1. [01_version-control.md](01_version-control.md) — Branches, tags, release waves, release gates (core workflow)
2. [02_periodic-audits.md](02_periodic-audits.md) — Run `audit-all` continuously while editing — cron / tmux / agent loops, JSON contract, Claude Code mechanisms
3. [03_release-automation.md](03_release-automation.md) — Automation commands, ecosystem sync CLI, MCP tools, Python API
4. [04_skills-self-explain.md](04_skills-self-explain.md) — Quality measure for skill content
5. [05_doc-surfaces.md](05_doc-surfaces.md) — Which documentation surface beats which
6. [06_subprocess-coverage.md](06_subprocess-coverage.md) — Subprocess coverage wiring (parallel + COVERAGE_PROCESS_START + `.pth` shim)
7. [07_demo-smoke-tests.md](07_demo-smoke-tests.md) — Parametrised smoke test over every `_demo_*.py` and `__main__`-bearing module
8. [08_coverage-push-playbook.md](08_coverage-push-playbook.md) — End-to-end playbook for taking a package 30% → 90% Codecov without `omit` shortcuts
9. [09_ecosystem-tq-migration.md](09_ecosystem-tq-migration.md) — Per-peer migration playbook for the no-mocks + test-quality rules; four-pass sequence, dispatch template, rollback contract
10. [10_package-maintenance-prompt.md](10_package-maintenance-prompt.md) — Reusable package-maintenance prompt
11. [11_dependency-tiers.md](11_dependency-tiers.md) — Dependency tier model
