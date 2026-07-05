---
description: |
  [TOPIC] Manuscript Structure Design
  [DETAILS] How to design (and compact) a scientific paper's structure: a claims-first spine where each Result subsection maps to exactly ONE figure, leading with a dataset + experimental-design Result that orients before any method detail, an EXPLICIT float manifest (figure/table -> source script + claim) instead of an implicit glob+filename-prefix convention, writing Introduction and Discussion LAST (they reframe around the findings that survive), simplifying redundant analyses (pick one design when competing designs yield the same claim), flagging provisional elements that lack a downstream story, and panel-level figure sketches bound to their generating script. Use when planning a new manuscript, compacting a bloated draft, or auditing a paper for structural redundancy.
tags: [scitex-scientific-planning-paper-structure]
---

# Manuscript Structure Design (universal principles)

Counterpart to [00_planning_01_hypotheses-agreement.md](00_planning_01_hypotheses-agreement.md):
hypotheses fix *what you will test*; this leaf fixes *how the manuscript that
reports them is shaped*. Design the structure explicitly, before prose.

## One claim, one figure, one Result subsection

- Each **Result subsection maps to exactly one figure** (or table). If two
  subsections lean on the same figure, they are one subsection.
- Each figure carries **one load-bearing claim**; mark which panel is the
  load-bearing evidence (e.g. the non-circular-transfer scatter, the
  stability scalar). The rest of the panels support that claim.
- Bind every figure to the **claim it proves** and the **script that builds
  it** — this binding is the spine of the paper.

## Lead with dataset + experimental design

Make **Result 1** the dataset overview + experimental-design schematic, so the
reader is oriented to the corpus, the inclusion rules, the event/control
construction, and the analysis/prediction design *before* any method detail.
Make it earn "Result" status by carrying real numbers (cohort/event counts,
spans, a demographics table) — not a pure schematic, which belongs in Methods.
A headline method (e.g. a new tool) reads fine as Result 2, applied to the
dataset just introduced.

## Explicit float manifest, not implicit glob

Declare the ordered float list explicitly — a manifest binding each figure /
table to its `id`, caption, **source script**, and media — rather than relying
on a compiler that globs a directory and infers order from filename prefixes.
An implicit glob+prefix contract is what lets duplicate figures, ambiguous
ordering, and stray cruft accumulate unnoticed. Order = manifest order;
anything undeclared is ignored (and flagged).

## Write Introduction and Discussion LAST

- **Introduction** is reframed around the findings that actually survive — so
  it is written once the figure set is frozen, not first.
- **Discussion** depends on which claims hold and which got demoted — also
  last.
- Draft Methods + Results first; they drive everything else.

## Simplify redundant analyses

- When two competing designs (e.g. two cross-validation partitions) yield the
  **same claim**, keep ONE in the main text and demote the other to a
  supplementary robustness check. Pick the one that is scientifically most
  honest for the paper's framing (e.g. a prospective split for a prediction
  paper), not the one with the prettier number.
- A descriptive result that is *interesting but has no downstream story* is
  **provisional**: stage it as a single panel with an explicit open question,
  and demote it to supplementary if no story emerges. Do not let an orphan
  taxonomy/categorisation inflate the main figure count.

## Compacting a bloated draft

Bloat usually comes from an **accreted double spine** — an old organisation
plus a newer per-figure organisation kept side by side, narrating the same
content twice. To compact:

1. Inventory floats and subsections; find the duplicated pairs.
2. Collapse to the one-claim-one-figure spine; merge duplicate captions /
   methods subsections.
3. Re-number figures and supplementary (S1, S2, …) with one-line descriptions.
4. Sketch each figure at **panel level** (A/B/C/D) bound to its build script,
   marking load-bearing panels and provisional ones.

## Supplementary

Number `Table S1, S2, …` and `Fig S1, S2, …`, each with a clear one-line
description. Natural supplementary contents: sensitivity / excluded-subject
analyses, demoted robustness designs, per-subject narrative reports, and
overflow validation that supports but does not carry a main claim.

## Anti-patterns

- Two subsections narrating the same figure from different angles.
- A schematic-only "Result 1" with no data — that is Methods.
- Inferring figure order from filename prefixes instead of an explicit manifest.
- Writing the Introduction first, then having to rewrite it when the findings
  shift.
- Keeping both of two designs that prove the same claim "for completeness".
- Promoting an interesting-but-storyless categorisation to a main figure.
