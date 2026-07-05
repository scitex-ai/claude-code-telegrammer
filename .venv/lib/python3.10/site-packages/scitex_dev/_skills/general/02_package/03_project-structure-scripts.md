---
description: |
  [TOPIC] Package Scripts
  [DETAILS] `./scripts/` for a SciTeX *package* — maintenance and scientific analysis (research scripts, one-off pipelines). Not shipped. Free to depend on the full SciTeX umbrella, third-party tools, anything. Helpers used by multiple scripts go in `./scripts/utils/`. The `./scripts/makefile/` subdir is documented separately in [02_package/04_project-structure-makefile.md](04_project-structure-makefile.md). Anything that produces a result worth keeping should graduate into `./examples/` (as a demo) or `./src/` (as a public API).
tags: [scitex-general-package-project-structure-scripts]
---

# `./scripts` — maintenance or scientific analysis

> Sibling leaves: [`./root`](01_project-structure-root.md) · [`./src`](02_project-structure-src.md) · [`./scripts/makefile`](04_project-structure-makefile.md) · [`./examples`](05_project-structure-examples.md) · [`./tests`](06_project-structure-tests.md)

## Purpose

Project maintenance + scientific analysis. **Not shipped** in the wheel.

- Maintenance: release helpers, repo-cleanup scripts, agent prompts, CI helpers.
- Scientific analysis: research scripts, one-off pipelines, exploratory data work.
- Free to depend on the full SciTeX umbrella, third-party tools, anything.

## Layout

```
./scripts/
├── makefile/                    # Makefile target backing scripts (separate leaf)
├── utils/                       # helpers used by multiple scripts
├── analysis/                    # scientific analysis pipelines (optional)
│   └── 01_<descriptive-name>.py
└── <ad-hoc>.py                  # one-off scripts
```

- Numbered prefixes (`01_<name>.py`) are encouraged for analysis pipelines — same convention as `./examples/`.
- Each substantial script entered via `@stx.session` so `CONFIG`, `SDIR_OUT`, `SDIR_RUN`, `logger`, `plt` are auto-injected (see `_skills/scientific/02_research-project_02_config-and-parameters.md`).

## Tests for scripts

Substantial scripts get tests under `./tests/scripts/` (mirrors `./scripts/`). See [02_package/06_project-structure-tests.md](06_project-structure-tests.md).

```
scripts/analysis/run_pipeline.py        →  tests/scripts/analysis/test_run_pipeline.py
scripts/analysis/_helper.py             →  tests/scripts/analysis/test__helper.py
```

Throwaway one-offs don't need tests; if you find yourself wanting one, that's a signal to graduate the code (see below).

## Graduation: scripts → examples or src

When a script produces a result worth keeping:

- **Move to `./examples/`** if it's a demo of a feature → numbered, with `_out/` committed, with a matching `tests/examples/test_*.py`. See [02_package/05_project-structure-examples.md](05_project-structure-examples.md).
- **Move to `./src/<pkg>/`** if it's a function the package should expose publicly → put it under `__all__`, write proper docstrings, add `tests/<pkg>/test_<name>.py`. See [02_package/02_project-structure-src.md](02_project-structure-src.md).

The graduation step is what keeps `./scripts/` from accumulating dead code.

## `./scripts/utils/`

Helpers used by multiple scripts go here. Not exposed via the package's public API.

```
./scripts/
├── utils/
│   ├── _io_helpers.py
│   └── _date_parsing.py
├── analysis/
│   ├── 01_collect_data.py        # imports from ../utils/_io_helpers
│   └── 02_summarize.py
```

If a util ends up imported from `./examples/` or starts being useful for end-users → graduate it to `./src/<pkg>/`.
