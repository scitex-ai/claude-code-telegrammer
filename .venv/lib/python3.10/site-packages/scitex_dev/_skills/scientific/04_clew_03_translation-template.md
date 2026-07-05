---
description: |
  [TOPIC] Per-project translation template for Clew adoption
  [DETAILS] Concrete project skeleton + step-by-step procedure for translating a `(project, dataset, research-questions)` tuple into a SciTeX project that produces a Clew-verifiable claims.json. Pairs with the playbook (`04_clew_02_translation-playbook.md`) — the playbook is the *what to do*, this is the *what to write*. Six steps: identify inputs, pre-flight checklist, scaffold, implement+iterate, validity gate, DONE. Includes the agent-vs-verifier directory split, the clean-DAG Makefile pattern, and the per-stage retry budget.
tags: [scitex-scientific-clew-translation-template]
---

# Per-project translation template

Apply once per `(project, dataset, research-questions)` tuple to bootstrap
a SciTeX project that produces a Clew-verifiable `claims.json`.

## Thesis

By requiring every claim to back-propagate through a Clew DAG to source
data, **Clew enforces that agents must have evidence — they cannot
hallucinate.** A claim with no provenance chain fails the validity gate.

## Args

| Slot | Meaning |
|---|---|
| `$ARGS[0]` | Pointer to the research questions (file path, JSON entry, doc) |
| `$ARGS[1]` | Pointer to the source dataset (capsule dir, raw data, ...) |
| `$ARGS[2]` | Working dir (e.g. `/tmp/<project>-<id>`) |

## Step 0 — Inputs

Identify, from `$ARGS[0]` + `$ARGS[1]`:

- **Questions**: verbatim strings the answer file must use as keys.
- **Scoring rule**: how an answer is judged correct (exact / interval /
  equality / LLM-judge).
- **Evidence source**: where the answers can be derived from (logs,
  results dir, raw data).
- **Oracle** (if separate): ground-truth answers, **never** exposed to
  the agent — not as a path, not as an env var, not as a container
  bind mount. The agent's project produces `claims.json`; a separate
  third-party verifier process consumes `claims.json` + the oracle and
  emits `score.json`. Even passing the oracle's location to the agent
  is a leak.

If agents will run this pipeline, mask answer values from any
agent-readable files; keep answers oracle-side only and out of the
agent's environment entirely.

## Step 1 — Pre-flight (SciTeX rules)

```
□ Read relevant SciTeX skills (scientific/, scitex-core/, scitex-io/, scitex-clew/).
□ Makefile must NOT set `SHELL := /bin/bash` (breaks @stx.session under make).
□ config/PATH.yaml: NO outer `PATH:` wrapper; values are f"..." literals.
□ @stx.session declares all 5 INJECTED params (CONFIG, COLORS, logger, plt, rngg).
□ Cross-stage I/O via stx.io.save(..., symlink_to=eval(CONFIG.PATH.X)).
□ For unknown extensions (e.g. .mmd) write directly with Path(...).write_text(...).
□ Vars consumed only by eval(CONFIG.PATH.X) need # noqa: F841.
□ Mermaid → SVG/PNG rendering needs `mmdc` + Puppeteer Chrome:
    npm i -g @mermaid-js/mermaid-cli
    npx puppeteer browsers install chrome
  Stage 05_render_dag.py auto-discovers chrome under ~/.cache/puppeteer/.
□ Scoring against degenerate prediction interval (sd=0; all reference reruns
  identical → PI half-width = 0): use `math.isclose(rel_tol=1e-9, abs_tol=1e-12)`
  as fallback so single-ULP float roundoff in JSON parse doesn't cause false FAIL.
□ stx.io.load(".txt") returns list[str] of lines, NOT a single string.
  Iterate as-is or `"\n".join(lines)` if you need flat text.
□ Tips of the DAG (root inputs and final outputs) MUST be FILES, not scripts.
  Final stage ends at `claims.json` (saved via stx.io.save), not at the script node.
□ Agent vs Verifier: scripts in scripts/agent/ are @stx.session-decorated and
  register Clew runs. Scripts in scripts/verify/ are PLAIN PYTHON (no decorator)
  so they DO NOT pollute the agent's DAG with oracle-using or visualization runs.
□ Source files with non-descriptive names (literal "output", "stdout"): COPY
  (not symlink) into a descriptive name in data/ before stage 1. Clew resolves
  symlinks to target basename, so a symlink "eval_output.txt" → real "output"
  shows up as "output" in the DAG. A real copy "eval_output.txt" shows clearly.
```

