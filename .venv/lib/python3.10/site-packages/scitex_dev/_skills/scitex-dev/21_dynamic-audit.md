---
description: |
  [TOPIC] Dynamic Audit
  [DETAILS] Design skeleton for dynamic ecosystem audits — agent-driven end-to-end research tasks that exercise the full SciTeX stack under realistic workloads. Paired with static audits (scitex-python 99_checklist §§1–15) to form a two-gate quality regime: static gates commit, dynamic gates release.
tags: [scitex-dev-dynamic-audit]
---

# Dynamic Audit Skeleton (§16 of 99_checklist)

**Status: design skeleton.** Not yet implemented — lists task dataset, infra requirements, and metrics so the first pass can be scoped independently.

## Purpose

Static audits catch structural / API regressions cheaply. They cannot catch:

- Skill-trigger regressions (agent stops invoking `stx.io.save` when README rewrites change phrasing)
- Cross-package workflow regressions (paper draft compiles but bibliography lookup silently returns stale data)
- Tool-use distribution drift (same task now takes 3× the tool calls after a CLI flag rename)
- Error-recovery regressions (agent loops on new error messages it doesn't know)

Dynamic audits run real research-shaped tasks against an agent and measure observable behaviour.

## Two-gate regime

| Gate | Audit class | Triggers |
|---|---|---|
| **Commit** | static (checklist §§1–15 + playbook §98) | every push to develop |
| **Release** | dynamic (this file) | before a PyPI release wave, before a grant milestone |

Static passing is necessary but not sufficient for a release.

## Task dataset (to be built)

Each task is a runnable prompt + expected artifact set. Target 8–12 tasks covering the cascade's main directions:

| ID | Task category | Example |
|---|---|---|
| T01 | Paper-draft compile | "Write a 200-word abstract for ω, save with `stx.writer.compile`, report figure count" |
| T02 | Data pipeline | "Load `data/signal.npz`, run bandpass 5–40 Hz, save with `stx.io.save`" |
| T03 | Statistical test | "Given two arrays, pick the right test via `stx.stats` and report effect size" |
| T04 | Figure composition | "Compose two line plots side-by-side at 80mm width via figrecipe" |
| T05 | BibTeX enrichment | "Fetch metadata for DOI X via `stx.scholar`, append to refs.bib" |
| T06 | PDF full-text | "Download the paper for DOI Y and extract the IMRaD sections" |
| T07 | Notebook verify | "Re-run `analysis.ipynb` and confirm hashes match `stx.clew`" |
| T08 | Container launch | "Build an Apptainer image via `stx.container.apptainer.build`" |
| T09 | Multi-pkg cascade | "Plot confusion matrix via `stx.plt`, save with `stx.io`, verify reproducibility via `stx.clew`" |
| T10 | CLI composition | "Run `scitex scholar search` → `scitex bibtex enrich` piped via shell" |

## Execution infrastructure

- **Container substrate:** `scitex-agent-container` (newbie-docker image) to guarantee identical environment across runs
- **Runner:** spawn `claude -p` with `--allowedTools` pinned per task
- **Transcript capture:** per-task JSONL log (tool calls, stdout, exit code, wallclock)
- **Artifact capture:** per-task output directory, diffed against golden reference

## Metrics (per task, aggregate across ecosystem)

| Metric | Captured from | Interpretation |
|---|---|---|
| Pass/fail | artifact-vs-reference diff | binary — task completed correctly |
| Tool-call count | transcript JSONL | efficiency — lower is better, flag 1.5× regressions |
| Tool-call distribution | transcript JSONL | did the agent take the intended path? |
| Error-recovery depth | transcript JSONL | how many retries before success |
| Wallclock | runner | latency budget — flag 1.5× regressions |
| Skill triggers | transcript JSONL | did the correct `stx.*` skills activate? |

## Output

After each dynamic-audit run append to
`scitex-dev/quality-audits/YYYY-MM-DD-dynamic.md`:

- task ID, pass/fail, tool-call count, wallclock
- diff from previous run
- regression flags (any metric > 1.5× prior)

Dashboard script (§17 of 99_checklist) should read these and add a
"dynamic" column to the ecosystem table.

## Scope for a minimal first pass

To unblock release-gate use before the full task dataset exists:

1. Pick 3 tasks (T02 data-pipeline, T03 stats, T09 multi-pkg cascade)
2. Run weekly
3. Track pass/fail + tool-call count only
4. Block release if any regress

Full coverage is a quarter-long effort; start with this minimum.
