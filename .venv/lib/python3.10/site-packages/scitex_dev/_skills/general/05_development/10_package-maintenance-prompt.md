---
description: |
  [TOPIC] Package maintenance: the standing prompt for any agent
  handed a scitex-* package, plus the CLAUDE.md-vs-skill split that
  decides where each rule lives.
  [DETAILS] One canonical prompt covers package management, day-to-day
  development, and maintenance. CLAUDE.md = invariants every turn must
  see; skill files = contextual depth loaded on demand. Required vs
  available skills, the `@path` reference mechanism that forces a skill
  to load at startup, and the agent-runtime path that makes both work.
tags: [scitex-general-development-package-maintenance-prompt]
---

# The package-maintenance prompt

When a fresh agent (sac runner, subagent, or interactive Claude Code
session) is handed a `scitex-*` package, it should run **one** standing
loop, not bespoke per-task prompts:

> You are the maintainer of `<pkg>`. While the user works elsewhere:
>
> 1. Read the package's required skills (under
>    `src/<import>/_skills/<pkg>/`) plus the general skills
>    (`scitex/general/`).
> 2. Run `scitex-dev ecosystem audit-all <pkg>` and triage violations.
> 3. Keep the test suite green (`pytest tests/`), Sphinx clean
>    (`make -C docs html`), and skills consumer-mirrored
>    (`scitex-dev skills install --link --claude-symlink`).
> 4. For each user request, judge whether it belongs as code, as
>    a CLAUDE.md invariant, or as a skill file — see split below.
> 5. Commit on feature branches; PR into `develop`; never push to
>    `main` directly. CI is the contract.

That paragraph is the **only** prompt a package agent needs. Everything
else (where files go, naming, doc surfaces, lint rules) is in the skill
tree and gets loaded contextually.

## CLAUDE.md vs skill files — the split

Both are markdown, both are agent-readable, both can carry rules. The
difference is **scope and load frequency**.

| | CLAUDE.md | Skill file |
|---|---|---|
| Loaded | Every turn, automatically | On demand, when topic-relevant |
| Token cost | Paid on every turn | Paid only when consulted |
| Right for | Invariants no agent can miss | Domain depth, recipes, leaves |
| Right size | Tight (lines, not pages) | Whatever the topic needs |
| Right tone | Hard rules, no preamble | Teaching, examples, rationale |

The rule of thumb: **if forgetting it once would cause a real incident**,
it belongs in CLAUDE.md. If the cost of "agent didn't know that yet" is
a quick re-read, it belongs in a skill file.

Examples of CLAUDE.md material:

- "Main checkout always stays on `develop`."
- "Never push to `main` without explicit user authorization."
- "Subagents launched with `isolation: worktree`; never on the main
  checkout."
- "Speak in English on audio channels."

Examples of skill-file material:

- "How to write a Sphinx page" (`04_docs/02_sphinx.md`).
- "Coverage push playbook" (`05_development/08_coverage-push-playbook.md`).
- "Package-categories taxonomy" (`01_ecosystem/09_package-categories.md`).

If you find yourself adding a paragraph of explanation to CLAUDE.md,
it almost certainly wants to live in a skill file with a one-line
pointer in CLAUDE.md.

## Required vs available skills (the `@path` mechanism)

Skill files in `_skills/` come in two tiers, set by **how CLAUDE.md
references them**:

```
# Required — forced load at startup
@_skills/<pkg>/03_publishing_01_release-checklist.md

# Available — agent will find them via search/topic match, not auto-loaded
See `_skills/<pkg>/` for the full skill tree.
```

A literal `@<path>` line in CLAUDE.md is interpreted by Claude Code as
a directive to **inline that file into the agent's startup context**.
Use this for skill leaves the agent must apply unconditionally — most
typically:

- The package's per-tool quality rules (e.g. "every plt function
  returns the figure handle").
- The repo's git workflow (branch model, commit-message format).
- The list of hard "do not do X" rules specific to this package.

Anything else goes into the skill tree and is consulted on-topic —
either by the agent searching the tree, or by another skill cross-
referencing it.

### sac-agent variant

For agents launched through `scitex-agent-container` (sac), the
required-skill set is declared in the spec, not in CLAUDE.md:

```yaml
# agent spec
required_skills:
  - python-scitex
  - scitex-stats
available_skills:
  - code-review
  - orchestrator
```

The sac runtime materialises a CLAUDE.md inside the agent container
that contains `@`-references to each required skill, so the same
forced-load mechanism applies. `available_skills` are mounted but not
auto-loaded — the agent finds them when topic-relevant.

This is why `available_skills` is cheap (cost paid only on
consultation) while `required_skills` is the slot to think hard
about — every name there is a permanent context-window tax.

## Where each piece of doctrine lives

A maintenance instruction can land in five places. From most-targeted to
most-global:

1. **Code itself** (a docstring, a CLI `--help`, a hint string). Best
   when the rule is local to the call site.
2. **Skill file** in the package's own `_skills/<pkg>/`. Best when the
   rule is package-specific but spans many call sites.
3. **Skill file** in `_skills/general/` (this directory). Best when
   the rule is ecosystem-wide.
4. **Package CLAUDE.md** (`<repo>/CLAUDE.md`). Best when the rule is
   repo-specific AND every turn must see it.
5. **User-global CLAUDE.md** (`~/.claude/CLAUDE.md`). Best when the
   rule is user-specific and crosses all projects.

Default to the most-targeted layer that still gets seen. Promoting
from skill → CLAUDE.md is cheap; demoting later is a token-budget win.

## Audit hooks that keep the split honest

```bash
# Every general/package skill file must declare description + tags.
scitex-dev ecosystem audit-skills <pkg>

# Skill files vs README vs docstring drift.
scitex-dev ecosystem audit-all <pkg>
```

If a skill file's `description` block is vague, the auditor flags it
(rule SK101). If a rule shows up in three places (CLAUDE.md + skill +
README) with slightly different wording, the consumer-mirror step
(`scitex-dev skills install --link --claude-symlink`) catches the
divergence — one file is the canonical source, the others are
symlinks.

## Cross-references

- `04_docs/01_readme.md` — README surface.
- `04_docs/02_sphinx.md`, `04_docs/03_rtd.md` — Sphinx + RTD.
- `05_development/04_skills-self-explain.md` — quality measure for
  skill content.
- `05_development/05_doc-surfaces.md` — which surface beats which.
- `../02_package/` — physical layout rules for files in the package.