## Step 2 — Scaffold

```bash
mkdir -p $WORKDIR/{scripts,config,data/results,docs,tests/scripts}
git -C $WORKDIR init -q -b develop
# symlink inputs read-only:
ln -sfn <dataset>  $WORKDIR/data/source
# DO NOT symlink the oracle into the agent's workspace.
```

### Agent-only work; verifier is third-party

**Critical**: the agent's project contains ONLY the agent's work
(`scripts/agent/`). Scoring, rendering, and figure composition that
require the oracle are run by a separate third-party verifier
(different sac yaml, different identity, oracle access of its own).

```
scripts/
└── agent/                       # @stx.session-decorated, registers Clew runs
    ├── 01_extract.py            # evidence → metrics.csv
    ├── 02_build_answers.py      # metrics.csv → report.json
    └── 03_register_claims.py    # report.json → claims.json   (DAG terminates here)
```

Required files: `Makefile` (single phase: `solve`), `config/{PATH,PARAMS}.yaml`,
the 3 agent scripts above, `tests/scripts/.gitkeep`.

### Makefile (clean-DAG pattern, agent-only)

```make
ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
.PHONY: solve clean-clew clean
all: solve
solve: clean-clew                                   # AGENT — Clew-tracked
	python3 $(ROOT)/scripts/agent/01_extract.py
	python3 $(ROOT)/scripts/agent/02_build_answers.py
	python3 $(ROOT)/scripts/agent/03_register_claims.py
clean-clew:
	rm -f $(ROOT)/.scitex/clew/db.sqlite
clean: clean-clew
	find $(ROOT)/scripts -type d -name "*_out" -prune -exec rm -rf {} +
	rm -rf $(ROOT)/data/results/*
```

**No `verify` target inside the agent's project.** The third-party
verifier runs separately, e.g. as a sibling sac agent that consumes the
agent project's `claims.json` plus the oracle and emits `score.json`
into its own (oracle-aware) workdir.

## Step 3 — Implement + iterate

For each stage 1→4: implement → `make solve` → if failing, read the
error, revert what you don't understand, consult Step 1 checklist,
retry. **Max 3 iterations per stage.**

## Step 4 — Validity gate

```
□ Stage 3 reports n_passed == n_questions
□ Stage 4 registered N claims (= number of questions)
□ For each claim: clew.chain(<claim_value>) reaches an input file
  (the source dataset or the masked-questions file)
```

If any check fails, fix the `source_file` argument in
`clew.add_claim(...)` or the upstream symlink, and retry (max 3).

## Step 5 — DONE

`make solve` exits 0 + all validity-gate boxes ticked +
`data/results/dag.mmd` non-empty + `data/results/report.json` matches
the expected schema.

Write a one-line summary:

```json
{
  "id": "...",
  "n_questions": N,
  "n_passed": M,
  "n_claims": N,
  "n_back_propagated": N,
  "wall_clock_s": ...,
  "iterations": ...,
  "blockers": []
}
```

## Related

- [04_clew_01_dag-as-map-and-evidence.md](04_clew_01_dag-as-map-and-evidence.md) — conceptual framing
- [04_clew_02_translation-playbook.md](04_clew_02_translation-playbook.md) — universal agent prompt that drives this template
- [04_clew_04_translation-notebook-delta.md](04_clew_04_translation-notebook-delta.md) — notebook-cohort delta
- [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md) — `@stx.session` reference
