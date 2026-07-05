---
description: |
  [TOPIC] Hypotheses agreement (research-project equivalent of architecture agreement)
  [DETAILS] Before writing any experiment script, agree with the user on a numbered, falsifiable list of hypotheses (H1, H2, ...) — each with a measurable observable, a predicted outcome, and a comparison baseline. Vague claims like "X works better" are non-testable and must be rejected or sharpened. The hypotheses doc is the source of truth that experiment scripts, manuscript claims, and statistical tests resolve against. Analogous to the "architecture agreement" required for pip packages before code is written. Pairs with [`./scripts`](02_research-project_02_project-structure-scripts.md) (where each H gets at least one experiment) and [`general/04_docs`](../general/04_docs/01_readme.md) (where the H list ends up summarised in the README).
tags: [scitex-scientific-planning-hypotheses-agreement]
---

# Hypotheses Agreement

> The research-project counterpart to the **architecture agreement** required for pip packages (see `general/05_development_*`). No experiment code without an agreed hypothesis list.

## Why

A research project's units of progress are **hypotheses**, not features. Writing an experiment without a stated hypothesis is the scientific equivalent of writing code without a spec — it produces output, but no decision can be made from it.

Empirically: when an agent jumps to "let me run the experiment" before agreeing on hypotheses, the result is almost always (a) a metric that doesn't answer any question, or (b) a question the user didn't actually want answered. Both burn time.

## Requirements per hypothesis

Every `H<n>` must have:

1. **A one-sentence claim**, in plain English. No tool/method names that aren't defined elsewhere in the doc.
2. **A measurable observable.** "Better" / "minimal" / "more reliable" without a metric is non-testable.
3. **A predicted outcome with a number/threshold.** "≥ 45/49 capsules", "p < 0.05", "rate ≥ 95%". A hypothesis without a prediction can't be falsified.
4. **A baseline or comparator.** "Higher than" needs a "than what". Paired arms (with-X vs without-X), historical baseline, or random-chance baseline are all valid; "higher than vibes" is not.
5. **A clear failure mode.** What outcome would falsify the hypothesis?

If any of (2)–(5) is missing, the hypothesis is **not yet ready for experiment**. Send it back to the user for sharpening.

## Format

Document at `GITIGNORED/HYPOTHESES.md` (or `docs/hypotheses.md` if public). One project-wide doc; numbered sections per major experiment group.

```markdown
# <experiment-group> — Hypotheses

## Headline claim
<one sentence — the paper's contribution as a single statement>

## Hypotheses

- **H1 — <one-sentence claim>.**
  Observable: <what is measured>.
  Prediction: <number or threshold>.
  Baseline: <comparator>.
  Falsified if: <failure outcome>.

- **H2 — ...**
```

## Anti-patterns to reject

| Bad form | Why it fails | Sharpen to |
|---|---|---|
| "Method X is better." | "Better" undefined; no comparator. | "Method X scores ≥ Y on benchmark B vs baseline Z." |
| "DAG shows minimal logic." | "Minimal" undefined; "shows" undefined. | "DAG node count ≤ X% of source-file count, with 100% claim coverage." |
| "Agent works as a better scientist." | "Better scientist" too broad; no metric. | "Agent with skill S scores ≥ X percentage points higher than same agent without S on benchmark B (paired, n=...)" |
| "We will show feasibility." | Feasibility ≠ a falsifiable claim. | "Pipeline runs to completion on ≥ N inputs without manual intervention." |

## Workflow

```
draft hypotheses (agent)
  → user reviews; sharpens or rejects vague ones
  → repeat until each H meets the 5 requirements
  → user explicitly approves: "okay, H1 + H2 only" / "all four"
  → only then start writing experiment scripts that resolve each H
```

The agreement step is **gating**. Don't write code until the user has approved.

## When NOT to require this

- Quick exploratory plotting / EDA — "is this distribution bimodal?" — no formal H needed; the figure IS the answer.
- Smoke tests / pipeline-shake-out runs that produce no claim.
- Internal debugging tooling.

If the output won't appear in a manuscript or a public claim, skip the formality.

## Versioning

Hypotheses can evolve. When a hypothesis is sharpened, add a `(revised <date>)` annotation rather than overwriting silently — the prior form is part of the project's reasoning trail.

When a hypothesis is **dropped**, move it to a "Dropped" section with a one-line reason. Don't delete; the trail shows what was considered and why.

## Audit

`scitex-dev ecosystem audit-project --hypotheses` (planned) checks:

1. A `HYPOTHESES.md` exists.
2. Every numbered `H<n>` has all 5 required parts.
3. Every experiment script under `./scripts/` references at least one `H<n>`.
4. Every `\stxclaim{...}` / `\vclaim{...}` in the manuscript resolves to a hypothesis.
