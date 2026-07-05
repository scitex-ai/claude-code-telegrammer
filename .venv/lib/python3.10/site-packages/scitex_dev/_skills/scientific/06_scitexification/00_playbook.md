---
description: |
  [TOPIC] Universal scitexify playbook — the layer-agnostic translation act.
  [DETAILS] Canonical playbook for **scitexification**: the act of taking ANY scientific problem (a script, a notebook, a small repo, a paper supplement, a published analysis) and translating it into a SciTeX project — canonical structure, `@stx.session` discipline, DAG/pipeline conventions, source-grounded outputs — then re-solving it within that structure. This leaf is the GENERAL layer: it COINS the vocabulary (`scitexify` verb / `scitexification` noun) and fixes the universal contract. Experiment-specific layers (experiment-specific evaluation/scoring/output gates, etc.) live separately and compose ON TOP of this skill via `04_clew_*`. The core scientific-integrity principle — "honest source-grounding WITHOUT over-abstaining: attempt every claim, ground where possible, and when ungroundable include the claim explicitly with `null` + a reason — NEVER silently omit" — is framed here as a general scientific norm, not an output-schema rule. To actually translate-and-resolve, scitexification DEPENDS on four package-level companion skills that supply the API knowledge: scitex.session (the `@stx.session` framework), scitex.io (save/load I/O), scitex.plt + figrecipe (figures), and scitex.clew (provenance / source-grounding / validity chain). Load these alongside this playbook — see the "Required companion skills" section below for the canonical declaration and the SAC `spec.skills.required` snippet.
tags: [scitex-scientific-scitexification-playbook]
requires:
  - scitex-session
  - scitex-io
  - figrecipe
  - scitex-clew
---

# Scitexify — universal playbook

