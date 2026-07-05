---
description: |
  [TOPIC] Research Project Tests
  [DETAILS] `./tests/` for a SciTeX research project — pytest-driven, same convention as for packages but the source tree being mirrored is `./scripts/` (not `./src/`). Mandatory `tests/scripts/` parent. Allowed sibling subdirs (examples/agentic/integration/e2e/github_actions/coverage/results/logs/reports/custom). Public/private filename convention with double-underscore for private. Same `audit-project` rule set (PS-201–PS-206 with `tests/scripts/` substituted for `tests/<pkg>/`, plus PS-302/PS-303).
tags: [scitex-scientific-research-project-project-structure-tests]
---

# `./tests` — pytest-driven, mirrors `./scripts`

> Sibling leaves: [`./root`](02_research-project_01_project-structure-root.md) · [`./scripts`](02_research-project_02_project-structure-scripts.md) · [`./config + ./data`](02_research-project_03_project-structure-config-and-data.md) · [`./scripts/makefile`](02_research-project_04_project-structure-makefile.md) · [`./examples`](02_research-project_05_project-structure-examples.md)

## Mandatory `tests/scripts/` parent

A research project's primary code lives in `./scripts/`, so `./tests/scripts/` is the mandatory mirror parent (analogous to `tests/<pkg>/` for packages). PS-201 fires when it's missing.

```
scripts/                            tests/scripts/
├── analysis/                       ├── analysis/
│   ├── 01_collect.py               │   ├── test_01_collect.py
│   ├── 02_summarize.py             │   ├── test_02_summarize.py
│   └── _shared.py                  │   └── test__shared.py             (private → double __)
└── utils/                          └── utils/
    └── _io_helpers.py                  └── test__io_helpers.py
```

## Public / private filename convention

A leading underscore in the source marks the module **private**. The mirroring test uses **double underscore** between `test` and the basename — same as for packages (PS-205 enforces it):

| Source | Test |
| :--- | :--- |
| `scripts/analysis/run.py` | `tests/scripts/analysis/test_run.py` |
| `scripts/analysis/_helper.py` | `tests/scripts/analysis/test__helper.py` |
| `scripts/utils/_PathBuilder.py` | `tests/scripts/utils/test__PathBuilder.py` |

## Allowed `tests/` subdirectories

| Subdir | Tracked? | Mirrors / contains |
| :--- | :--- | :--- |
| `tests/scripts/` | ✅ | 1:1 mirror of `./scripts/` (the bulk of unit tests) |
| `tests/examples/` | ✅ | one `test_<example-stem>.py` per file in `./examples/` |
| `tests/agentic/` | ✅ | agentic-trigger tests — LLM invokes a Skill / MCP tool / CLI and we assert the right path fires |
| `tests/integration/` | ✅ | cross-script / cross-module tests |
| `tests/e2e/` | ✅ | end-to-end pipeline tests (full `data → result` runs) |
| `tests/github_actions/` | ✅ | local GitHub Actions runner config (`act`/Apptainer) |
| `tests/coverage/` | gitignored | HTML / XML coverage reports |
| `tests/results/` | gitignored | general test-run artifacts spanning topics (coverage data files, captured payloads, fixture output) |
| `tests/logs/` | gitignored | pytest run logs, captured stdout/stderr |
| `tests/reports/` | optional | agent-generated test summaries |
| `tests/custom/` | ✅ | tests with no script counterpart |

## Allowed at `tests/` root

A small set of meta-tests at the top level (anything else triggers PS-203):

```
tests/
├── conftest.py
├── __init__.py
├── test_examples.py                # walks ./examples/, runs each
├── test_skills_quality.py
├── test_integration.py             # legacy (prefer tests/integration/)
├── test_reproduce.py
├── test_units.py
├── test_api.py
└── scripts/                        # mandatory parent
```

## Auditor coverage

Same `audit-project` rule set as for packages — see [`../general/02_package/06_project-structure-tests.md`](../general/02_package/06_project-structure-tests.md#auditor-coverage). For research projects, "src/<pkg>/" in the rule descriptions is replaced by "scripts/".

## Tests against `CONFIG` snapshots

Research-specific testing patterns:

- Snapshot a `CONFIG` resolution and assert it's stable across reruns (catches accidental config drift).
- Run a small slice of the pipeline against a tiny synthetic dataset under `./tests/scripts/<stage>/test_<stage>.py`.
- Use `tests/e2e/` for the full-pipeline test (slow; CI-only).

## Historical: `sync_tests_with_source.sh` and source-as-comments

The legacy `tests/sync_tests_with_source.sh` script (in `~/proj/scitex-python/`) auto-creates missing test files and mirrors the directory structure. It also embedded source code as comments at the bottom of every test file — that pattern is now considered too noisy and should be dropped. The auditor (`audit-project`) is read-only and never writes test files.
