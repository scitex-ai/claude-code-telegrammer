---
description: |
  [TOPIC] Private skills for consumer projects (research repos, paper repos, internal apps)
  [DETAILS] Where to put project-specific agent-facing knowledge in a SciTeX *consumer* project (e.g. `paper-scitex-clew`, an internal analysis repo, a fleet ops repo) — distinct from public-package skill rules in `../general/03_interface/04_skills/06_public-vs-private.md` (which is for package authors). Covers the 4-layer skill stack (public-package, fleet-private, consumer-project-private, consumer-project gitignored notes), when content belongs in each layer, how consumer projects pull in the public skill mirror at `~/.claude/skills/scitex/...`, the lift-up rule (when a project-private note becomes reusable enough to graduate to a public package skill), and concrete examples from `paper-scitex-clew`.
tags: [scitex-scientific-private-skills-consumer-project]
---

# Private skills for consumer projects

A *consumer project* uses SciTeX packages but is not itself a SciTeX
package — research repos (`paper-scitex-clew`), internal analysis
repos, fleet-ops repos, paper-companion code bundles. The
public-vs-private decision rule for *packages* lives in
[`../general/03_interface/04_skills/06_public-vs-private.md`](../general/03_interface/04_skills/06_public-vs-private.md);
this leaf fills in the consumer side.

## The four-layer skill stack

| # | Layer | Lives at | Tracked by | Audience |
|---|---|---|---|---|
| 1 | **Public package skills** | `<pkg>/src/<pkg>/_skills/<pip-name>/` | `git push` to package repo, exported via `scitex-dev skills install` to `~/.claude/skills/scitex/<pip-name>/` | every consumer who installs the package |
| 2 | **Fleet-private package skills** | `~/.scitex/<pkg-short>/shared/skills/<pip-name>-private/` | dotfiles repo (private), symlinked into `~/.claude/skills/` | one fleet (your fleet) |
| 3 | **Consumer-project-private skills** | `<project>/.claude/skills/<project>/` | tracked in the project repo | every collaborator on that project |
| 4 | **Consumer-project gitignored agent notes** | `<project>/GITIGNORED/`, `<project>/docs/to_claude/`, `~/.claude/projects/<encoded>/memory/` | local-machine artefacts, not committed | only this machine / this user |

A consumer project may use any of layers 1, 3, 4 (plus 2 if your fleet
has private package skills). Layer 1 is *consumed* by the project
(via `~/.claude/skills/scitex/`); layers 3 and 4 are *authored* by the
project.

## What goes in each consumer-side layer

### Layer 3 — `<project>/.claude/skills/<project>/`

The right place for **project-specific agent procedures that
collaborators must follow**. Tracked in the project repo, so a fresh
clone gets them. Examples:

- The project's analysis pipeline order ("run scripts in `01_*`,
  `02_*` order; never run `99_*` standalone").
- Project-specific naming rules that diverge from ecosystem default.
- A collaborator-onboarding checklist.
- Anti-patterns specific to this paper / capsule cohort.

Not appropriate for layer 3:

- Agent prompts shared with multiple projects → lift to layer 1
  (a public-package skill in `scitex-dev/_skills/scientific/`).
- Local-machine paths, hostnames, credentials → layer 4 or layer 2.
- One-off scratch notes, conversation transcripts → layer 4.

### Layer 4 — `<project>/GITIGNORED/`, `docs/to_claude/`, auto-memory

The right place for **local-machine, transient, or
work-in-progress agent context** that should *not* enter the project
repo. Examples:

- `GITIGNORED/FAILED_PATTERNS.md` — running log of failures while the
  project is exploratory; promote to layer 3 once stable.
- `GITIGNORED/AGENT_PROMPT.md` — drafts of agent prompts during
  iteration; promote to layer 1 once the prompt is reusable.
- `docs/to_claude/` — host-specific quirks, paths to scratch
  directories, fleet credentials.
- `~/.claude/projects/<encoded>/memory/` — auto-memory entries (user
  preferences, session-spanning context).

The general gitignore policy: anything that would burden a fresh
collaborator with local-machine specifics goes here.

## The lift-up rule (when a private note graduates)

Consumer-project gitignored notes (layer 4) and consumer-project
private skills (layer 3) often turn into ecosystem-grade contributions
over time. Watch for these signals and promote upward:

1. **Reusable across projects** → lift to layer 1 (public package skill
   in the appropriate `scitex-*` package's `_skills/` dir, e.g.
   `scitex-dev/_skills/scientific/` for research-project conventions).
2. **Stable for the project's collaborators** → lift from layer 4 to
   layer 3.
3. **Fleet-internal but reusable across projects** → layer 2.

Example: `paper-scitex-clew/GITIGNORED/AGENT_PROMPT.md` (layer 4)
described a project-internal universal agent prompt for capsule
translation. Once the design stabilised, it was lifted to
`scitex-dev/_skills/scientific/04_clew_02_translation-playbook.md`
(layer 1) so any project — not just `paper-scitex-clew` — can declare
`spec.skills.required: [scitex-scientific-clew-translation-playbook]`
on its sac yaml and get the canonical playbook auto-imported.

