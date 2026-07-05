---
description: |
  [TOPIC] Lessons learned from real research projects
  [DETAILS] Concrete mistakes encountered while building paper-scitex-clew (and earlier projects), with the rule that fixed each one. Append-only — when a new failure mode is encountered, capture it here as a one-liner with a pointer to the leaf where the rule lives. Reading this leaf at project kickoff prevents the same mistake from being made twice.
tags: [scitex-scientific-lessons-learned]
---

# Lessons Learned

Append-only log of mistakes that cost real time, and the rules that fix them. Read at project kickoff.

## Hypotheses & planning

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Wrote experiment scripts before agreeing on hypotheses | Metric produced doesn't answer any user question | [`00_planning_01_hypotheses-agreement`](00_planning_01_hypotheses-agreement.md) |
| Stated "X is better" without metric/comparator | Untestable claim; reviewer rejection risk | Hypotheses must list (observable, prediction, baseline, falsification) |
| Bundled four hypotheses; user accepts two | Time wasted on H3/H4 that user never wanted | Always send back numbered, table-formatted list; let user trim |
| Assumed reader can infer "minimal logic" | Vague hypothesis; can't be tested | Either pin to a metric or drop the H |

## Project organization

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Hard-coded parameters scattered across experiment scripts (`N_TRIALS = 100`, `LR = 1e-3`, paths) | Re-running with different values means editing N files; no single source of truth; can't sweep by config | All parameters in `./config/PARAMS.yaml` (or `EXPERIMENT.yaml`); access via `CONFIG.PARAMS.<key>` injected by `@stx.session` ([`./07_config-and-parameters`](02_research-project_07_config-and-parameters.md)) |
| Project missing `./config/` entirely | Parameters live in code; reproducibility depends on git diff of `.py` files | Mandatory `./config/{PATH,PARAMS,EXPERIMENT,COLORS}.yaml` from project init ([`./03_config-and-data`](02_research-project_03_project-structure-config-and-data.md)) |
| Project missing top-level `Makefile` | `README.md` says "run `bash scripts/cohorts/a/dataset/download.sh && python scripts/...`"; new contributors run wrong command in wrong order; pipeline reproduction undocumented | Mandatory thin top-level `Makefile` dispatching to `scripts/makefile/` targets — `make download / extract / inventory / run-pipeline / repro / eval / clean` are the standard target names ([`./04_makefile`](02_research-project_04_project-structure-makefile.md)) |
| `SHELL := /bin/bash` at top of Makefile silently breaks `@stx.session` | Pipeline scripts run fine when invoked directly via `python3 ...`, but fail with `AttributeError: 'DotDict' object has no attribute '<KEY>'` when the same command is invoked via `make`. Burns hours debugging "the same command works in two places". | Drop the `SHELL :=` line entirely; let make use its default `/bin/sh`. Bash-specific features go inside `scripts/makefile/<target>.sh` with their own shebang ([`./04_makefile` § footgun](02_research-project_04_project-structure-makefile.md#footgun-do-not-set-shell--binbash-at-the-top-of-the-makefile)) |
| `config/PATH.yaml` wrapped in outer `PATH:` namespace | Every script accesses `CONFIG.PATH.<KEY>` and crashes — turns out keys are nested at `CONFIG.PATH.PATH.<KEY>` because the YAML's outer `PATH:` got loaded as a key, not stripped | Drop the outer `PATH:` wrapper in `PATH.yaml`. Filename gives the namespace ([`./03_config-and-data` § PATH.yaml](02_research-project_03_project-structure-config-and-data.md#pathyaml--single-source-of-truth-for-paths)) |
| Static paths in `PATH.yaml` written without `f"..."` prefix | `eval(CONFIG.PATH.X)` raises `SyntaxError: invalid syntax` because plain `"./data/foo"` is parsed as a Python expression, not a string literal | Always use `f"..."` form, even for static paths: `KEY: f"./data/foo"`. The `f` prefix makes it a valid Python expression ([`./03_config-and-data` § PATH.yaml](02_research-project_03_project-structure-config-and-data.md#pathyaml--single-source-of-truth-for-paths)) |
| Cross-stage pipelines fail because stage 2 can't find stage 1's `_out/` outputs | Each `stx.io.save(obj, "x.csv")` auto-routes to `<this-script>_out/`; stage 2's `stx.io.load("x.csv")` looks at cwd → `FileNotFoundError` | Use `stx.io.save(obj, "x.csv", symlink_to=eval(CONFIG.PATH.X))` — real bytes stay under the producer's `_out/`, but a symlink at the canonical PATH-yaml location makes them discoverable from anywhere ([`./03_config-and-data` § cross-stage I/O](02_research-project_03_project-structure-config-and-data.md#cross-stage-io-with-symlink_to)) |
| `stx.io.save(text, "x.mmd")` silently does nothing for unrecognised extensions | Log says "saved" but no file lands on disk; only common formats (csv/json/pkl/png/...) are dispatched | For unknown extensions, write directly: `Path(...).write_text(content)` |
| `@stx.session def main(CONFIG=stx.INJECTED, logger=stx.INJECTED):` — only 2 of 5 INJECTED params declared | scitex-linter STX-S006 warns; some agents reject the file | Declare all 5: `CONFIG, COLORS, logger, plt, rngg` (use `stx.session.INJECTED`, not the deprecated `stx.INJECTED`) |
| Sub-directories with no `README.md` | Reader has to guess what `data/cohort_b_bixbench/notebook_convert/` is for; new contributors open arbitrary `.py` files to reverse-engineer; rationale lost on hand-off | **Every directory has a `README.md`** explaining its purpose, what files belong here, what does NOT belong here, and links to sibling/parent READMEs. Even one paragraph beats nothing. Especially required: every cohort dir, every experiment dir, every `dataset/` dir. |
| Project lacks a `./docs/` tree (only top-level README) | Methodology, hypothesis history, dataset provenance, decision logs all crammed into README or scattered; reviewers / co-authors can't find context; can't link to specific topics | Mandatory `./docs/` with topic subdirs (`docs/{benchmark_datasets,methodology,decisions}/`). README links to `docs/`, not the other way around. Pre-create at project init even if empty (use `.gitkeep`). |
| Empty directory needed at runtime (e.g. `outputs/`, `cache/`, `logs/`) but git can't track empty dirs | `git clone` on a fresh machine; pipeline fails because `mkdir -p` was assumed but missing; or developer reorganises and forgets to recreate | **Place `.gitkeep` in every empty dir that the project's runtime expects to exist**. Distinguish from gitignored output dirs (`SDIR_OUT/`) which are NOT tracked. `.gitkeep` is for "this dir is part of the project structure and must exist on clone". |
| Cohort raw data + extractions + experiment outputs all in `data/<cohort>/` flat | No way to tell what's source vs. derived; accidental edits to upstream | Two-level: `data/<cohort>/{capsules,src}/` ([`./08_cohort-datasets`](02_research-project_08_cohort-datasets.md)) |
| Cohort-specific filenames (`download_corebench.sh`) in a flat scripts/ dir | Orchestrator needs lookup table; rename = 3× the work | Cohort goes in the **path**, filename is generic ([`./10_naming-and-numbering`](02_research-project_10_naming-and-numbering.md) rule 3) |
| `tests/` empty until tests written | Structure invisible in git; people forget the mirror | Pre-create with `.gitkeep` ([`./08_cohort-datasets`](02_research-project_08_cohort-datasets.md)) |
| Top-level project dirs created ad-hoc (`GITIGNORED/` tracked accidentally) | Reviewer notes / scratch in git history | Top-level scratch dirs MUST be in `.gitignore`; check `git ls-files` after creation |
| Scattering temporary/scratch files (TODOs, reviewer notes, PDF drafts, draft hypotheses, discussion logs) across the repo | Pollute git history; reviewers see WIP state; merge conflicts on personal notes | **Convention**: a single top-level `GITIGNORED/` dir per project, listed in `.gitignore` from day one. All temporary / per-machine / per-author files go there. Subdirs by type: `GITIGNORED/{TODO.md,REVIEWERS/,DISCUSSIONS/,DRAFTS/}` |
| Experiment outputs written into `data/<cohort>/src/` | Can't tell upstream raw from our derived; loses provenance | Outputs go to `SDIR_OUT/`; `src/` is read-only convention ([`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md)) |

## Naming + numbering

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| `bix-6/` next to `bix-10/` (1-digit + 2-digit) | `ls` and `for f in *` see them in wrong order | Zero-fill to max-ID width ([`./10_naming-and-numbering`](02_research-project_10_naming-and-numbering.md) rule 1) |
| Renaming UUID dirs to ordinals (lost provenance) | Can't trace back to upstream ID without a mapping table | Symlink, don't rename ([`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md) rule 1) |
| Renumbering non-contiguous upstream IDs (`bix-43, bix-45 → bix-43, bix-44`) | Manuscript citations referring to upstream `bix-44` now invalid | Preserve gaps; ordinal width is the only normalisation ([`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md) rule 3) |

## Data integrity

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Edited a CSV in `src/capsules_extracted/` to "fix" a typo | Hash drift; provenance broken; original lost | Treat extractions as ephemeral; fix in code, never on disk |
| Stored only the extracted dirs, deleted compressed originals to save disk | Can't replicate; can't compute upstream-bytes hash for provenance | Compressed `.tar.gz`/`.zip` is canonical; extractions are derived/regenerable ([`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md) Part 2) |
| Mass-renamed files via `git mv` while `core.fileMode=false` was set | New scripts committed as 100644 (non-executable) → broken pipeline on next pull | Use `git update-index --chmod=+x`; install pre-commit hook to auto-mark `.sh`/`.src` as +x |
| Tried to "fix" the storage layer's `-32768` sentinel by rewriting the DB | Other consumers (integer-typed binary protocols, downstream DB schemas) break; sentinel was intentional | Convert sentinel → `np.nan` at the figure layer on read; treat the storage-layer sentinel as a contract, not a bug ([`figrecipe/22_nan-sentinel-on-read`](https://github.com/ywatanabe1989/figrecipe/blob/develop/src/figrecipe/_skills/figrecipe/22_nan-sentinel-on-read.md)) |

## Figures (publication-bound)

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Used `np.random.randn` to populate a "representative" figure in a paper draft | Synthetic figure traveled into slides / Slack / the PDF; reviewer caught the placeholder one revision before submission | Real-data-only policy for publication figures; fail loud (raise / non-zero exit) when real data missing; synthetic OK only in `synthetic_*` fixtures ([`./01_figures_03_no-synthetic-data-policy`](01_figures_03_no-synthetic-data-policy.md)) |
| `make_example_figure()` helper swallowed `FileNotFoundError` and rendered a stub | A "polite" placeholder figure shipped in an internal report; co-author thought it was the real result | Helper must propagate the error; refuse to write the file; never silently substitute synthetic data ([`./01_figures_03_no-synthetic-data-policy`](01_figures_03_no-synthetic-data-policy.md)) |
| Heatmap comparison with per-panel `vmin`/`vmax` "for clarity" | Visual comparison meaningless; reviewer requested redraw | Shared `vmin`/`vmax`, shared colorbar across compared panels ([`./01_figures_01_standards`](01_figures_01_standards.md), figrecipe `21_figure-prep-playbook`) |
| Hard-coded `SUBJECT_ID = 7` for the "representative example" because subject 7 looked good | Cherry-pick encoded in the pipeline; cohort change does not propagate; reviewer challenges criterion | Representative-example criterion in `CONFIG.REPRESENTATIVE.*` (median / nearest-mean / first-passing-quality), re-derived on every render; show cohort distribution alongside (figrecipe `21_figure-prep-playbook` rule 4) |
| Raw `-32768` (int16 min) values reached `vmin=data.min()` and crushed the colormap | Heatmap rendered as a single dark pixel surrounded by uniform background; "the figure is broken" — actually the sentinel leaked | Convert sentinel → `np.nan` immediately after load; use `np.nanmin`/`np.nanmax`; `cmap.set_bad("white")` for heatmaps (figrecipe `22_nan-sentinel-on-read`) |

## Tooling / dotfiles / fleet

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Stale shell session (started before dotfile fix deployed) doesn't see new env vars | "Works for me" / "doesn't work for me" inconsistencies on same host | `exec bash -l` in any pane that pre-dates the fix; or close+reopen tmux |
| Wrong `sac`/CLI version in PATH after venv activation | Subcommand "not found" even though installed | Activate the right venv before assuming `which <tool>` is correct |
| `direnv` not installed → manually `source .env` every shell | Stale env, forgotten env, project-leak across cd | Per-machine `direnv` install; `.envrc` per project |
| Per-project `.env` accidentally committed with secrets | Token leak in git history | `.env` in `.gitignore` from day one; secrets via `~/.bash.d/secrets/` |

## Communication

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Long prose answers with embedded options | User has to parse to find decision points | Numbered Q1/Q2 with a)/b) options + recommendation + tradeoffs table |
| Asking three questions in one turn | User answers one, agent loses the others | Cap at 1–2 decisions per turn ([`general/03_interface_*`](../general/03_interface/00_overview.md)) |
| Saying "untestable" when paired-arms make it testable | Wrong rejection of valid hypothesis | If a comparator + metric exist, it's testable — "vague" ≠ "untestable" |

## How to add to this list

When something costs you (or the user) > 15 min and the cause is structural (not domain-specific):

1. Add a one-row entry in the relevant section above.
2. Link to the leaf that codifies the fix; if no leaf yet, **write one** before adding the lesson.
3. Append-only: do not delete past lessons even if the failure mode is now impossible — the entry serves as a "this is why we have this rule".
