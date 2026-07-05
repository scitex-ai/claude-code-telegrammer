---
description: |
  [TOPIC] Architecture Decision Records (ADRs)
  [DETAILS] When and how to write ADRs in SciTeX packages — placement under
  `<pkg>/docs/adr/NNNN-kebab-case-title.md`, the six-section template
  (Status / Context / Decision / Consequences / Notes, plus optional
  inventory tables and per-phase recipes), versioning convention
  (zero-padded `0001`, `0002`, …), and the criteria distinguishing an ADR
  from regular CHANGELOG entries or migration plans. Use whenever a
  cross-cutting decision is made that future maintainers would otherwise
  have to reverse-engineer from commits.
tags: [scitex-general-docs-adr]
---

# Architecture Decision Records (SciTeX)

## What an ADR is

A **short, durable record** of one architectural decision. It freezes
the *why* of a choice so future maintainers don't have to dig through
chat logs, commits, or stale design docs to understand the call.

ADRs are immutable once accepted. If a decision is reversed, write a
**new** ADR that supersedes the old one (and reference it).

## When to write one

Write an ADR when **all** of these are true:

- The decision affects more than one package, or a cross-cutting
  convention (SoC rules, layered architecture, observer-pattern wiring,
  SSOT for a shared symbol, dependency policy, deprecation policy).
- The reasoning is non-obvious from the resulting code alone.
- A reasonable future maintainer might be tempted to undo or duplicate
  the decision without context.

Do **not** write an ADR for:

- Routine feature work that's covered by the PR description + CHANGELOG.
- Bug fixes whose rationale is captured in the commit message.
- Module-internal refactors that don't cross package boundaries.

## Where it lives

```
<pkg>/docs/adr/
├── 0001-<kebab-case-title>.md
├── 0002-<kebab-case-title>.md
└── …
```

- Per-package directory: `<pkg>/docs/adr/`.
- Filenames: `NNNN-kebab-case-title.md` with **zero-padded** 4-digit
  index, monotonically increasing per package.
- Reference packages: [`scitex-gen/docs/adr/`](https://github.com/ywatanabe1989/scitex-gen/tree/develop/docs/adr),
  [`scitex-ui/docs/adr/`](https://github.com/ywatanabe1989/scitex-ui/tree/develop/docs/adr).

When a decision spans multiple packages, place the ADR in the package
that **owns** the decision (e.g. SSOT for `@deprecated` → goes in
`scitex-compat/docs/adr/`, since scitex-compat is the canonical home).
Cross-package corollaries can be linked from the affected packages'
README "Architecture" sections.

## Template (copy/paste)

```markdown
# ADR-NNNN: <one-line decision in the imperative>

## Status
<one of: Proposed | Accepted (YYYY-MM-DD) | Superseded by ADR-MMMM | Rejected>

## Context
<2–6 paragraphs describing the situation that required a decision.
Include any quantitative audit results (e.g. "scan showed 6 of ~50
symbols had downstream consumers across 4 packages / 11 files").
Tables welcome. State the constraint that made this hard.>

## Decision
<the actual decision in 1–3 sentences. Then expand with:

**Placement / design principles** (numbered list, ~3–5 items)
Why this shape, not the alternatives.

**Inventory table** (when the decision touches many symbols / files)
| Source | Symbol | Target | Notes |
| --- | --- | --- | --- |

**Per-step recipe** (when other engineers will execute the migration)
Numbered steps + the exact `scitex-dev rename-symbols ... --dry-run`
or equivalent command.

**Ordered phases** (when rollout is staged)
Phase 0 / 1 / 2 / 3 with what each delivers.>

## Consequences
<bullet list of what changes as a result — positive AND negative.
Include the cycles avoided, the deprecation grace period, downstream
churn, what disappears, what new responsibility appears.>

## Notes
<provenance: when the decision was surfaced, who raised it, which
draft documents this ADR supersedes, links to related ADRs.>
```

## What goes in each section

- **Status** — `Accepted (YYYY-MM-DD)`. Never edit later; reverse via
  a new ADR. Use absolute dates, not "yesterday".
- **Context** — the problem AND the audit data. An ADR without numbers
  is a hunch. When you say "many callers" prove it with a count.
- **Decision** — the rule itself plus the *principles* that produced
  it. Future readers must be able to apply the same principles to a
  new edge case without re-deriving them.
- **Consequences** — explicit trade-offs. If you skip negatives you'll
  hide the cost from whoever is asked to undo it.
- **Notes** — provenance is what separates an ADR from a wiki page.

## ADR vs. other docs

| Document | Lifespan | Mutability | Audience |
| --- | --- | --- | --- |
| ADR | forever | immutable (supersede instead) | future maintainers |
| CHANGELOG | per-release | append-only | users of this release |
| PR description | merged | frozen at merge | reviewers + git archaeology |
| Migration plan | until executed | edited as plan firms up | the engineer doing the migration |
| `GITIGNORED/*.md` | scratch | freely edited | the operator + Claude |

A migration plan often **becomes** an ADR when the work is done — the
plan dies (delete the file in the same PR) and the ADR takes its place
as the durable record.

## Index hygiene

If a package accumulates more than ~5 ADRs, add a
`<pkg>/docs/adr/README.md` index:

```markdown
# ADRs — <pkg>

| # | Title | Status |
|---|---|---|
| [0001](0001-…md) | … | Accepted (2026-…) |
| [0002](0002-…md) | … | Superseded by 0005 |
```

Keep entries one line each. Don't re-summarize the ADR in the index —
the title is the summary.

## Convention summary (quick reference)

- One ADR = one decision. Don't bundle.
- Status uses absolute dates.
- Title is in the imperative ("Move @deprecated to scitex-compat",
  not "Moved @deprecated to scitex-compat").
- Reverse a decision with a NEW ADR; mark the old one
  `Superseded by ADR-NNNN`.
- An ADR-worthy decision usually deserves a short note in the affected
  packages' SOC.md or README "Architecture" section, linking back.
