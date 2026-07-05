---
description: |
  [TOPIC] Research projects declare `project-type: research` and get a
  research-appropriate audit instead of the package-publish ruleset.
  [DETAILS] A research repo is NOT a pip package — no `src/<pkg>/`, no
  PyPI/RTD/codecov/CHANGELOG/CLA. It declares `project-type: research` in
  `.scitex/dev/config.yaml`; the auditor then SKIPS package-publish rules
  and KEEPS the universal ones (scripts↔tests/scripts mirror via RP-2xx,
  TQ001-007, NM001-003, line budgets, the audit-all gate). CI = single
  Python version + `pytest` (requires_data CI-skipped) + `scitex-dev
  linter` — no pypi/RTD/matrix/codecov.
tags: [scitex-general-ecosystem-research-project-type]
---

# Research Projects (`project-type: research`)

A SciTeX **research project** (a paper / analysis repo, not a publishable
library) declares itself so the auditor stops nagging it about
package-publishing concerns it will never have.

## Axis: `project-type`, not `category`

Research is declared on the **`project-type`** list axis in
`<repo>/.scitex/dev/config.yaml` — the same axis as `pip` / `special` /
`django` / `deferred`:

```yaml
# <repo>/.scitex/dev/config.yaml
project-type:
  - research
```

**Why this axis and not `[tool.scitex_dev] category`?** The
`category` axis (`library` / `cli-tool` / `infrastructure`, see
[01_ecosystem/09_package-categories.md](09_package-categories.md))
is a *publishable-package* self-declaration that drives workflow-presence
(PS-165) and lives in `pyproject.toml`. A research project is **not a pip
package** — it has no `src/<pkg>/`, no wheel, no `[project]` table worth
auditing, and is **not** in `scitex_dev.ECOSYSTEM`. Forcing a publish
category onto it is a category error. The `project-type` list axis already
existed for exactly this kind of repo-kind switch, and `research` was
already a recognised value with `RP`-family rule routing — so research
slots in there cleanly.

Heuristic fallback (no config file): a repo with `scripts/` + `data/` +
`config/` but no `src/<pkg>/` is auto-detected as `research`. Commit the
explicit `project-type: research` anyway — heuristics drift.

A hybrid repo (a tool package whose `examples/` *is* a research project)
may list **both**: `project-type: [pip, research]`. Then PS rules fire on
the `src/<pkg>/` side and RP rules on the `scripts/` side.

## What the auditor SKIPS for research

A pure-`research` repo (no `pip` in the list) drops every `PS-*` rule —
the `applies()` router gates `PS-*` on `pip` being present (see
[`_config/_loader.py`](../../_cli/audit/_config/_loader.py)). That removes
all the package-publish noise:

- **PyPI publish** workflow presence (PS-165)
- **RTD / Sphinx** docs bundle + config (PS-121..PS-128)
- **codecov / coverage badge** (PS-106)
- **PyPI / version badges** (PS-109, PS-143, PS-144)
- **multi-version test matrix**, **CHANGELOG / CLA** as package files
  (PS-133..PS-138)
- **smoke / e2e** layer rules (PS-211 / PS-212)

## What the auditor KEEPS for research

The universal quality rules still hold — they're not PS package-publish
rules:

| Concern | Mechanism | Notes |
| :--- | :--- | :--- |
| `scripts/` ↔ `tests/scripts/` mirror | **RP-201/202/204/205** | Research-flavoured siblings of PS-201/202/204/205. `tests/scripts/` is the mandatory mirror parent; private `_foo.py` → `test__foo.py`. W during adoption. |
| No mocks | **STX-NM001/002/003** (`scitex-dev linter`) | Universal; applies regardless of project-type. |
| Test quality (AAA + ≥3-word names + 1 assert) | **STX-TQ001-007** (`scitex-dev linter`) | Universal. |
| Per-file line budget | PostToolUse hook | Universal. |
| audit-all gate | `tests/develop/test_audit.py` | The repo still runs `scitex-dev ecosystem audit-all` as a normal test. |

The RP mirror checks fire only when `research` is in the project-types and
the repo has a `scripts/` directory; `tests/scripts/` substitutes for
`tests/<pkg>/` (full structure in
[`../scientific/02_research-project_06_project-structure-tests.md`](../../scientific/02_research-project_06_project-structure-tests.md)).

## Research project structure (summary)

```
<repo>/
├── scripts/                # primary code (analysis, pipelines) — NOT shipped
│   ├── analysis/01_collect.py
│   └── utils/_helpers.py
├── tests/
│   └── scripts/            # 1:1 mirror of ./scripts/   (RP-201 parent)
│       ├── analysis/test_01_collect.py
│       └── utils/test__helpers.py
├── config/                 # YAML params (PATH/COLORS/EXPERIMENT)
├── data/                   # gitignored (large) — .gitkeep + symlinks tracked
├── docs/                   # human docs (no Sphinx/RTD requirement)
└── .scitex/dev/config.yaml # project-type: research
```

Deep structure (per-directory conventions, `@stx.session`, `CONFIG`,
cohort datasets) lives in the
[`scientific/02_research-project_*`](../../scientific/02_research-project_01_project-structure-root.md)
leaves.

## CI expectation for research projects

A research repo's CI is intentionally lean — no pypi / RTD / matrix /
codecov. The expected workflow runs, on a **single** Python version:

```yaml
# .github/workflows/test.yml (research project)
- name: Install
  run: uv pip install -e ".[dev]"   # or a requirements file
- name: Lint
  run: scitex-dev linter check-files scripts tests
- name: Test
  run: pytest tests/ -q -m "not requires_data"
```

- **Single Python version** — research repos pin one interpreter; they
  don't ship a wheel that must work across 3.10–3.13.
- **`@pytest.mark.requires_data`** marks tests that need the (gitignored,
  often large/HPC) dataset. CI skips them with `-m "not requires_data"`;
  run them locally / on the data host. Register the marker in
  `pyproject.toml [tool.pytest.ini_options] markers`.
- **`scitex-dev linter`** enforces the universal TQ / NM / style rules on
  `scripts/` + `tests/`.
- No `pypi-publish`, no `rtd-sphinx-build`, no codecov upload, no version
  matrix. Don't add them; they have nothing to publish.

The auditor does **not** force a specific workflow filename on research
projects (PS-165 only fires for `pip`); the above is the convention, not a
hard-checked rule.

## Quick checklist (research project)

- [ ] `.scitex/dev/config.yaml` declares `project-type: research` (tracked in git).
- [ ] Primary code under `scripts/`; mirrored 1:1 by `tests/scripts/`.
- [ ] `tests/scripts/` parent exists (RP-201).
- [ ] Private `_foo.py` tested by `test__foo.py` (RP-205).
- [ ] `data/` gitignored; `config/*.yaml` tracked.
- [ ] CI = single Python + `pytest -m "not requires_data"` + `scitex-dev linter`.
- [ ] `tests/develop/test_audit.py` still runs `audit-all` (the gate).
- [ ] No PyPI / RTD / codecov / CHANGELOG / CLA scaffolding (research repos don't publish).
