---
name: scitexification
description: |
  [WHAT] Scitexification — the verb: translate existing code (a script, a notebook, a small repo, a published-paper supplement) into SciTeX form so it gains the ecosystem's session-managed I/O, scitex-clew evidence binding, publication-quality figures, and project structure. Single source of truth for the migration act itself, package-agnostic; per-package patterns delegate to the per-pkg SKILL.md, and Clew-specific specialization layers on top of this skill via `scientific/04_clew_*`.
  [WHEN] You have existing code that works and want to bring it into the SciTeX ecosystem with minimal rewrite, OR an agent is asked to translate a research bundle, paper supplement, or one-off notebook into a SciTeX project. Load this skill BEFORE picking the per-chapter topic.
  [HOW] Read this SKILL.md first to orient on the 5-stage translation arc; then drill into the topic chapter you need next (`01_io-patterns`, `02_session-config`, `03_plt-patterns`, `04_repro-clew`, `05_naming-and-numbering`). Per-package details (full stx.io API surface, figrecipe figure types, etc.) live in the corresponding per-pkg SKILL.md — this skill references them rather than restating.
tags: [scitexification]
requires:
  # Scitexification is the translation act; the four package-level
  # companions supply the API knowledge an agent needs to actually
  # translate-and-resolve. Loading `scitexification` should also
  # surface these. See 00_playbook.md §"Required companion skills".
  - scitex-session
  - scitex-io
  - figrecipe
  - scitex-clew
user-invocable: true
primary_interface: skills
interfaces:
  python: 0-3
  cli: 0-3
  mcp: 0-3
  skills: 3
  http: 0
---