## Decision tree

```
Where does this new agent-facing doc belong?

1. Is it generic to ALL ecosystem users (researchers + package authors)?
     YES → layer 1 (public package skill in scitex-dev/scitex-clew/etc.)

2. Does it name fleet-internal hostnames / credentials / zone IDs / containers?
     YES → layer 2 (fleet-private package skill at ~/.scitex/<pkg>/...)

3. Is it specific to ONE project but every collaborator must follow it?
     YES → layer 3 (consumer-project skill at <project>/.claude/skills/)

4. Else (transient, local-machine, scratch, or work-in-progress)
     → layer 4 (<project>/GITIGNORED/, docs/to_claude/, auto-memory)
```

When in doubt, start at layer 4 (cheapest), then promote upward as
content stabilises and reusability becomes clear.

## How consumers pull in layer-1 skills

Public package skills are exported on `pip install <pkg>` (or
`scitex-dev skills install` for editable installs) into
`~/.claude/skills/scitex/<pip-name>/`. Two consumption paths:

| Consumer | Mechanism |
|---|---|
| Interactive Claude Code on the consumer project | Skills auto-discoverable; reference by canonical name in any prompt or agent yaml |
| Sac peer agent — **hard injection** | `spec.skills.required: [<skill-id>]` → materialised as `@<path>` in CLAUDE.md, agent ALWAYS sees the content at session start |
| Sac peer agent — **soft reference** | `spec.skills.available: [<skill-id>]` → listed by name only, agent decides whether to read |

The **hard / soft** distinction is the user-facing contract — pick
**hard** for procedures the agent must apply (validity gates, security
rules, scoring schemas) and **soft** for references the agent should
know exist but doesn't need until invoked. Internally these map to
`spec.skills.required` and `spec.skills.available` respectively.

Caveat: as of 2026-05-05, `runtime: claude-sdk-persistent`
(formerly `claude-session`) does NOT honor either mode — only
`runtime: claude-cli-tui` (formerly `claude-code`) materialises
`required` via `setup_claude_md`. See F-CS1 in
scitex-agent-container's GITIGNORED/FEATURE_REQUESTS.md.
Workaround until fixed: include the absolute path to the hard skill
leaf in the mission text and treat soft skills as documentation-only.

## Concrete consumer-project layout — `paper-scitex-clew`

Annotated tree showing how the four layers manifest in one
already-running consumer project:

```
paper-scitex-clew/                              # consumer project root
├── .claude/skills/paper-scitex-clew/           # layer 3 (project-private, tracked)
│   ├── SKILL.md
│   └── 01_capsule-cohort-discipline.md
├── docs/to_claude/                             # layer 4 (gitignored, local context)
├── GITIGNORED/                                 # layer 4 (gitignored, scratch)
│   ├── FAILED_PATTERNS.md                      # → may lift to layer 1 once stable
│   ├── AGENT_PROMPT.md                         # → already lifted to scitex-dev layer 1
│   └── TRANSLATION_TEMPLATE*.md                # → already lifted to scitex-dev layer 1
└── (project source...)

~/.claude/skills/scitex/scientific/             # layer 1 mirror (consumer-side)
├── 04_clew_01_dag-as-map-and-evidence.md      # ← from scitex-dev/_skills/scientific/
├── 04_clew_02_translation-playbook.md         # ← from scitex-dev (was paper's GITIGNORED)
└── ...

~/.claude/projects/<encoded>/memory/            # layer 4 (auto-memory, machine-local)
├── feedback_spartan_home_is_login_only.md
└── project_constraints_improve_accuracy_hypothesis.md
```

## Anti-patterns

- **Cargo-culting layer 1**: copying public package skills into a
  project's `.claude/skills/` "for safety". Doubles maintenance, drifts
  immediately. Trust the consumer-side mirror at
  `~/.claude/skills/scitex/`; reference by canonical name.
- **Layer 4 forever**: leaving stable, reusable agent guidance in
  `GITIGNORED/` indefinitely. If three different projects copy the same
  pattern, lift it to layer 1.
- **Layer 3 leaking secrets**: putting hostnames, credentials, or
  paper-specific oracles into a tracked project skill. Use layer 4
  (gitignored) or layer 2 (fleet-private) instead.

## Related

- [../general/03_interface/04_skills/06_public-vs-private.md](../general/03_interface/04_skills/06_public-vs-private.md) — public-vs-private decision rule for *packages*
- [../general/01_ecosystem/06_dot_scitex_directory.md](../general/01_ecosystem/06_dot_scitex_directory.md) — `~/.scitex/<pkg-short>/` and `<project>/.scitex/<pkg-short>/` layouts
- [02_research-project_01_project-structure-root.md](02_research-project_01_project-structure-root.md) — research-project root rules; mentions `GITIGNORED/` and `docs/to_claude/`
- `scitex-agent-container/_skills/scitex-agent-container/18_full-agent-delegation.md` — sac peer/fleet usage including `spec.skills.required`
