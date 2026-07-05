---
description: |
  [TOPIC] Research Project Config And Data
  [DETAILS] `./config/` and `./data/` for a SciTeX research project. `./config/` is the project-scope YAML tree (`PATH.yaml`, `PARAMS.yaml`, `EXPERIMENT.yaml`, `COLORS.yaml`) auto-loaded into `CONFIG` by `@stx.session`. `./data/` holds inputs and intermediate datasets — large files gitignored, symlinks tracked. Run outputs do NOT live in `./data/` — those go under `SDIR_OUT/` (auto-created by `@stx.session`). Pairs with [`02_research-project_07_config-and-parameters.md`](02_research-project_07_config-and-parameters.md) for CONFIG semantics.
tags: [scitex-scientific-research-project-project-structure-config-and-data]
---

# `./config` and `./data`

> Sibling leaves: [`./root`](02_research-project_01_project-structure-root.md) · [`./scripts`](02_research-project_02_project-structure-scripts.md) · [`./scripts/makefile`](02_research-project_04_project-structure-makefile.md) · [`./examples`](02_research-project_05_project-structure-examples.md) · [`./tests`](02_research-project_06_project-structure-tests.md)

## `./config` — project-scope YAML tree

Centralized project parameters, loaded into `CONFIG` by `@stx.session`. **Scripts pull parameters from here rather than hardcoding.**

```
./config/
├── PATH.yaml                            # paths to data, output, references
├── PARAMS.yaml                          # numeric / categorical parameters
├── EXPERIMENT.yaml                      # experiment-specific (per condition)
└── COLORS.yaml                          # plotting palette
```

- One YAML per logical concern (cheap to override one without touching others).
- `.gitkeep` so the directory exists even when empty.
- `@stx.session` deep-merges every file into a single `CONFIG` object exposed to `main(...)`.
- Resolution chain: **direct argument → CONFIG yaml → env var → default**. See [`02_research-project_07_config-and-parameters.md`](02_research-project_07_config-and-parameters.md) for full semantics, examples, override rules.

### `PATH.yaml` — single source of truth for paths

**Mandatory** when a project has any non-trivial filesystem layout. ALL_CAPS keys; values are Python `f"..."` strings interpolated at access time via `eval(CONFIG.PATH.<KEY>)`.

**No outer `PATH:` wrapper.** The filename `PATH.yaml` already gives the namespace — `@stx.session` exposes the file's top-level keys directly under `CONFIG.PATH`. If you wrap the contents in `PATH:`, you end up with `CONFIG.PATH.PATH.<KEY>` and 100 % of your access sites break with `AttributeError`.

**Every value uses `f"..."` literal syntax — even static paths.** Scripts always do `eval(CONFIG.PATH.<KEY>)`; if a value is a plain `"./data/foo"` it parses to a Python expression `./data/foo` which is a `SyntaxError`. The `f` prefix makes it a valid Python f-string literal that evaluates to the path string (with any `{var}` interpolated against the local frame).

```yaml
# config/PATH.yaml — note the absence of an outer ``PATH:`` wrapper
# (top-level keys ARE the contents of CONFIG.PATH) and the universal
# ``f"..."`` prefix even on static paths. Both rules above strictly.

## Top-level (mostly symlinks; targets in .scitex/<pkg>/ or canonical data roots)
PAPER:    f"./paper"             # → ./.scitex/writer
CLEW:     f"./clew"              # → ./.scitex/clew
DATA:     f"./data"

## Per-cohort (f-strings interpolated against capsule_id, etc. at access time)
COHORT_A:
  ROOT:      f"./data/cohort_a_corebench"
  SRC:       f"./data/cohort_a_corebench/src"
  INVENTORY: f"./data/cohort_a_corebench/src/inventory.json"
  RAW:       f"./data/cohort_a_corebench/src/capsules/{capsule_id}.tar.gz"
  EXTRACTED: f"./data/cohort_a_corebench/src/capsules_extracted/{capsule_id}"
  CAPSULE:   f"./data/cohort_a_corebench/capsules/capsule-{capsule_nn:02d}"

## Experiment outputs (write target for stx.io.save symlink_to=...)
RESULTS:
  ROOT:      f"./data/results"
  CLEW_DEMO: f"./data/results/clew_demos/{exp_name}"
```