<!--
SSoT status (2026-06-13):
  - This SKILL.md is the overview / index for the 6-file scitexification series.
  - The 01-05 chapter files are WRITTEN (substantive content: translation
    inventories, the symlink_to= idiom, worked before/after examples, and
    corner cases per stage), delegating full per-package API surface to the
    companion pkg SKILLs. (They superseded the 2026-06-12 #167 link-stubs.)
  - Discovery (consumer-side `spec.claude.skills: [scitexification]` declarative
    interface) is gated on a separate scitex-dev / SAC contract decision; see
    A2A thread `48d2324b` (proj-paper-scitex-clew ↔ proj-scitex-dev) and
    the "Discovery" section below.
-->

# Scitexification — the translation act

`pip install scitex-dev` (no extras needed for the skill itself).

> **scitexify** *(verb, derived)* — to convert existing research code into
> the SciTeX idiom: session-managed I/O, project-structured outputs, evidence-
> bound claims, publication-quality figures, mirrored test layout.

This skill is the **single source of truth** for the translation act. It is
deliberately package-agnostic at the top level; each chapter delegates
package-specific patterns to the corresponding per-pkg SKILL.md so the per-
package teams own the surface area they ship.

> **Canonical universal playbook — [00_playbook.md](00_playbook.md).** Read
> this first when scitexifying any artefact. It coins the vocabulary
> (`scitexify` / `scitexification` / `scitexified`), fixes the universal
> contract (universal inputs, pre-flight, phase dispatch, done condition,
> forbidden), and frames the **honest source-grounding** principle — "attempt
> every claim, ground where possible, and when ungroundable include the
> claim with `null` + a reason, NEVER silently omit" — as a general
> scientific-integrity norm independent of any specific evaluator. The
> per-chapter files (01–05) drill into stage-specific patterns; the
> `04_clew_*` siblings are clew-tracked specialisations that compose on
> top of the universal playbook.

## When to load this skill

Load when **any** of the following is true:

- You inherited working code (script, notebook, small repo) and want it
  inside the ecosystem with minimal rewrite.
- An agent is asked to translate a research bundle, paper supplement,
  or one-off notebook into a SciTeX project.
- You are about to hand-write `data/results/claims.json` (or any
  results/output JSON, etc.) — **stop**, read chapter `04_repro-clew`,
  use the API.
- You are about to copy-paste a `matplotlib` figure call from a paper
  template — **stop**, read chapter `03_plt-patterns`, use the figrecipe
  pattern.

Do **not** load this skill when:

- You are starting a brand-new SciTeX project from scratch — go to
  [`../02_research-project_*`](../) (project structure rules).
- You are auditing or building a SciTeX **package** (i.e. publishing
  scitex-xxx) — go to [`../../general/`](../../general/) (engineering
  rules for package authors).

## The 5-stage translation arc

Scitexification is **not** a search-and-replace. It is five staged transforms
each of which holds independently:

| Stage | Chapter | What changes | What stays the same |
|---|---|---|---|
| 1 | [01_io-patterns](01_io-patterns.md) | Every `open()` / `np.load` / `pd.read_csv` / `pickle.load` becomes `stx.io.load(...)`; every `np.save` / `pickle.dump` / `df.to_csv` becomes `stx.io.save(..., symlink_to=...)`. DAG composition (output of step N is input of step N+1) becomes visible at the filesystem level. | Your algorithm. Your data shapes. Your business logic. |
| 2 | [02_session-config](02_session-config.md) | The script entry-point becomes `@stx.session.start(...)`; magic numbers and paths become `CONFIG.<KEY>` lookups against `config/*.yaml`; logging becomes the session logger. | Function call structure. Module organization. Test cases. |
| 3 | [03_plt-patterns](03_plt-patterns.md) | Every `plt.savefig(...)` becomes a `stx.io.save(fig, ...)` (so the figure is bound to a session output), and every visual style choice ladders up to figrecipe's publication-quality primitives. | Figure intent (what comparison, what axis labels). What information the figure carries. |
| 4 | [04_repro-clew](04_repro-clew.md) | Final-mile assertions (`accuracy was X%`, `effect size was Y`) become registered Clew **claims**, each evidence-bound to the file that produced it; the results/output JSON is composed by iterating registered claims through `scitex_clew.list_claims()` + `scitex_clew.verify_claim()` and filtering to `source_verified=True`, not hand-written. | What you are claiming. Your numbers. |
| 5 | [05_naming-and-numbering](05_naming-and-numbering.md) | `cnn_v3_final_FIXED2.py` becomes `scripts/03_cnn.py` (zero-filled, sortable, mirrored under `tests/`); IDs and ordinals become readable symlinks per `02_research-project_09`. | Your filenames as a *concept*. The numbers themselves (after zero-fill). |

Doing stages 1+2 alone gets you a *runnable* SciTeX project — stage 3+ are
strictly additive. If a project's deadline is tight, stages 1+2 are the
minimum viable scitexification; stages 3, 4, 5 land in subsequent PRs.

## Relationship to other skills

This skill **does not duplicate** content elsewhere; it composes them.

- For project **structure** (where files go, what `./config/` looks like,
  what `./data/` allows): see `../02_research-project_*`. This skill
  assumes a working knowledge of that structure as the *target* of the
  translation.
- For per-package **API surface** (the full `stx.io` save/load type
  matrix, figrecipe's figure types, scitex-clew's primitive operations):
  see the per-pkg SKILL.md (`~/.claude/skills/scitex/scitex-io/`,
  `.../figrecipe/`, `.../scitex-clew/`). This skill teaches *which*
  primitive to reach for during translation, not *what* the primitive
  does internally.
- For **Clew-specific** translation (project-aware DAG, evidence-bound
  claims, the validity chain): see `04_clew_*` skills. Those are
  specializations of scitexification stages 1+2+4 for the Clew-tracked
  flow. If you only need to scitexify and *don't* need Clew
  verifiability, ignore the `04_clew_*` skills.
- For **PDF reporting** (recurring scientific PDF deliverables): see
  `03_reporting_*`. Reporting is a *downstream* concern; scitexify first,
  then report.

## Tags & discovery

This skill uses a parent + sub-tag scheme:

```
tags: [scitexification]              # the umbrella tag — include all 5 chapters
tags: [scitexification, scitexification.io]      # chapter 01 only
tags: [scitexification, scitexification.session] # chapter 02 only
tags: [scitexification, scitexification.plt]     # chapter 03 only
tags: [scitexification, scitexification.clew]    # chapter 04 only
tags: [scitexification, scitexification.naming]  # chapter 05 only
```

Consumer-side declarative interface (target, gated on the scitex-dev /
SAC discovery contract — see A2A thread `48d2324b`):

```yaml
# <project-root>/.scitex/dev/config.yaml
skills:
  tags: [scitexification]            # full series
  # or, for a stripped-down subset:
  tags: [scitexification.io, scitexification.session]
```

Until the declarative-discovery contract is finalized, an agent can
manually expand the tag:

```bash
scitex-dev skills tags-expand scitexification
```

and read the printed paths. The reference consumer
([proj-paper-scitex-clew](https://github.com/...)) drives the
prompt-side migration plan: their bespoke
`PROMPT_SCITEX_TRANSLATION_FOR_CLEW.md` will be retired once this
skill ships and is wired through the discovery contract.

## Pitfalls (the migration traps)

Patterns that look "almost SciTeX" but aren't, and that this skill
exists to keep you out of:

1. **Hand-writing `claims.json` / any results/output JSON** even though the
   project has Clew registered. The hand-written JSON drifts from the
   evidence-binding the registered claims actually have. Always compose
   from `scitex_clew.list_claims()` + filter on
   `scitex_clew.verify_claim(c).source_verified` — see chapter 04.
2. **Calling `plt.savefig` from a SciTeX session script** because
   "matplotlib already wrote the file." The file lands outside the
   session's output dir, gets timestamped against the wrong run, and
   silently breaks `make repro`. Always wrap in `stx.io.save(fig, ...)`
   — see chapter 03.
3. **Mixing `os.path.join(...)` and `CONFIG.PATH.<KEY>`** inside the
   same script. Either fully translate to the CONFIG lookup or stay
   fully on `os.path.join` for the call site; mixing is the loudest
   tell that scitexification stage 2 was rushed. See chapter 02.
4. **Renaming `final_v3_FIXED.py` to `script_final_v3_FIXED.py`** under
   the impression that putting it in `scripts/` is enough. Stage 5
   exists because filename hygiene is *load-bearing* for downstream
   reproducibility — see chapter 05.
5. **Skipping `tests/` mirroring** because "the script already works."
   See `../02_research-project_06_project-structure-tests.md`; the
   mirroring is what lets `audit-project` catch drift.

## Status (2026-06-13)

- ✅ This overview SKILL.md drafted.
- ✅ Chapters `01–05` **written** (substantive: per-stage translation
  inventories, the `symlink_to=` DAG idiom, worked before/after examples,
  corner cases; full per-pkg API delegated to the companion SKILLs).
  Dogfooded during the proj-paper-scitex-clew prompt retirement (the
  solver auto-loads this skill instead of a bespoke prompt).
- ⏳ Parent + sub-tag discovery syntax (`scitexification` vs
  `scitexification.io`) requires a small extension in
  `scitex-dev/_cli/skills/_tags.py` — separate issue to be filed.
- ✅ Chapter 04 uses scitex-clew **primitives** (`list_claims`,
  `verify_claim`, `render_dag`) rather than proposing a new
  `emit_results` API. Rationale: scitex-clew stays general-purpose;
  the output/results shape (which keys, which schema) is an experiment-
  specific concern, owned by the consumer (proj-paper-scitex-clew,
  MNIST template, etc.) as a 10-line iterate+filter+emit helper.
  Per operator decision (Telegram msg 125).
- ⏳ Consumer-side discovery contract (`spec.claude.skills:
  [scitexification]` auto-loading) tracked in A2A thread `48d2324b`
  between proj-paper-scitex-clew ↔ proj-scitex-dev.

## References

- `~/.claude/skills/scitex/scitex-io/SKILL.md` — full `stx.io` API surface.
- `~/.claude/skills/scitex/scitex-session/SKILL.md` — `@stx.session.start`
  contract + CONFIG mechanics.
- `~/.claude/skills/scitex/scitex-clew/SKILL.md` — clew primitives,
  registration, verification.
- `~/.claude/skills/scitex/figrecipe/SKILL.md` — figrecipe figure types,
  publication-quality defaults.
- `~/.claude/skills/scitex/scitex-template/SKILL.md` — the cookiecutter
  research-project scaffold (the *target* shape of scitexification).
- [`../02_research-project_*`](../) — what the scitexified result should
  look like structurally.
- [`../04_clew_*`](../) — Clew-tracked specialization of stages 1+2+4.
- [`../05_private-skills_01_consumer-project.md`](../05_private-skills_01_consumer-project.md)
  — where consumer-project-private notes live (post-scitexification).
