---
description: |
  [TOPIC] Research Project Makefile
  [DETAILS] Makefile + `./scripts/makefile/` pattern for a SciTeX research project — same convention as for packages. Root Makefile is a thin one-line dispatcher per target; logic lives as standalone shell scripts under `./scripts/makefile/`. Targets here lean toward analysis lifecycle (run-pipeline, repro, eval) more than packaging (build/upload-pypi). For the full pattern, see the package equivalent and reuse the same scripts where applicable.
tags: [scitex-scientific-research-project-project-structure-makefile]
---

# `./scripts/makefile/` — Makefile target backing scripts (research project)

> Sibling leaves: [`./root`](02_research-project_01_project-structure-root.md) · [`./scripts`](02_research-project_02_project-structure-scripts.md) · [`./config + ./data`](02_research-project_03_project-structure-config-and-data.md) · [`./examples`](02_research-project_05_project-structure-examples.md) · [`./tests`](02_research-project_06_project-structure-tests.md)

## Same pattern as packages

Same convention as for SciTeX packages — see [`../general/02_package/04_project-structure-makefile.md`](../general/02_package/04_project-structure-makefile.md) for the full rationale. The root `Makefile` is a thin dispatcher; each target's actual logic lives as one script per target under `./scripts/makefile/`:

```
./scripts/makefile/
├── install.sh                           # install dev deps
├── test-changed.sh
├── test-full.sh
├── coverage-html.sh
├── lint.sh
├── clean.sh
├── docs.sh                              # sphinx-build + refresh src/<pkg>/_sphinx_html/ if applicable
├── run-pipeline.sh                      # research-specific: re-run the analysis pipeline
├── repro.sh                             # research-specific: re-run with frozen CONFIG
└── eval.sh                              # research-specific: aggregate metrics across runs
```

Root `Makefile`:

```make
.PHONY: install test-changed test-full coverage-html lint clean docs \
        run-pipeline repro eval

install:        ; @./scripts/makefile/install.sh
test-changed:   ; @./scripts/makefile/test-changed.sh
test-full:      ; @./scripts/makefile/test-full.sh
coverage-html:  ; @./scripts/makefile/coverage-html.sh
lint:           ; @./scripts/makefile/lint.sh
clean:          ; @./scripts/makefile/clean.sh
docs:           ; @./scripts/makefile/docs.sh
run-pipeline:   ; @./scripts/makefile/run-pipeline.sh
repro:          ; @./scripts/makefile/repro.sh
eval:           ; @./scripts/makefile/eval.sh
```

## Research-specific targets

Beyond the standard set, research projects often want:

| Target | What it does |
| :--- | :--- |
| `run-pipeline` | Walk `./scripts/analysis/0[1-9]_*.py` in order via `00_run_all.sh` |
| `repro` | Re-run the pipeline with a frozen `CONFIG` snapshot (e.g. from `SDIR_RUN/<run-id>/`) |
| `eval` | Aggregate metrics across runs into `./eval/<date>/` |
| `figures` | Re-render publication figures (often a thin wrapper around `./examples/`) |

What's typically **dropped** vs the package set:

- `build`, `upload-pypi-test`, `upload-pypi`, `release` — research projects aren't shipped to PyPI.

## Script template

Use the same bash template as packages — see [`../general/02_package/04_project-structure-makefile.md`](../general/02_package/04_project-structure-makefile.md#script-template). Logs land under `./tests/logs/`.

## Footgun: do NOT set `SHELL := /bin/bash` at the top of the Makefile

When a Makefile target invokes a `@stx.session`-decorated Python script and the Makefile has `SHELL := /bin/bash`, the session decorator fails to resolve `CONFIG.PATH` and raises `AttributeError: 'DotDict' object has no attribute '<KEY>'`. Running the same Python command from the same shell directly works fine.

Root cause: `SHELL := /bin/bash` changes how make's recipes evaluate environment + cwd inheritance under certain make versions, and scitex's session decorator depends on the inherited environment to locate `./config/`. Empirically dropping the line (so make uses its default `/bin/sh`) fixes it.

```make
# WRONG — breaks @stx.session under make
SHELL := /bin/bash

.PHONY: solve
solve:
	python3 scripts/01_extract_metrics.py
	python3 scripts/02_build_report.py        # ← AttributeError on CONFIG.PATH.X
```

```make
# RIGHT — drop the SHELL line; default /bin/sh works
.PHONY: solve
solve:
	python3 scripts/01_extract_metrics.py
	python3 scripts/02_build_report.py
```

If you genuinely need bash features (arrays, `[[ ]]`), put them in a `./scripts/makefile/<target>.sh` with `#!/bin/bash` shebang and have the Makefile target call that script. Don't change the Makefile's SHELL.