Rules:

- **Single source of truth** — every other location in the codebase (scripts, manuscripts, sbatch wrappers, sac yamls) reads from `CONFIG.PATH.<KEY>`, never hardcodes the same string.
- **f-string syntax in YAML** — values starting with `f"` are evaluated as Python f-strings against the local variables in scope. `@stx.session` (or its scitex-io / scitex-dev shim) handles the resolution.
- **No hardcoded absolute paths** — `/home/<user>/...` and `/data/...` literals are forbidden in scripts (lint rule RP203). Use `CONFIG.PATH.<KEY>` instead.
- **Read alongside `stx.io.save(..., symlink_to=CONFIG.PATH.RESULTS.CLEW_DEMO)`** — outputs become discoverable from `./data/` without changing where `@stx.session` writes (next to script).

### Cross-stage I/O with `symlink_to`

`stx.io.save(obj, "x.csv")` auto-routes to `<script>_out/x.csv` under the current script's SDIR_OUT. This is good for per-script provenance but breaks multi-stage pipelines where stage 2 needs to load stage 1's output without knowing stage 1's filename.

**Pattern**: every cross-stage save publishes to a fixed location via `symlink_to`:

```python
# stage 1 — extract metrics
stx.io.save(df, "metrics.csv", symlink_to=eval(CONFIG.PATH.METRICS_CSV))
# real bytes:  ./scripts/01_extract_metrics_out/metrics.csv
# symlink at:  ./data/results/metrics.csv  → real bytes

# stage 2 — load via the stable path
df = stx.io.load(eval(CONFIG.PATH.METRICS_CSV))
```

Result: every stage's outputs are simultaneously (a) namespaced under their producing script's `_out/` for provenance, and (b) discoverable from a single `./data/results/` location for downstream consumers.

### Using f-string paths in scripts

`CONFIG.PATH.<KEY>` returns the **literal f-string** (e.g. the string `'f"./data/seizures/{patient_id}.csv"'`). The caller resolves it with `eval(...)` against local variables in scope. The convention from real research projects (e.g. neurovista):

```python
import scitex as stx

@stx.session
def main(patient_id: str = "P001", CONFIG=stx.INJECTED, logger=stx.INJECTED):
    # Single value
    df = stx.io.load(eval(CONFIG.PATH.SEIZURES_CSV))
    # → resolves f"./data/seizures/{patient_id}.csv"  using local patient_id

    # Save with discoverable symlink (auto-creates ./data/results/.../result.csv → script_out/.../)
    stx.io.save(df, "result.csv", symlink_to=eval(CONFIG.PATH.RESULTS_CLEW_DEMO))

    # Glob over a templated directory (one f-string, many matches)
    capsules = stx.io.glob(eval(CONFIG.PATH.COHORT_A.EXTRACTED).replace(
        "{capsule_id}", "*"
    ))

    # Save into a templated location (e.g. per-cohort)
    summary = {"violations": 0}
    cohort = "A"
    stx.io.save(summary, eval(CONFIG.PATH.RESULTS.COHORT_RUN), force=True)
```

Rules for f-string usage:

- **Always `eval(CONFIG.PATH.<KEY>)` before passing to `stx.io.{load,save,glob}`** — never use the raw string.
- **Wrap the script with `@stx.session`** — only the session decorator deep-merges + injects `CONFIG`.
- **Local variables must be named exactly as the f-string placeholders.** `f"...{patient_id}..."` requires `patient_id` in the call frame.
- **For glob/wildcard semantics**, replace the placeholder with `"*"`: `eval(CONFIG.PATH.X).replace("{patient_id}", "*")`. Then call `stx.io.glob(resolved_pattern)`.
- **Reject unbound placeholders** — if a `{var}` is not in scope, `eval` raises `NameError`. That's correct: it surfaces missing parameters loudly instead of silently using a stale or wrong path.

### The "phantom-unused-variable" problem

`eval(CONFIG.PATH.X)` reads `patient_id` from the call frame, but to a static analyzer (`ruff F841`, `pyright reportUnusedVariable`, `vulture`) the variable looks **unused** — it's never referenced explicitly in the source. Linters will flag it, autofixers may delete it. This is the single biggest footgun of the f-string + eval pattern.

