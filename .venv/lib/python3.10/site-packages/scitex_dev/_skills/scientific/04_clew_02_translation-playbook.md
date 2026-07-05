---
description: |
  [TOPIC] Universal agent playbook for Clew-tracked translation
  [DETAILS] Project-agnostic system prompt for any "translate this capsule into a SciTeX project that produces a Clew-verifiable claims.json" task. The agent receives EXACTLY 4 inputs (CAPSULE_ID, CAPSULE_PATH, QUESTIONS_PATH, WORKDIR) and is NEVER given the oracle's location — scoring is performed by a separate third-party verifier process. The agent dispatches by tier (easy / notebook / medium / hard) by inspecting the capsule, builds a SciTeX project with @stx.session-decorated agent stages, registers claims as the DAG terminus, and exits with a DONE line. Loaded as a `spec.skills.required` entry on any sac agent yaml so the experiment yaml only needs to supply the 4 inputs.
tags: [scitex-scientific-clew-translation-playbook]
---

# Universal Clew translation playbook

Project-agnostic agent prompt for translating any research capsule into
a SciTeX project that produces a Clew-verifiable `claims.json`.
Cohort-, tier-, and language-specific behaviour is selected at runtime
by inspecting the inputs.

## Inputs

The agent receives **exactly 4** inputs and nothing else benchmark-specific:

```
$CAPSULE_ID         opaque capsule identifier (e.g. "capsule-1624349", "bix-1")
$CAPSULE_PATH       read-only directory or .zip containing code/data/notebook/results
$QUESTIONS_PATH     masked questions file (in-repo, GT fields = null)
$WORKDIR            agent-writable scratch directory (e.g. /tmp/clew-fleet-<id>)
```

The launcher fills these. The agent never hard-codes paths.

### Critical: the agent NEVER sees the oracle

The oracle (ground-truth answers) is **not passed to the agent in any
form** — not as a path, not as an env var, not as a binding inside the
container, not via a "for-the-verifier-only" hint in the prompt. Even
the *location* of the oracle is sufficient to compromise the masking
discipline (the agent runs as the same user as the oracle owner; mere
knowledge of the path enables anchoring of "answers" without an explicit
read).

Verifier-side scoring is the responsibility of a **separate process**
(a launcher hook, a second sac agent with its own yaml, or a CI job)
that has its own oracle access. The agent's project produces
`data/results/answers.json` and `data/results/claims.json`; a third
party reads those plus the oracle to produce `score.json`. The
agent's `make solve` target must complete without any knowledge of the
oracle's existence or location.

## Mission

Build a SciTeX project under `$WORKDIR` that:

1. **Extracts evidence** for each task question from `$CAPSULE_PATH`.
   - If `results/` exists and is non-empty → read it (easy).
   - Else if a `.ipynb` notebook exists → convert + execute (notebook).
   - Else if `REPRODUCING.md` exists → follow it, translating
     `docker → apptainer` on Spartan (medium).
   - Else → infer execution from `code/` + `data/` (hard).

2. **Builds answers.json**, keyed by `question_id` from `$QUESTIONS_PATH`.

3. **Registers Clew claims** in `data/results/claims.json`, one per
   question. The DAG terminus is `claims.json` — never a script node.

The agent's job ends at `claims.json`. **Scoring against the oracle is
out of scope for the agent.** A third-party verifier (separate process,
separate yaml, separate identity) reads `claims.json` + the oracle and
emits `score.json`.

## Required project layout under $WORKDIR

```
scripts/
└── agent/                      # @stx.session, in-DAG
    ├── 01_extract.py           # capsule → metrics / executed-notebook outputs
    ├── 02_build_answers.py     # → answers.json
    └── 03_register_claims.py   # → claims.json (DAG terminus)
config/{PATH,PARAMS}.yaml
Makefile                        # solve, clean-clew, clean — NO verify target
data/{source,results}/
```

A separate **verifier project** (different sac yaml, different identity,
oracle-mounted) consumes the agent's `claims.json` and emits
`score.json`. The verifier never lives inside `$WORKDIR` and never
writes there.

## Pre-flight (universal)

Apply on every cohort, every tier:

- Makefile must NOT set `SHELL := /bin/bash` (breaks `@stx.session`).
- `config/PATH.yaml`: NO outer `PATH:` wrapper; values are `f"..."` literals.
- `@stx.session` declares all 5 INJECTED params (`CONFIG`, `COLORS`,
  `logger`, `plt`, `rngg`).
- Cross-stage I/O via `stx.io.save(..., symlink_to=eval(CONFIG.PATH.X))`.
- DAG tips MUST be files (e.g. `claims.json` saved via `stx.io.save`),
  not script nodes.
