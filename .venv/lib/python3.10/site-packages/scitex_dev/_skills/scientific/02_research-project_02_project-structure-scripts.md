---
description: |
  [TOPIC] Research Project Scripts
  [DETAILS] `./scripts/` is the **primary code location** for a SciTeX research project — analysis pipelines, model-training runs, exploratory data work. Pipelines entered via `@stx.session` so `CONFIG`, `SDIR_OUT`, `SDIR_RUN`, `logger`, `plt` are auto-injected. Helpers in `./scripts/utils/`. Pipelines that produce a result worth keeping land artefacts under `SDIR_OUT/` (auto-created per script). The `./scripts/makefile/` Makefile-target subdir is documented separately.
tags: [scitex-scientific-research-project-project-structure-scripts]
---

# `./scripts` — the primary code location

> Sibling leaves: [`./root`](02_research-project_01_project-structure-root.md) · [`./config + ./data`](02_research-project_03_project-structure-config-and-data.md) · [`./scripts/makefile`](02_research-project_04_project-structure-makefile.md) · [`./examples`](02_research-project_05_project-structure-examples.md) · [`./tests`](02_research-project_06_project-structure-tests.md)

## Purpose

A research project's `./scripts/` is what `./src/` is to a package. Pipelines, analyses, model-training runs all live here.

```
./scripts/
├── makefile/                            # Makefile target backing scripts (separate leaf)
├── dataset/                             # data prep — download / extract / build_inventory / inspect
├── io/                                  # I/O helpers — readers/writers shared across analyses
├── utils/                               # helpers shared across multiple scripts
├── <experiment-name>/                   # one subdir per substantive experiment / analysis lane
│   ├── 01_load_and_summarize.py
│   ├── 02_run_models.py
│   └── _shared.py                       # private; tested as test__shared.py
└── one_off/
    └── inspect_2026-04-30.py            # ad-hoc; .dev/ is also fine
```

**Standard subdir set for any research project**:

| Subdir | Role |
|---|---|
| `dataset/` | Acquire + stage the data (download, extract, inventory, sanity-inspect). One subdir level deeper than this when there are ≥ 2 cohorts: `scripts/cohorts/<cohort>/dataset/` (see [`./08_cohort-datasets`](02_research-project_08_cohort-datasets.md)). |
| `io/` | Cross-experiment readers/writers — e.g. `load_subject(N)`, `save_pac_results(...)`. Imported, not invoked. |
| `utils/` | Cross-experiment helpers (math, plotting, path resolvers). Imported, not invoked. |
| `makefile/` | Files invoked by the project's Makefile (separate leaf). |
| `<experiment-name>/` | One per substantive analysis lane (`pac/`, `power_spectrum/`, `clew/`). Numbered scripts inside (`01_*`, `02_*`, ...). |

The `dataset/`, `io/`, `utils/` triad is the **stable foundation** a research project starts with. Experiment subdirs accrete as the project grows.

**Real-world examples**:
- `~/proj/neurovista/scripts/{dataset,io,utils,pac,power_spectrum,clew}/` — single-cohort project; experiment subdirs are domain analyses.
- `~/proj/paper-scitex-clew/scripts/cohorts/{a_corebench,b_bixbench,c_biomysterybench,shared}/dataset/` — multi-cohort project; the `dataset/` triad nests one level deeper.

## Entry-point pattern: `@stx.session`

Each substantive script is entered via `@stx.session`. The decorator injects `CONFIG`, `SDIR_OUT`, `SDIR_RUN`, `logger`, `plt` — see [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md) for the full semantics.

```python
# scripts/analysis/01_load_and_summarize.py
import scitex as stx

@stx.session
def main(
    data_path: str = "./data/raw.parquet",
    n_samples: int = 100,
    CONFIG=stx.session.INJECTED,
    SDIR_OUT=stx.session.INJECTED,
    plt=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    df = stx.io.load(data_path).head(n_samples)
    fig = plt.figure(); df.plot(ax=fig.gca())
    stx.io.save(fig, SDIR_OUT / "summary.png")
    return 0
```

Why `@stx.session`:
- Auto-CLI from the function signature (every parameter becomes a flag).
- `CONFIG` resolved from `./config/*.yaml` with deep-merge + CLI/env override.
- `SDIR_OUT` deterministic per script, `SDIR_RUN` unique per invocation.
- Reproducibility metadata (git sha, python version, config snapshot) saved automatically.

## `./scripts/utils/`

Helpers used across multiple scripts go here. Not exposed via any public API.

```
./scripts/
├── utils/
│   ├── _io_helpers.py                   # private (note the underscore)
│   └── _date_parsing.py
├── analysis/
│   ├── 01_collect_data.py               # imports from ../utils/_io_helpers
│   └── 02_summarize.py
```

If a util gets imported from `./examples/` or starts being broadly useful → graduate it to a real package.

## Tests for scripts

Substantial scripts get tests under `./tests/scripts/` (mirrors `./scripts/`, see [02_research-project_06_project-structure-tests.md](02_research-project_06_project-structure-tests.md)):

```
scripts/analysis/run_pipeline.py        →  tests/scripts/analysis/test_run_pipeline.py
scripts/analysis/_helper.py             →  tests/scripts/analysis/test__helper.py
```

Throwaway one-offs in `./scripts/one_off/` don't need tests; if you find yourself wanting one, that's a signal to graduate the code to `./scripts/analysis/` (or to `./examples/`).

## Numbered prefixes

Numbered prefixes (`01_<name>.py`) are encouraged for analysis pipelines — same convention as `./examples/`. The order encodes pipeline stage:

```
scripts/analysis/01_collect_data.py
scripts/analysis/02_clean.py
scripts/analysis/03_train_model.py
scripts/analysis/04_evaluate.py
```

Once stable, a `00_run_all.sh` dispatcher in the same dir lets you re-run the whole pipeline.

## Output discipline: `SDIR_OUT/` vs `SDIR_RUN/`

Use `SDIR_OUT` (deterministic — same script → same path) for figures, summary tables, processed data the next run should clobber. Use `SDIR_RUN` (unique per invocation) for logs, full-state snapshots, anything you want to keep across reruns. Don't write run-specific artefacts under `./data/` (that's for inputs).

See [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md) for the canonical pattern.
