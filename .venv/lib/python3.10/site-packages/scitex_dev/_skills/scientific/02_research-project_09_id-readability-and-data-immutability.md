---
description: |
  [TOPIC] ID readability + raw-data immutability
  [DETAILS] Two paired conventions for ingesting external data into a research project. (1) Map random/UUID upstream IDs (e.g. `CapsuleData-0923d260-...-79ed`, `capsule-7038571`) to readable ordinal IDs (`bix-01`, `capsule-01`) via symlinks — provenance preserved in the symlink target, ergonomics in the link name. (2) Keep raw-upstream data **compressed** (`.tar.gz`, `.zip`, HF snapshot dirs) so it cannot be accidentally edited by scripts or humans; extract into a mirrored sibling tree (`src/capsules/` → `src/capsules_extracted/`) that IS writable but is gitignored and regenerable. For very large datasets, defer extraction or work directly from compressed via streaming readers. Pairs with [`./08_cohort-datasets`](02_research-project_08_cohort-datasets.md).
tags: [scitex-scientific-research-project-id-readability-data-immutability]
---

# ID readability + raw-data immutability

> Two conventions that travel together because they share the same target dir (`data/<cohort>/src/`). Sibling: [`./08_cohort-datasets`](02_research-project_08_cohort-datasets.md).

## Part 1 — UUID/random ID → readable ordinal via symlink

External datasets often use opaque IDs:

| Source | Example upstream ID |
|---|---|
| HuggingFace BixBench | `CapsuleData-0923d260-fe1b-4fb4-4398-79edf546e584` |
| Princeton CORE-Bench | `capsule-7038571` |
| OpenNeuro / DANDI | `ds002336`, `dandi:000004` |
| Generic | random hashes, accession codes |

These are unreadable in scripts, untyped in conversation ("the bix-six-something one"), and break lex-sort. Wrap them with a per-cohort ordinal:

```
data/<cohort>/
├── capsules/
│   ├── capsule-01 -> ../src/capsules_extracted/capsule-7038571
│   ├── capsule-02 -> ../src/capsules_extracted/capsule-0220918
│   └── ...
└── src/capsules_extracted/
    ├── capsule-7038571/    # extraction of upstream tarball; UUID in path = provenance
    ├── capsule-0220918/
    └── ...
```

### Rules

1. **Symlink, not rename.** The target dir keeps the upstream ID; only the link is short. `readlink capsules/capsule-01` gives provenance instantly.
2. **Zero-pad to the cohort's max-ID width.** 49 capsules → `capsule-01..49`; 99 → `001..099`. So lex-sort = numeric-sort.
3. **Preserve gaps in non-contiguous upstream IDs.** If BixBench skips `bix-44`, your ordinal sequence skips `bix-44` too. Renumbering breaks traceability.
4. **One source of truth: the inventory.** A tracked `inventory.json` in `src/` records the upstream-ID ↔ ordinal mapping. Symlinks are derived; `extract.sh` rebuilds them from inventory.
5. **Don't put symlinks under `src/`.** `src/` is for raw upstream + extractions. Symlinks live one level up at `data/<cohort>/capsules/` so the project's "human-facing" capsules dir is decoupled from immutable upstream.

## Part 2 — Raw data stays compressed

External raw data lands in `data/<cohort>/src/capsules/` as **compressed archives** (`.tar.gz`, `.zip`) or HF-snapshot subdirectories. It is **read-only by convention and by inability**:

- A `.tar.gz` cannot be partially edited; modification means re-creation. So accidental `vim` / `sed -i` / "just patch this one CSV" can't happen.
- The compressed form is the bit-for-bit object that everyone else (auditors, reviewers, replication studies) can re-fetch from the upstream URL.
- Hash of the compressed file is the canonical "what data was used" provenance. Any extraction's hash drifts (timestamp metadata, fs-dependent inode order); the original archive's hash is stable.

### Extraction is a mirrored sibling tree

`extract.sh` writes into a sibling dir, **never overwriting `src/capsules/`**:

```
data/<cohort>/src/
├── capsules/                 # COMPRESSED — read-only convention
│   ├── capsule-7038571.tar.gz
│   └── capsule-0220918.tar.gz
└── capsules_extracted/       # EXTRACTED — writable, gitignored, regenerable
    ├── capsule-7038571/
    └── capsule-0220918/
```

Mirror invariants:
- `src/capsules/` and `src/capsules_extracted/` have **the same set of names** (modulo extension).
- Deleting `capsules_extracted/<id>` and re-running `extract.sh` reproduces the working tree from the compressed source.
- Both are gitignored. Inventory + small derived metadata (`summary.json`, `kernelspec_audit.csv`) are tracked.

### When the extraction is too big to keep on disk

For datasets > 50 GB or > 100k files where double-storing (compressed + extracted) is infeasible:

| Option | When | Tradeoff |
|---|---|---|
| **a) Stream from compressed** | Whole-file random access not needed | Reading is per-archive (tar/zip iteration); slower but zero extra disk |
| **b) On-demand extraction** | Only a subset is touched per run | `extract.sh` accepts an ID list; extracts only what's requested; deletes after run |
| **c) Single-instance via symlink** | Compressed already extracted by upstream snapshot | `capsules_extracted/<id>` is a symlink into HF cache; doesn't double-store |
| **d) Full upfront extraction** (default) | Dataset < 50 GB and disk has room | Simplest; faster scripts; uses 2× disk |

Document the choice in `src/README.md` and pick (d) unless disk budget says otherwise.

## Audit

`scitex-dev ecosystem audit-project --data` (planned) checks:

1. Every `data/<cohort>/src/capsules/` is non-empty (raw artefacts present).
2. Every entry in `src/capsules/` has a corresponding extraction or stream-strategy note in `src/README.md`.
3. No `.py` / `.csv` / `.json` files written under `src/capsules/` or `src/capsules_extracted/` by experiment scripts (those go to `SDIR_OUT/`).
4. All `data/<cohort>/capsules/<ordinal>` are symlinks pointing into `src/capsules_extracted/`.
5. Every symlink target exists on disk (no dangling links).
