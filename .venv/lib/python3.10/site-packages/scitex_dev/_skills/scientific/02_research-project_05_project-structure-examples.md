---
description: |
  [TOPIC] Research Project Examples
  [DETAILS] `./examples/` for a SciTeX research project — same convention as for packages. Numbered prefix (`01_<descriptive-name>.{py,sh,ipynb}`), `_out/` artefacts committed to git, `00_run_all.sh` dispatcher, matched 1:1 by `tests/examples/test_<stem>.py`. Less common in research projects than in packages, but valuable for showcasing how the project's pipelines are invoked.
tags: [scitex-scientific-research-project-project-structure-examples]
---

# `./examples` — runnable demos (research project)

> Sibling leaves: [`./root`](02_research-project_01_project-structure-root.md) · [`./scripts`](02_research-project_02_project-structure-scripts.md) · [`./config + ./data`](02_research-project_03_project-structure-config-and-data.md) · [`./scripts/makefile`](02_research-project_04_project-structure-makefile.md) · [`./tests`](02_research-project_06_project-structure-tests.md)

## Same convention as packages

The shape, numbering, `_out/` policy, and `00_run_all.sh` dispatcher are identical to the package side — see [`../general/02_package/05_project-structure-examples.md`](../general/02_package/05_project-structure-examples.md). The differences are scope-related, listed below.

```
./examples/
├── 00_run_all.sh
├── 01_invoke_pipeline.py
├── 01_invoke_pipeline_out/
├── 02_make_figure.py
└── 02_make_figure_out/
```

## What goes here in a research project

- **Demos of how the project's pipelines are invoked.** A reader who lands on the GitHub repo should be able to run `00_run_all.sh` and reproduce the headline result.
- **Figure regeneration** demos that re-create publication figures from frozen `CONFIG` + frozen data.
- **`@stx.session`-decorated scripts** — same pattern as in `./scripts/`; examples are thin wrappers around analysis pipelines plus narrative text.

## What goes in `./scripts/` instead

- One-off analyses, exploratory work, intermediate artefacts → those belong in `./scripts/` (not shipped, not part of the demo surface). See [`02_research-project_02_project-structure-scripts.md`](02_research-project_02_project-structure-scripts.md).

## Output policy

Same as packages — sibling `_out/` directories committed:

```
examples/01_invoke_pipeline.py
examples/01_invoke_pipeline_out/                # git-tracked
    ├── summary.png
    └── metrics.json
```

Don't commit `SDIR_RUN/<run-id>/` artefacts (those are session-unique). Use `SDIR_OUT` for stable demo outputs.

## 1:1 match with `tests/examples/`

Every example file has a matching `tests/examples/test_<stem>.py`. PS-303 of `audit-project` flags missing tests.

```
examples/01_invoke_pipeline.py          →  tests/examples/test_01_invoke_pipeline.py
examples/02_make_figure.py              →  tests/examples/test_02_make_figure.py
```

The test's job is to confirm the example runs to completion and the expected `_out/` artefacts land.

## When research projects skip `./examples/`

If the project has *one* canonical pipeline and no separate "demo" surface, a single `examples/01_run.py` that calls the same pipeline with the canonical `CONFIG` is fine. Don't manufacture demos that just duplicate `./scripts/` — that's churn.
