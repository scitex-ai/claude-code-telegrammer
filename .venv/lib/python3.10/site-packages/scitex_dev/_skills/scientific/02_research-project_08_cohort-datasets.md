---
description: |
  [TOPIC] Cohort-based dataset organization
  [DETAILS] How to lay out `./data/`, `./scripts/`, and `./tests/` when a research project consumes multiple external benchmark datasets (cohort A/B/C/...). Uniform per-cohort tree: `data/<cohort>/capsules/` = ordinal symlinks for human-readable access, `data/<cohort>/src/` = raw upstream artefacts (downloads, inventory, README), per-cohort scripts under `scripts/cohorts/<cohort>/dataset/{download,extract,build_inventory,inspect_capsule}.{sh,py}` with parallel `tests/scripts/cohorts/<cohort>/dataset/` mirror. Zero-pad ordinal IDs to the cohort's max-ID width for lexicographic/numeric alignment. Pairs with [`./03_config-and-data`](02_research-project_03_project-structure-config-and-data.md) and [`./scripts`](02_research-project_02_project-structure-scripts.md).
tags: [scitex-scientific-research-project-cohort-datasets]
---

# Cohort-based dataset organization

> Sibling leaves: [`./root`](02_research-project_01_project-structure-root.md) · [`./scripts`](02_research-project_02_project-structure-scripts.md) · [`./config + ./data`](02_research-project_03_project-structure-config-and-data.md) · [`./tests`](02_research-project_06_project-structure-tests.md)

## When to use

A project that **consumes ≥ 2 external benchmark datasets** (e.g. CORE-Bench + BixBench + BioMysteryBench) needs a uniform layout so that scripts, tests, and downstream verification (Clew DAGs, claim registration) can target *any* cohort by the same path conventions.

If the project has **one** dataset, prefer the simpler `data/raw/`, `data/processed/` pattern in [`./03_config-and-data`](02_research-project_03_project-structure-config-and-data.md). The cohort layout is overhead until you have N ≥ 2.

## Naming convention

Cohort dirs at the top of `./data/` are named `cohort_<letter>_<short-id>`:

```
data/
├── cohort_a_corebench/
├── cohort_b_bixbench/
└── cohort_c_biomysterybench/
```

- `<letter>` (`a`, `b`, `c`, ...) gives stable ordinals so manuscripts, claim IDs, and figures can refer to "cohort A" without depending on the dataset's branding.
- `<short-id>` is the dataset's canonical short name (`corebench`, `bixbench`, ...).

## Per-cohort directory tree

Every cohort has the **same two top-level dirs** under it:

```
data/cohort_<letter>_<short-id>/
├── capsules/             # human-facing access — ORDINAL SYMLINKS only
└── src/                  # immutable raw upstream artefacts
    ├── capsules/         # raw downloads (.tar.gz, .zip, HF snapshot dirs)
    ├── capsules_extracted/  # extractions (one dir per upstream ID)
    ├── inventory.json    # tracked: per-cohort metadata
    └── README.md         # tracked: cohort description + provenance
```

### `capsules/` — ordinal symlinks

Top-level `capsules/` contains **only symlinks** named with ordinal IDs:

```
data/cohort_a_corebench/capsules/
├── capsule-01 -> ../src/capsules_extracted/capsule-7038571
├── capsule-02 -> ../src/capsules_extracted/capsule-0220918
└── ...
```

Why symlinks, not copies:
- One source of truth (the extraction in `src/`).
- Cheap to recreate (e.g. when a new ordinal scheme is needed).
- Manuscripts and scripts use the short ordinal (`capsule-01`); provenance is one `readlink` away.

### `src/` — raw upstream

`src/` is **read-only by convention**. No experiment writes here. All experimental outputs go under `SDIR_OUT/` per the standard `@stx.session` pattern.