The single canonical playbook for **scitexification**, the act of converting
arbitrary scientific code into a SciTeX project. Layer-agnostic by
construction: nothing here is tied to a specific experiment's harness
(evaluation gates, scoring, output schemas). Specializations layer on top
(see [Related](#related)).

## Vocabulary (canonical)

- **scitexify** *(verb, transitive)* — to convert an existing scientific
  artefact (script, notebook, supplement, repo) into the SciTeX idiom.
  *Example: "scitexify the notebook before we add stats."*
- **scitexification** *(noun)* — the act, or its result. *Example: "the
  scitexification of this analysis is stage-2-complete."*
- **scitexified** *(adjective, past participle)* — describes a project that
  has been through the playbook below. *Example: "a scitexified script
  has `@stx.session`-decorated entry points."*

These three forms are the ecosystem's canonical vocabulary. Use them in PR
titles, docstrings, commit messages, and skill descriptions instead of
ad-hoc terms ("port to scitex", "scitex-ify", "convert to stx").

## Required companion skills

Scitexification is the *translation act*. To actually translate-and-resolve
in the SciTeX way, an agent (or human author) needs the **API knowledge**
that lives in the per-package skills. This playbook deliberately stays
package-agnostic at the surface level and DELEGATES the API surface to its
four canonical companions:

| Companion skill | What it provides for scitexification |
|---|---|
| **scitex.session** | The `@stx.session.start(...)` decorator, the CONFIG injection contract (`CONFIG`, `COLORS`, `logger`, `plt`, `rngg`), `SDIR_OUT` / `SDIR_RUN` semantics, YAML deep-merge + CLI/env overrides. **Required for stage 2** (session + config). |
| **scitex.io** | `stx.io.save(...)` / `stx.io.load(...)` with the per-extension saver/loader registry, the `symlink_to=eval(CONFIG.PATH.X)` cross-stage I/O pattern, post-save / post-load hook registration. **Required for stage 1** (I/O patterns) and **stage 4** (claims save/load). |
| **scitex.plt + figrecipe** | `stx.plt` figure objects, FigRecipe publication-quality primitives, the `stx.io.save(fig, ...)` DAG-binding for figures. **Required for stage 3** (figures). |
| **scitex.clew** | Claim registration, evidence-binding (the DAG that anchors a claim to a source file), `list_claims()` / `verify_claim()` / `render_dag()` primitives, validity-chain semantics. **Required for stage 4** (claims + provenance) and load-bearing for the honest-grounding principle below. |

The four are not interchangeable; each carries a specific role in the
five-stage arc.

### Declarative loading

This playbook's frontmatter lists the four as `requires:`. A SAC agent yaml
that loads scitexification pulls them automatically:

```yaml
spec:
  skills:
    required:
      - scitexification           # this playbook (umbrella tag)
      # The four companions below are inherited via `requires:` above.
      # List them explicitly anyway for SAC versions that don't yet
      # resolve transitive requirements:
      - scitex-session
      - scitex-io
      - figrecipe
      - scitex-clew
```

If your SAC version resolves transitive `requires:`, only the first line
is needed. If not, list all five — the duplication is harmless. The
canonical short-form everyone should learn is: **"to scitexify you need
session, io, plt, and clew."**

#### Tag vs filename: how loading the umbrella surfaces this playbook

`SKILL.md` carries the umbrella tag `[scitexification]`. This playbook
file carries the narrower tag
`[scitex-scientific-scitexification-playbook]`. The two are NOT meant
to be loaded by separate `spec.skills.required` entries — that would
double-count the same content. The contract is:

- A SAC agent loads the **umbrella** tag (`scitexification`) via
  `spec.skills.required`.
- The skills export tool mounts `~/.claude/skills/scitex/scitexification/`
  with **every sibling `.md` under the `06_scitexification/` directory
  in scitex-dev's `_skills/scientific/`** — including this `00_playbook.md`,
  the (future) `01_io-patterns.md` … `05_naming-and-numbering.md`
  chapters, and the umbrella `SKILL.md` itself.
- An agent that loads `scitexification` therefore gets both the SKILL.md
  overview AND this playbook in its skills context, without needing to
  list the narrower tag separately.

The narrower tag exists so a downstream skill that needs to reference
*only this playbook* (e.g. an internal cross-reference, a `requires:`
fold in a future per-chapter skill) can do so without pulling the whole
umbrella. For the SAC agent yaml, **always use the umbrella tag**.

### Stand-alone reading

A human reading this playbook without an agent runtime should open the
four companion `SKILL.md` files alongside this one:

```
~/.claude/skills/scitex/scitex-session/SKILL.md
~/.claude/skills/scitex/scitex-io/SKILL.md
~/.claude/skills/scitex/figrecipe/SKILL.md
~/.claude/skills/scitex/scitex-clew/SKILL.md
```

The playbook tells you *which* primitive to reach for at each stage; the
companion skill tells you *what* the primitive does. Read both.

## What scitexification *is*

Five staged transforms. Each holds independently — partial scitexification
is meaningful. Stop at any stage; the remaining work is strictly additive.

| Stage | What changes | What stays the same |
|---|---|---|
| 1. I/O patterns | Every `open()` / `np.load` / `pd.read_csv` / `pickle.load` → `stx.io.load(...)`. Every `np.save` / `pickle.dump` / `df.to_csv` → `stx.io.save(..., symlink_to=eval(CONFIG.PATH.X))`. The DAG (output of step N = input of step N+1) becomes visible at the filesystem level. | Your algorithm. Your data shapes. Your business logic. |
| 2. Session + config | The script entry-point becomes `@stx.session.start(...)`. Magic numbers + paths become `CONFIG.<KEY>` lookups against `config/*.yaml`. Logging becomes the session logger. | Function-call structure. Module organisation. Test cases. |
| 3. Figures | Every `plt.savefig(...)` → `stx.io.save(fig, ...)` so the figure is bound to a session output. Visual choices ladder up to FigRecipe's publication-quality primitives. | Figure intent (what comparison, what axis labels). What information the figure carries. |
| 4. Claims + provenance | Final-mile assertions (numbers in the abstract / conclusions) become **registered claims**, each evidence-bound to the file that produced it. Hand-written result JSON is replaced by an iterate-and-filter over registered claims. | What you are claiming. Your numbers. |
| 5. Naming + numbering | `cnn_v3_final_FIXED2.py` → `scripts/03_cnn.py` (zero-filled, sortable, mirrored under `tests/`). IDs and ordinals become readable symlinks per `02_research-project_09`. | Your filenames as a *concept*. The numbers themselves (after zero-fill). |

Stages 1+2 alone give you a *runnable* SciTeX project — the minimum viable
scitexification. Stages 3, 4, 5 are independently additive PRs.

## What scitexification *is not*

- **Not a search-and-replace.** Each stage requires you to read the
  surrounding logic. `df.to_csv("./out.csv")` → `stx.io.save(df,
  "./out.csv")` is wrong: the second arg should be the CONFIG path key
  resolved via `eval(CONFIG.PATH.X)`, not the literal.
- **Not an algorithm change.** The science stays. If the original computes
  a paired t-test on log-transformed counts, the scitexified version
  computes the same paired t-test on the same log-transformed counts.
- **Not a rewrite.** Stage 1's I/O swap is local and surgical. If the
  original calls a helper from `utils/parse_logs.py`, the scitexified
  version still calls `utils/parse_logs.py` — only the file *open* inside
  it moves to `stx.io.load`.
- **Not coupled to any specific evaluator.** Whether the project's outputs
  are later checked by a human reviewer, an LLM judge, a third-party
  verifier, or no one — scitexification is the same five stages. The
  evaluator is a separate concern.

## Universal inputs

The playbook takes exactly three slots. Anything beyond this is an
experiment-specific extension and belongs in a downstream layer.

| Slot | Meaning |
|---|---|
| `$SRC` | The thing being scitexified: a directory, a single notebook, a tarball, a git URL. **Read-only** to the agent / author. |
| `$WORKDIR` | The destination — the agent-writable directory where the scitexified project will live. |
| `$QUESTIONS_OR_GOALS` (optional) | A pointer to what the scientific output should answer or demonstrate. Free-form: a list of research questions, a notebook's conclusion section, an issue body, a paper's abstract. If absent, the goals are inferred from `$SRC`. |

The scitexification act produces a SciTeX project under `$WORKDIR` whose
DAG terminates in one or more **registered claims** plus their evidence
chain. Nothing else is required at this layer.

## Pre-flight (universal SciTeX rules)

Apply these BEFORE writing any code. They catch the recurring failure
modes that no amount of careful translation will fix later.

```
□ Makefile must NOT set `SHELL := /bin/bash`. It breaks `@stx.session`
  under `make`.
□ config/PATH.yaml: NO outer `PATH:` wrapper. Top-level keys are exposed
  directly under `CONFIG.PATH.<KEY>`; an outer wrapper produces
  `CONFIG.PATH.PATH.<KEY>` and every access site crashes with
  `AttributeError`. (See PS-PATH-001.)
□ `@stx.session` declares ALL FIVE injected params explicitly: CONFIG,
  COLORS, logger, plt, rngg. Missing one breaks DI assumptions in
  downstream stx modules.
□ Cross-stage I/O via `stx.io.save(..., symlink_to=eval(CONFIG.PATH.X))`.
  Vars consumed only by `eval(CONFIG.PATH.X)` need `# noqa: F841`.
□ For non-standard extensions (e.g. `.mmd`, `.tex` source), fall back
  to `Path(...).write_text(...)`; `stx.io.save` handles only the
  ecosystem-registered savers (see scitex-io's per-extension registry).
□ `stx.io.load(".txt")` returns `list[str]` of lines, NOT a single
  string. Iterate as-is or `"\n".join(lines)` if you need flat text.
□ Tips of the DAG (root inputs AND final outputs) MUST be FILES, not
  scripts. The final stage ends at a file saved via `stx.io.save(...)`,
  not at the script node.
□ All figures via `stx.plt` / FigRecipe so they enter the DAG as data.
  `matplotlib.pyplot.savefig()` is forbidden — it writes outside the
  session's output dir, the file is invisible to provenance tooling,
  and `make repro` silently breaks.
□ Files with non-descriptive source names (literal "output", "stdout"):
  COPY (not symlink) into a descriptive name in `data/` before stage 1.
  Clew/scitex-io resolve symlinks to target basename, so a symlink
  `result_output.txt` → `output` shows up as `output` in the DAG. A real
  copy `result_output.txt` shows clearly.
```

## Phase dispatch

Before writing stage 1, inspect `$SRC` and pick a phase. The four phases
share the same downstream (stages 1→5); only stage 1's *extraction*
differs.

```python
from pathlib import Path
src = Path(SRC)
results_dir   = src / "results"
has_results     = results_dir.exists() and any(results_dir.iterdir())
has_notebook    = bool(list(src.rglob("*.ipynb")))
has_repro_doc   = (src / "REPRODUCING.md").exists()

if has_results:
    phase = "read"        # parse existing result files — fastest
elif has_notebook:
    phase = "notebook"    # convert + execute the notebook
elif has_repro_doc:
    phase = "repro-doc"   # follow the documented reproduction recipe
else:
    phase = "infer"       # explore code/ + data/, infer the entry point
```

Note: `has_repro_doc` triggers on `REPRODUCING.md` specifically, not on
the more common `README.md`. A `README.md` is too broad a signal —
many notebook bundles carry a stub `README.md` that documents the
project at a glance rather than the *reproduction recipe*. Triggering
`repro-doc` on it would misroute the agent into looking for run
commands that aren't there. The narrower `REPRODUCING.md` convention
matches the existing `04_clew_02` playbook for the same reason.

| Phase | Stage-1 tool |
|---|---|
| read | direct file reads — `stx.io.load(...)`, pandas / json |
| notebook | `scitex_notebook.convert_notebook(..., mode="unified")` then `subprocess.run(["python", "stage1.py"])` |
| repro-doc | follow the documented commands; translate container runtimes (`docker run ...` → `apptainer exec ...` on HPC) as needed |
| infer | inspect `code/` for `if __name__ == "__main__"` or a `main()`; do not modify the source repo |

All four phases converge at `extract → answers/results → claims`.

## Honest source-grounding (the integrity principle)

**This is the scientific-integrity contract scitexification enforces.** It
is independent of any evaluator and applies even when no one is checking.

### The principle

> Every claim a scitexified project makes about the world MUST be
> attempted, grounded against verifiable source where possible, and —
> when grounding is impossible — recorded explicitly with `null` and a
> reason. Silent omission of an ungroundable claim is forbidden.

### Why the principle is necessary

A natural failure mode under uncertainty is **over-abstention**: an agent
or author who cannot ground a claim quietly drops it. Across many runs
this becomes a **silent-attrition** pattern — the agent answers only the
easy questions, never tries the hard ones, and the output set is a
*smaller, biased subset* of the question set. The downstream record
looks clean but lies by omission, and a reviewer reading the output
**cannot distinguish three radically different states**:

1. "we tried, evidence was clear, the answer is X"
2. "we tried, the evidence was ambiguous / inaccessible"
3. "we never attempted this question"

All three collapse to the same shape: *nothing in the output*. The bias
is invisible to anyone downstream.

Scitexified projects refuse the silent failure by construction. A claim
either:

1. **Lands with `answer != null` and an evidence chain.** The evidence
   chain (Clew DAG, `stx.io` save path, registered claim) lets a
   reviewer verify the number ladders back to a file in `data/`. This
   is the desired state.

2. **Lands with `answer = null` and `reason != null`.** The reason
   explains why grounding failed — *the data was not in the supplement*,
   *the cell errored on a missing dependency*, *the published table is
   ambiguous between two reportings* — in enough detail that a human
   reviewer can decide whether to escalate, defer, or accept.

The two states are **not equivalent to success and failure**. Both are
honest outputs. The only dishonest output is the *missing* claim: a
question the project should have addressed, with no entry in the
results.

### Concretely

```python
# WRONG — silent over-abstention.
# If the value can't be extracted, drop the entry.
try:
    val = extract_accuracy(results_path)
    claims.append({"id": qid, "answer": val})
except Exception:
    pass  # ← this is the forbidden silence.

# RIGHT — explicit null with reason.
try:
    val = extract_accuracy(results_path)
    claims.append({"id": qid, "answer": val, "source": str(results_path)})
except Exception as exc:
    claims.append({"id": qid, "answer": None, "reason": str(exc)})
```

The general rule:

- **Attempt every claim.** Do not pre-emptively skip "hard" questions.
- **Ground what you can.** When the value comes from a file, record the
  file path on the claim itself (`source` / `evidence` field).
- **Be explicit about what you can't ground.** Include the claim with
  `answer: null` plus a one-sentence `reason`. The reason must be
  actionable for the next reviewer — "the source notebook errored on
  `ModuleNotFoundError: ot`" is good; "could not compute" is not.
- **Never silently omit.** A correct result is one where the *count* of
  claim entries equals the *count* of expected goals — independent of
  how many entries are `null`.

Schema note (layer-agnostic): the WRONG/RIGHT example above uses
`{answer, source}` for grounded claims and `{answer, reason}` for null
claims — two key sets. The playbook stays agnostic to the final shape;
downstream evaluators typically prefer one of two uniform schemas:
(a) **always carry both keys** with the unused one set to `null`
(`{answer, source, reason}` everywhere — easiest to parse uniformly);
or (b) **a single `evidence` field** that is either a file path string
or a reason string, with the discriminator being how it parses. Pick
whichever the consuming evaluator wants; the integrity contract is
about the *presence* of the entry, not the key set.

### Separation of concerns: filtering is downstream

If a downstream evaluator does need to filter the agent's output (a
SHA-256 lineage gate, a source-verified flag, an evidence-completeness
threshold), the filter applies **after** the agent emits — on the
verifier side, never as an instruction to the agent. Telling the agent
"if you can't ground it, omit it" produces silent attrition and
destroys the epistemic signal the verifier needs.

The agent's job is to emit a faithful record of *what it attempted and
what it found*. The verifier's job is to decide *which entries count*.
Mixing the two is the bug.

### Why this is a general principle, not an output-schema rule

This principle is older than scitex-clew and outlives any one evaluator.
It is the standard scientific-record norm: report what you found,
including what you couldn't find. Pre-registration and Methods-section
discipline operationalise the same idea. Scitexification just enforces
it in the output schema so the project's filesystem reflects the norm
mechanically.

## Done condition (universal)

A scitexification is complete when ALL of:

1. The project under `$WORKDIR` runs end-to-end. (`make solve` or
   equivalent exits 0.)
2. The DAG terminus exists and is a file — `claims.json` is the
   canonical default, but the playbook is agnostic to the schema.
3. The count of entries at the terminus equals the count of
   `$QUESTIONS_OR_GOALS` items (or the project's stated goal-count if
   unstructured).
4. Every entry has either `answer != null` with an evidence pointer, OR
   `answer == null` with a non-empty `reason`. Silent omission fails.
5. The five pre-flight items are still green (the project hasn't drifted
   during translation).

If any of (1)–(5) fail, the project is partially scitexified — that's a
valid state, but it should be recorded explicitly (e.g., README note,
issue) rather than presented as done.

## Forbidden (at the universal layer)

These are forbidden regardless of which downstream evaluator the project
feeds. Experiment-specific layers add more (e.g., an evaluator-blind
harness forbids reading the held-out answers); this list is the universal
floor.

- Silent omission of an ungroundable claim (see Honest Grounding).
- Hand-writing the results / claims JSON instead of composing it from
  registered claims via the appropriate API (e.g. iterate over
  registered claims via the project's claim-store API — `scitex_clew.
  list_claims()` for clew-tracked projects, the equivalent claim-store
  iterator for any other evaluator). Hand-written JSON drifts from the
  evidence-binding the registered claims actually carry.
- `matplotlib.pyplot.savefig(...)` directly — figures must enter the
  DAG via `stx.io.save`.
- Modifying the source-of-translation in `$SRC` (read-only by
  convention; copy first, transform the copy).
- Heavy data anywhere under `~` on HPC nodes (capacity quotas; use
  `$WORKDIR` or the cluster's scratch tier).
- Mixing `os.path.join(...)` and `CONFIG.PATH.<KEY>` for the same path
  inside the same script. Pick one per call site.

## On failure

Iterate at most **three times per stage**. If still blocked:

1. Record the blocker on the affected claim(s) as `answer: null` +
   `reason: <short>`.
2. Move on. A partially scitexified project with explicit nulls is more
   valuable than a fully scitexified project that took shortcuts.
3. Open an issue / leave a README note for the reviewer.

The honest-grounding principle gives you permission to ship the partial
result without over-fitting it.

## What this skill does NOT cover

Deliberately out of scope (each has its own dedicated home):

- **The target project structure** (`./config/`, `./data/`,
  `./scripts/`, `./tests/`, Makefile shape) →
  [`../02_research-project_*`](../).
- **Per-package API surface** (full `stx.io` type matrix, FigRecipe
  figure types, scitex-clew primitives) → the per-pkg SKILL.md in
  `~/.claude/skills/scitex/<pkg>/`.
- **Clew-specific / experiment-specific specialisation** (evaluator-blind
  scoring, run dispatch, completion signalling, output/results
  schemas) → [`../04_clew_*`](../). Read those AFTER this playbook
  when working in a clew-tracked flow.
- **The discovery contract** (consumer-side
  `spec.claude.skills: [scitexification]` auto-loading) — tracked
  separately in the SAC ↔ scitex-dev contract thread; not a
  scitexification concern.

## Related

- [SKILL.md](SKILL.md) — the 5-stage arc table and "when to load" gate.
- [`../04_clew_01_dag-as-map-and-evidence.md`](../04_clew_01_dag-as-map-and-evidence.md)
  — DAG-as-map vs DAG-as-evidence framing. Read after this playbook
  when adopting clew.
- [`../04_clew_02_translation-playbook.md`](../04_clew_02_translation-playbook.md)
  — clew-specific translation playbook. Specialisation of stages 1+2+4
  for the clew-tracked flow.
- [`../04_clew_03_translation-template.md`](../04_clew_03_translation-template.md)
  — concrete project skeleton for clew-tracked translation.
- [`../02_research-project_07_config-and-parameters.md`](../02_research-project_07_config-and-parameters.md)
  — `@stx.session` reference (required by stage 2).
