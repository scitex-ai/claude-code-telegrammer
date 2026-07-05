---
description: |
  [TOPIC] Naming + numbering conventions
  [DETAILS] Three rules for consistent, sortable, scriptable identifiers across a research project. (1) **Zero-fill all numbering** to the width of the maximum value so file managers / `ls` / glob loops sort lexicographically the same as numerically. (2) **Mirror naming between scripts/, tests/, data/** — same path shape, same names, so any tool that resolves one resolves the others by string transform. (3) **Cohort context lives in the path, not the filename** — `scripts/cohorts/a_corebench/dataset/download.sh` not `scripts/cohorts/download_corebench.sh`; this lets generic tooling target any cohort by path interpolation. Pairs with [`./08_cohort-datasets`](02_research-project_08_cohort-datasets.md) and [`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md).
tags: [scitex-scientific-research-project-naming-numbering]
---

# Naming + numbering conventions

> Sibling leaves: [`./08_cohort-datasets`](02_research-project_08_cohort-datasets.md) · [`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md)

Three rules. All three serve the same goal: make the project's IDs predictable enough that **scripts and humans treat them identically**.

## Rule 1 — Zero-fill all numbering

Pad every numeric identifier to the width of the maximum value in its sequence:

| Sequence max | Width | Examples |
|---|---|---|
| ≤ 9 | 1 | `step-1`, `step-9` |
| 10–99 | 2 | `capsule-01`, `bix-43`, `exp-07` |
| 100–999 | 3 | `problem-001`, `task-099`, `bix-205` |
| 1000+ | 4+ | `subject-0001`, `trial-0123` |

Why this is non-negotiable:

```
unpadded                        zero-filled
bix-1                           bix-01
bix-10                          bix-02
bix-11                          bix-03      ← lex-sort = numeric-sort
bix-2                           ...
bix-20                          bix-10
bix-3                           bix-11
                                ...
                                bix-43
```

`ls`, `for f in *`, file managers, GUI explorers, and human eyes ALL break on the unpadded form. Unicode collation, locale, glob expansion order — none of them rescue you. Zero-fill is the only fix.

### What to zero-fill

- **Cohort capsule/problem IDs**: `capsule-01..49`, `bix-01..61`, `problem-01..05`.
- **Experiment numbering**: `exp-01_pipeline.py`, `exp-02_analysis.py`.
- **Step numbering** in numbered analysis pipelines: `01_load.py`, `02_clean.py`, `99_report.py`.
- **Skill leaves**: `01_figures_01_standards.md`, `02_research-project_07_config-and-parameters.md` (this file).
- **Subject / trial / session IDs**: `subject-0001`, `session-007`.

### What NOT to zero-fill

- Upstream IDs that are themselves opaque (UUIDs, hashes, accession codes). Don't pad those — wrap with a zero-filled ordinal symlink (see [`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md) for the symlink convention).
- Version strings (`v1`, `v2.0.3`).
- Year/date components (`2026`, not `02026`).

### Migration from un-padded existing IDs

When fixing an existing project: rename in one atomic commit, update every literal reference (path strings in scripts, config YAMLs, manuscript citations, claim IDs). Lint with:

```bash
rg '[a-z]+-[0-9]+\b' --files-with-matches  # find any 1-9-digit unpadded ID; fix or whitelist
```

## Rule 2 — Mirror naming across `scripts/`, `tests/`, and (often) `data/`

Same path shape under each top-level dir:

```
scripts/cohorts/a_corebench/dataset/extract.sh
tests/scripts/cohorts/a_corebench/dataset/test_extract.py     # mirror
data/cohort_a_corebench/                                     # mirrored cohort name (with cohort_ prefix)
```

Why:
- Any tool that targets `scripts/cohorts/a_corebench/dataset/` finds the test fixtures by string-replacing `scripts/` → `tests/scripts/`.
- Any cohort-A regression in `scripts/cohorts/a_corebench/...` has its tests in the matching path — no global search.
- Adding a new cohort (D) means creating one new branch in each of `data/`, `scripts/cohorts/`, `tests/scripts/cohorts/` with the same name.
- `.gitkeep` empty mirrors so the structure is in git from day one (see [`./08_cohort-datasets`](02_research-project_08_cohort-datasets.md)).

## Rule 3 — Cohort/group context belongs in the path, not the filename

```
GOOD                                                BAD
scripts/cohorts/a_corebench/dataset/download.sh     scripts/cohorts/download_corebench.sh
scripts/cohorts/b_bixbench/dataset/extract.sh       scripts/cohorts/extract_bixbench.sh
scripts/cohorts/c_biomysterybench/dataset/extract.sh scripts/cohorts/extract_bmb.sh
```

Why:

- An orchestrator at `shared/download_all_cohorts.sh` can call `<cohort>/dataset/download.sh` by interpolating the cohort name — **no per-cohort lookup table**.
- Adding cohort D means dropping `cohorts/d_<short-id>/dataset/{download,extract}.sh` — file names stay identical.
- Tab-completion and grep-by-filename work consistently across cohorts.
- `git mv` for renames is a one-line directory rename, not 30 file renames.

## Anti-patterns

- ❌ `bix-6/` next to `bix-10/` (mixed widths break sort).
- ❌ `download_corebench.sh`, `download_bixbench.sh`, `download_bmb.sh` in a flat dir (cohort context redundant in filename when path encodes it).
- ❌ `tests/test_cohort_a.py` (flat tests dir) when `scripts/cohorts/a_corebench/` is structured (mirror lost).
- ❌ Renumbering when upstream IDs are non-contiguous (lose traceability — see [`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md) rule 3).
- ❌ "Just one digit, we'll never have more than 9" — projects always grow past N=9.

## Quick checklist

When adding any new ID/name to the project:

1. Is it a number? → zero-fill to the sequence's max width.
2. Does it belong to a group (cohort, experiment, subject)? → put the group in the path, not the name.
3. Is there a parallel under `tests/` and `data/`? → mirror the path.
4. Is the ID upstream-derived (UUID/random)? → wrap with an ordinal symlink, don't rename the target.