**Mandatory convention** when defining a variable solely consumed by an eval'd path:

1. **Add a `# noqa: F841` (or pyright equivalent) suppression** at the binding site.
2. **Add a one-line comment** stating which `CONFIG.PATH.<KEY>` consumes it.

```python
@stx.session
def main(patient_id: str = "P001", CONFIG=stx.INJECTED, logger=stx.INJECTED):
    # patient_id consumed by eval(CONFIG.PATH.SEIZURES_CSV) below.
    # noqa: F841 — referenced inside f-string, invisible to static analysis.

    df = stx.io.load(eval(CONFIG.PATH.SEIZURES_CSV))
    # ↑ resolves f"./data/seizures/{patient_id}.csv"
```

Or, when the consuming line is far from the binding, repeat the suppression at the binding:

```python
patient_id = picker.next()  # noqa: F841 — see eval(CONFIG.PATH.SEIZURES_CSV)
...  # 30 lines of unrelated work
df = stx.io.load(eval(CONFIG.PATH.SEIZURES_CSV))
```

**Better alternative when available**: a wrapper function that names the bindings explicitly and avoids `eval`:

```python
# Hypothetical ergonomic wrapper (if/when scitex-io exposes it):
df = stx.io.load(stx.io.resolve(CONFIG.PATH.SEIZURES_CSV, patient_id=patient_id))
```

This makes `patient_id` a *real* function argument — visible to linters, IDEs, and refactoring tools. Prefer this form when the helper is available; fall back to `eval` + suppression comment otherwise.

**Auditor rule** (research-project mode): flag any `eval(CONFIG.PATH.*)` whose preceding ~5 lines contain a binding without a `# noqa` or `# eval` marker. The fix is to add the suppression, not to remove the variable.

## `./data` — inputs + intermediate

```
./data/
├── raw/                                 # untouched inputs
├── processed/                           # outputs of an upstream pipeline; inputs for downstream
├── README.md                            # what's here, where it came from
└── <symlink>                            # → /path/on/NAS/cohort_X
```

- Project data files. **Large files gitignored.**
- Small files, `.gitkeep`, and symlinks may be tracked.
- Symlinks to artefacts let you navigate `./data/` as a centralized directory even when the bytes live elsewhere (NAS, scratch, HPC scratch).
- Provenance: each subdir or symlink should have a one-line note (in `./data/README.md` or sibling `<dir>.md`) saying where it came from.

## What does NOT go in `./data`

- **Run outputs** — those live under `SDIR_OUT/` (deterministic, per-script) or `SDIR_RUN/` (unique per invocation), auto-created by `@stx.session`. Committing run outputs to `./data/` pollutes inputs with derived artefacts.
- **External documents** — paper PDFs, third-party specs. SciTeX no longer uses a top-level `./references/` — fold provenance into `./data/<source>/README.md`.
- **Configuration** — that's `./config/`.

## Project-scope SciTeX state: `./.scitex/<pkg-short>/`

Adjacent to `./config/` and `./data/`, SciTeX packages may also keep **project-scope runtime state** under `./.scitex/<pkg-short>/`. Examples:

```
./.scitex/
├── dev/runtime/                         # scitex-dev session metadata
├── io/cache/                            # scitex-io project cache
└── cloud/                               # local data for scitex-cloud Django dev
```

- The `<pkg-short>` slug is the package name minus the `scitex-` prefix.
- Resolution chain (project-level → user-level): `<project>/.scitex/<pkg-short>/` falls back to `~/.scitex/<pkg-short>/`. See [`../general/01_ecosystem/06_dot_scitex_directory.md`](../general/01_ecosystem/06_dot_scitex_directory.md) for the full layout, `SCITEX_DIR` override, and `PathManager` usage.
- Default policy: gitignored (most contents are per-machine state). Some packages may track config files inside it — check the package's own `_skills/<pkg>/`.

## Audit hooks

The `audit-project` rules apply: `./config/` not directly checked (its presence is informational), `./data/` not directly checked. The lint rules that DO touch this area:

- `PS-102` — `./references/` is forbidden at top level (fold provenance into `./data/<source>/README.md`).
- `PS-401` — `./docs/to_claude/` must be gitignored (also applies to `./.scitex/<pkg>/runtime/` artefacts).
