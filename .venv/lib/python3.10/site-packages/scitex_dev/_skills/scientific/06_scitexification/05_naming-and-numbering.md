---
description: |
  [TOPIC] Scitexification Stage 5 — Naming and numbering
  [DETAILS] Stage 5 of the 5-stage scitexification arc: ad-hoc filenames
  (`cnn_v3_final_FIXED2.py`) become zero-filled, sortable, stage-ordered
  script names (`scripts/03_cnn.py`) mirrored under `tests/`; opaque IDs
  and ordinals gain readable symlink aliases per
  `02_research-project_09`. Filename hygiene is load-bearing, not
  cosmetic: the run order, the test-mirror audit, and human navigation
  all key off it. This is the last, strictly-additive stage.
tags: [scitexification, scitexification-naming]
---

# Stage 5 — Naming and numbering

The hygiene step, and the one most often skipped — wrongly. Stage 5 makes
the pipeline's **order legible from the filenames alone** and mirrors the
script tree under `tests/` so `audit-project` can catch drift. It is
purely additive: nothing about the science changes; the *numbers* in the
filenames just get zero-filled and the names get descriptive.

> **What changes**: filenames and their ordinal prefixes; the `tests/`
> mirror.
> **What stays the same**: your filenames as a *concept*; the numbers
> themselves (after zero-fill).

## Script naming

```
BEFORE                          AFTER
cnn_v3_final_FIXED2.py           scripts/03_cnn.py
preprocess.py                    scripts/01_preprocess.py
extract features.py              scripts/02_extract_features.py
plot_results (copy).py           scripts/04_plot_results.py   # verify-side: scripts/verify/
```

Rules:
- **Zero-filled, sortable ordinal prefix** (`01_`, `02_`, …) so `ls`
  and `make` walk the pipeline in execution order.
- **Snake_case, descriptive, no version cruft** — drop `_final`,
  `_FIXED`, `_v3`, `(copy)`; git is the version history.
- **One responsibility per script**; the ordinal is the stage.
- **Mirror under `tests/`**: `scripts/03_cnn.py` →
  `tests/scripts/test_03_cnn.py`. The mirror is what lets
  `audit-project` detect an untested script.

## IDs and ordinals → readable symlinks

Opaque run IDs / hashes keep their canonical form but gain a readable
symlink alias, so humans navigate by meaning and tooling keeps the
stable id (per `../02_research-project_09`):

```
runs/run-7038571/                ← canonical (stable, machine)
runs/experiment-a_dataset-easy/  → run-7038571   (readable alias)
```

Apply the same to figure/table ordinals (`Figure 1` ↔ the script that
emits it) so the float manifest reads in plain language.

## Why this is load-bearing (not cosmetic)

- **Run order**: `make` / a glob executes `01_ → 02_ → 03_`; a mis-named
  `cnn_v3.py` runs out of order or not at all.
- **Repro**: `make repro` and the clew DAG assume the on-disk order
  matches the data dependency; bad names desync them.
- **Audit**: the `tests/` mirror only catches gaps if names correspond;
  an unmirrored `final_FIXED.py` is an untested script that hides.
- **Navigation**: a reviewer reads the pipeline from `ls scripts/`.

Stage 5 exists because filename hygiene is the cheapest thing to skip and
the most expensive to retrofit once downstream tooling and a manuscript
point at the old names.

## Worked example

```
BEFORE                                AFTER
analysis/                             scripts/
  load.py                               01_load.py
  model_final.py                        02_model.py
  fig_maker_v2.py                       03_make_figures.py   (or scripts/verify/)
(no tests)                            tests/scripts/
                                        test_01_load.py
                                        test_02_model.py
```

## Follow-up

- The canonical ID-readability + data-immutability rules live in
  [`../02_research-project_09_id-readability-and-data-immutability.md`](../02_research-project_09_id-readability-and-data-immutability.md)
  and the naming/numbering reference
  [`../02_research-project_10_naming-and-numbering.md`](../02_research-project_10_naming-and-numbering.md).
- The `tests/` mirror contract →
  [`../02_research-project_06_project-structure-tests.md`](../02_research-project_06_project-structure-tests.md).
- Stages 1–4 are the substance; Stage 5 makes their on-disk result
  legible and auditable. It can land in its own PR after 1–4.

See also: [`00_playbook.md`](00_playbook.md),
[`SKILL.md`](SKILL.md) (the 5-stage table).