Tracked under git: `inventory.json`, `README.md`, small derived metadata files (e.g. `summary.json`, `kernelspec_audit.csv`).
**Gitignored**: `src/capsules/` (raw blobs), `src/capsules_extracted/` (extractions). See [`./.gitignore`](#gitignore-pattern) below.

## Padding policy

Zero-pad ordinal IDs to **the width of the cohort's maximum ID**:

| Cohort max ID | Width | Example |
|---|---|---|
| ≤ 9      | 1 | `capsule-7` |
| 10 – 99  | 2 | `capsule-01`, `capsule-49` |
| 100 – 999| 3 | `problem-001` |

Padding ensures `ls`-order matches numeric order and that string sort is stable. Document the rule in the cohort's `src/README.md`.

If the upstream uses non-contiguous IDs (e.g. BixBench short_ids skip from 43 to 45), preserve the gap — don't renumber. The ordinal IS the upstream short_id; padding only normalises the width.

## Per-cohort scripts

Mirror the cohort layout under `./scripts/cohorts/`:

```
scripts/cohorts/
├── a_corebench/
│   ├── dataset/
│   │   ├── build_inventory.py    # rebuilds src/inventory.json from upstream metadata
│   │   ├── download.sh           # fetches src/capsules/* from upstream
│   │   ├── extract.sh            # unpacks src/capsules/* → src/capsules_extracted/*; refreshes capsules/* symlinks
│   │   └── inspect_capsule.py    # @stx.session-wrapped staging-and-print for one capsule (sanity check)
│   └── <experiment-name>/        # per-experiment subdirs created lazily as experiments are run
│       ├── run.py
│       └── run_out/              # gitignored SDIR_OUT
├── b_bixbench/
│   └── (same dataset/ + per-experiment shape)
├── c_biomysterybench/
│   └── (same dataset/ + per-experiment shape)
└── shared/
    ├── _build_summary.py         # cross-cohort aggregation helpers (private, leading underscore)
    └── download_all_cohorts.sh   # orchestrator — calls each cohort's dataset/download.sh
```

### Required per-cohort `dataset/` files

| File | Purpose | Idempotent? |
|---|---|---|
| `download.sh` | Fetch raw artefacts from upstream into `data/<cohort>/src/capsules/` | yes (skip-if-present) |
| `extract.sh` | Unpack into `src/capsules_extracted/`; refresh ordinal symlinks at `capsules/` | yes |
| `build_inventory.py` | (optional) Regenerate `src/inventory.json` from upstream metadata | yes |
| `inspect_capsule.py` | (optional) Pick first capsule, print structure + plan; useful for debugging | yes |

**Filename uniformity**: do NOT use cohort-specific names like `download_corebench.sh`. The cohort context comes from the *path*, not the filename. This way the orchestrator at `shared/download_all_cohorts.sh` can call `<cohort>/dataset/download.sh` without a cohort-specific lookup table.

### Shared orchestrator pattern

```bash
# scripts/cohorts/shared/download_all_cohorts.sh
for cohort in a_corebench b_bixbench c_biomysterybench; do
    bash "$SCRIPTS/cohorts/$cohort/dataset/download.sh" || \
        echo "[$cohort] orchestrator: download failed"
done
```

Private helpers in `shared/` start with `_` (e.g. `_build_summary.py`) — same convention as Python's "use this only via the public wrapper".

## Tests mirror

`tests/` mirrors `scripts/` structure exactly:

```
tests/
└── scripts/
    └── cohorts/
        ├── a_corebench/dataset/.gitkeep
        ├── b_bixbench/dataset/.gitkeep
        ├── c_biomysterybench/dataset/.gitkeep
        └── shared/dataset/.gitkeep
```

Empty mirror dirs are tracked with `.gitkeep` so the structure is in git from day one. As actual `test_*.py` files land, drop `.gitkeep`.

## `.gitignore` patterns

Per-cohort raw data is gitignored. Tracked: inventory + README + small JSON metadata.

```gitignore
# Cohort raw data — bulk benchmark downloads, not source-controlled.
# Each cohort dir keeps inventory.json + README.md tracked; everything
# below (raw blobs, capsule extractions, HF snapshots) is ignored.
data/cohort_*/src/capsules/
data/cohort_*/src/capsules_extracted/

# Cohort experiment outputs (regenerated each run; large)
scripts/cohorts/*/dataset/inspect_capsule_out/
scripts/cohorts/*/<experiment-name>_out/
```

## Dataset README — necessary and sufficient

Every `data/<cohort>/src/README.md` (and any standalone dataset README) must be **necessary and sufficient**:

- **Necessary**: contains every fact a re-runner / reviewer needs to understand the dataset's identity, layout, and provenance.
- **Sufficient**: nothing more. No marketing prose, no aspirational paragraphs, no "we plan to also...".

### Required sections (in this order)

```markdown
# Cohort <X> — <Short name> (<Source institution>)

## Identity
- Source: <upstream URL / repo / DOI>
- Version / snapshot date: <YYYY-MM-DD or commit hash>
- Citation: <BibTeX key or one-line ref>
- License: <SPDX or upstream wording>
- Access: <public | gated (how to request) | local-only>

## Size and contents
- Items: N capsules / problems / subjects (after dedup)
- Disk: ~XX GB compressed, ~YY GB extracted
- Languages / file types: <Python N, R M, notebooks K, data-only L>
- Naming: capsule-NN -> upstream-id (zero-padded; see padding policy)

## Layout
\```
data/<cohort>/
├── capsules/         (ordinal symlinks — human-facing)
└── src/
    ├── capsules/     (raw upstream artefacts; read-only convention)
    ├── capsules_extracted/  (extractions; gitignored, regenerable)
    ├── inventory.json
    └── README.md     (this file)
\```

## How to (re)acquire
- Download:    `bash scripts/cohorts/<cohort>/dataset/download.sh`
- Extract:     `bash scripts/cohorts/<cohort>/dataset/extract.sh`
- Inventory:   `python scripts/cohorts/<cohort>/dataset/build_inventory.py`
- Inspect one: `python scripts/cohorts/<cohort>/dataset/inspect_capsule.py`

## Padding policy
<one line — width and rationale; e.g. "2 digits because max upstream ID = 49">

## Caveats
<known issues, gotchas, broken upstream items, license restrictions on derivatives, etc.>
```

### What to leave out

- ❌ The motivation for why this paper exists (that's the project README).
- ❌ Upstream's marketing copy. Link instead.
- ❌ How to interpret the data scientifically (that's per-experiment README under `scripts/cohorts/<cohort>/<experiment>/README.md`).
- ❌ Future-work bullets ("we will also add..."). Tracked in TODO/issues, not the dataset README.
- ❌ Step-by-step running of experiments. README documents the *dataset*; the Makefile documents how to run.

### Audit checklist

- [ ] All seven required sections present.
- [ ] Every command in "How to (re)acquire" actually runs as written.
- [ ] Padding policy line matches actual `capsules/<id>` widths.
- [ ] No section longer than ~5 lines unless absolutely necessary.

## Anti-patterns

- ❌ Top-level `data/<cohort>/capsules/` is a **real directory** with extractions inside. Use symlinks; keep extractions in `src/capsules_extracted/`.
- ❌ Cohort-specific filenames in `scripts/cohorts/<cohort>/dataset/` (`download_corebench.sh`). Use generic names; cohort context is the path.
- ❌ Renumbering when upstream IDs are non-contiguous (`bix-43, bix-45 → bix-43, bix-44`). Preserve gaps for traceability.
- ❌ Writing experiment outputs into `src/`. `src/` is immutable upstream; writes go to `SDIR_OUT/`.
- ❌ Skipping the `tests/` mirror until tests exist. Pre-create with `.gitkeep` so the project layout is uniform from the first cohort.

## Audit

`scitex-dev ecosystem audit-project` (planned) checks:
1. Every `data/cohort_*/` has both `capsules/` and `src/`.
2. Every `capsules/<id>` is a symlink resolving inside `src/capsules_extracted/`.
3. Every cohort has matching `scripts/cohorts/<cohort>/dataset/` and `tests/scripts/cohorts/<cohort>/dataset/` dirs.
4. `inventory.json` parses and matches the symlink set.
5. No real (non-symlink) dirs under `capsules/`.