- All figures via `stx.plt` / FigRecipe (data + style separated,
  DAG-tracked). `matplotlib.pyplot.savefig()` is forbidden — figures
  must enter the DAG as data.

## Tier dispatch (decide once at the start of stage 01)

```python
from pathlib import Path
caps = Path(CAPSULE_PATH)
results_dir = caps / "results"
has_results     = results_dir.exists() and any(results_dir.iterdir())
has_notebook    = bool(list(caps.rglob("*.ipynb")))
has_reproducing = (caps / "REPRODUCING.md").exists()

if has_results:
    tier = "easy"        # read-only — parse results files
elif has_notebook:
    tier = "notebook"    # convert → execute → parse
elif has_reproducing:
    tier = "medium"      # follow REPRODUCING.md → execute → parse
else:
    tier = "hard"        # explore code/ + data/ — last resort
```

Each tier produces the same downstream:
`extract → answers.json → claims.json`.

## Mandatory tools by tier

| Tier | Tool used in `01_extract.py` |
|---|---|
| easy | direct file reads, pandas / json |
| notebook | `scitex_notebook.convert_notebook(..., mode="unified")` then `subprocess.run(["python", "stage1.py"])` |
| medium | `apptainer exec --cleanenv --pwd /code -B <data>:/data -B <code>:/code -B <results>:/results <sif> bash run` (translated from REPRODUCING.md's `docker run ...`) |
| hard | inspect `code/` for entrypoints; do not modify capsule code |

## Scoring is third-party

The agent does NOT score. After `claims.json` exists, a separate
verifier process (out of scope of this prompt) reads it plus the oracle
and emits `score.json`. The agent must not import oracle paths, must
not have `scripts/verify/`, must not include a `verify` Make target.

For reference, the third party uses these per-`eval_mode` rules:

| Mode | Comparison |
|---|---|
| `range_verifier` / numeric | `math.isclose(rel_tol=1e-4, abs_tol=1e-9)`, with degenerate-PI fallback (`rel_tol=1e-9`) when reference sd=0 |
| `str_verifier` | case-folded, whitespace-stripped exact compare |
| `llm_verifier` | `pass=null`, `reason="LLM-judge needed"` → INCONCLUSIVE |
| oracle null | `pass=null`, `reason="oracle null"` → INCONCLUSIVE |

## Done condition

ALL of:

1. `make solve` exits 0.
2. `data/results/claims.json` is present.
3. `len(claims) == n_questions` where `n_questions = ` the count of
   question rows in `$QUESTIONS_PATH` whose `capsule_id` matches
   `$CAPSULE_ID`. **Empty claims.json with `n_questions > 0` is a
   FAILURE, not success.**
4. Each entry in `claims.json` has a non-null `answer` field. A claim
   may legitimately answer "could not extract" but it must say so
   explicitly via `{"answer": null, "reason": "<why>"}` — never just
   omit the entry.

Print on stdout exactly:

```
DONE <capsule_id> tier=<easy|notebook|medium|hard> n_claims=N
```

If `len(claims) != n_questions`, do NOT print DONE; print
`BLOCKER: <reason>` instead and exit 0 so the launcher can move on.

Pass / fail / inconclusive counts come from the third-party verifier
later — not from the agent.

## Forbidden

- Asking for, looking up, importing, environment-reading, container-mounting,
  or otherwise *referencing* the oracle's location. The agent must complete
  its task with no awareness that an oracle exists.
- Writing a `scripts/verify/` directory, a `verify` Makefile target, or any
  file named `score.py` / `scoring.json` / `oracle*` inside `$WORKDIR`.
- Writing claims with `claim_type="text"` (silently dropped by upstream
  — use `value`).
- Running figures through `matplotlib.pyplot.savefig` (no DAG entry).
- Putting heavy data anywhere under `~` on Spartan.
- Modifying the capsule files in `$CAPSULE_PATH` (read-only).

## On failure

Iterate at most 3 times per stage. If still blocked, print
`BLOCKER: <short reason>` and stop with exit zero — the reaper will reap
based on score.json absence and the launcher will move on.

## Related

- [04_clew_01_dag-as-map-and-evidence.md](04_clew_01_dag-as-map-and-evidence.md) — conceptual framing of the two modes
- [04_clew_03_translation-template.md](04_clew_03_translation-template.md) — concrete project template (the *what to write*)
- [04_clew_04_translation-notebook-delta.md](04_clew_04_translation-notebook-delta.md) — notebook-cohort delta
- [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md) — `@stx.session` reference
