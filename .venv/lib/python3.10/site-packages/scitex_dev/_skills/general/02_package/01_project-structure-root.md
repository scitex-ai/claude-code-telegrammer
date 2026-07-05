---
description: |
  [TOPIC] Package Root
  [DETAILS] What's allowed at the repo root for a SciTeX package — README.md, LICENSE, pyproject.toml (the only Python packaging file — no setup.py / requirements.txt / MANIFEST.in), Makefile (thin dispatcher), .gitignore/.gitattributes, CLA.md / CONTRIBUTING.md (for the CLA gate), and optional CLAUDE.md / CHANGELOG.md. Forbidden top-level dirs (`mgmt`, `project_management`, `references`, `htmlcov`, top-level `assets`, `.playground`). Hidden/scratch (`.dev`, `.old`). The `production-ready always` invariant, anti-patterns, and a pre-release checklist. For each subdirectory, see the sibling leaves (02-06).
tags: [scitex-general-package-project-structure-root]
---

# Repo Root — Package Project Structure

The repo root contains exactly the files that **must** be there. Everything else lives in a subdirectory.

> Building a *research project* instead of a package? See [`../scientific/02_research-project_01_project-structure.md`](../../scientific/02_research-project_01_project-structure.md).
>
> Sub-leaves of this section: [`./src`](02_project-structure-src.md) · [`./scripts`](03_project-structure-scripts.md) · [`./scripts/makefile`](04_project-structure-makefile.md) · [`./examples`](05_project-structure-examples.md) · [`./tests`](06_project-structure-tests.md)

## What's required at the repo root

The auditor (`scitex-dev ecosystem audit-project <pkg>`) enforces this list — every file below must be present.

| File | Audit code | Purpose |
| :--- | :--- | :--- |
| `README.md` | PS-137 | Primary entry point |
| `LICENSE` (or `LICENSE.md` / `LICENSE.txt`) | PS-138 | License text (`AGPL-3.0-only` for SciTeX — see [01_ecosystem/07_license-and-cla.md](../01_ecosystem/07_license-and-cla.md)) |
| `CHANGELOG.md` | PS-134 | Release notes (Keep-a-Changelog style; new packages start with `[Unreleased]`) |
| `CONTRIBUTING.md` | PS-135 | Contribution guide referencing the CLA |
| `CLA.md` | PS-133 | CLA agreement text (referenced by `.github/workflows/cla.yml`) |
| `pyproject.toml` | PS-101 | Package metadata + build (no `setup.py`, `requirements.txt`, `MANIFEST.in`) |
| `Makefile` | — | Thin dispatcher; logic lives in `./scripts/makefile/` (see [02_package/04_project-structure-makefile.md](04_project-structure-makefile.md)) |
| `.gitignore`, `.gitattributes` | — | VCS hygiene |
| `.claude/CLAUDE.md` (optional, **canonical**) | — | AI-agent context for this repo. Tolerated as bare `CLAUDE.md` at root for back-compat, but **must be gitignored** either way — it carries machine-local agent state. |

Required directories at root:

| Directory | Audit code | Purpose |
| :--- | :--- | :--- |
| `src/<pkg>/` | (implicit) | Package source — see [02_package/02_project-structure-src.md](02_project-structure-src.md) |
| `tests/<pkg>/` | PS-201 | Mirror of `src/<pkg>/` — see [02_package/06_project-structure-tests.md](06_project-structure-tests.md) |
| `examples/` | PS-136 | At least one runnable `<NN_>name.py` / `.ipynb` / `.sh` |
| `docs/` | (recommended) | Sphinx + assets — see [04_docs/02_sphinx.md](../04_docs/02_sphinx.md) |

Everything else belongs in a subdirectory. **Do not create new top-level directories** without strong reason — extend an existing one or use `./.dev/` for one-offs.

## README badges — coverage is required (PS-106)

Every `scitex-*` README must surface its **current test coverage** at
the top, alongside the PyPI / docs / build / license badges. Reviewers
and downstream consumers should be able to see at a glance whether the
package is well-tested without diving into CI logs.

Recommended badge line (drop into the existing `<p align="center">`
badge block near the title):

```markdown
[![coverage](https://img.shields.io/codecov/c/github/<owner>/<repo>)](https://codecov.io/gh/<owner>/<repo>)
```

Either the shields.io shorthand (above) or a direct codecov / coveralls
badge satisfies `PS-106`. The auditor scans the first ~4 KB of
`README.md`, so the badge has to live near the title — a coverage badge
buried at the bottom is invisible and doesn't count.

If the package doesn't yet upload coverage, set up
[`codecov/codecov-action`](https://github.com/codecov/codecov-action)
in `test.yml` first; the badge will then start showing real numbers
once coverage uploads start arriving.

## `pyproject.toml` is the only Python packaging file

Don't add `setup.py`, `requirements.txt`, or `MANIFEST.in`. All those concerns belong in `pyproject.toml`. Lint enforced by `REL-5`/`REL-9`/`REL-10`/`REL-11`/`E5C13` in `scitex_dev._pyproject_lint`.

## Forbidden top-level dirs (PS-102)

| Top-level dir | Why forbidden | Where it should live |
| :--- | :--- | :--- |
| `./mgmt/`, `./project_management/` | not used in scitex | (delete) |
| `./references/` | not used in scitex | (delete) |
| `./htmlcov/` | coverage artifacts | `./tests/coverage/` (gitignored) |
| `./assets/` | top-level visual noise | `./docs/assets/` |
| `./.playground/` | collapsed for easier typing | `./.dev/` |
| `./logs/` | runtime artifact | `./GITIGNORED/logs/` (or `./tests/logs/`) and add to `.gitignore` |
| `./catboost_info/` | CatBoost training artifact | gitignore `catboost_info/` |
| `./signatures/` | scratch / signing artifacts | `./GITIGNORED/signatures/` if needed locally |
| `./scitex/` | orphan module dir — confused with package | the real package is `src/<pkg>/`. For runtime state use a hidden `./.scitex/` (e.g. `./.scitex/<pkg>/runtime/logs/`), never a visible `./scitex/`. |
| `./unknown_out/` | `@stx.session` output landed at root | re-run from a script directory, or set `CONFIG.SDIR_RUN`. Move the dir aside if you need to keep it. |

## PS-103 — strict root whitelist

PS-102 forbids specific dirs by name. **PS-103** flips the polarity:
**anything at repo root that is not in the strict baseline below, not
hidden (`.*`), and not explicitly whitelisted is a violation.**

The auditor lives at `scitex_dev._cli.audit._project._root_whitelist`
and is called by `scitex-dev ecosystem audit-project <pkg>` (rule
`PS-103`, severity `E`).

### Baseline (allowed everywhere, no config needed)

```
files: README.md, LICENSE{,.md,.txt}, CHANGELOG.md, CLA.md,
       CONTRIBUTING.md, SECURITY.md,
       pyproject.toml, Makefile, CLAUDE.md

dirs:  src, tests, docs, examples, scripts, data, externals,
       dist, build, GITIGNORED

hidden: any `.*`
        (.git, .github, .scitex, .dev, .gitignore, .gitattributes,
         .pre-commit-config.yaml, .readthedocs.yaml, .coverage,
         .env, .env.example, .venv, .pytest_cache, …)
```

This matches the canonical clean layout (see `~/proj/scitex-stats`
as a reference implementation).

### Per-pkg / global overrides

Edge cases — Django frameworks, multi-package monorepos, content-
vending packages — declare their extras explicitly in
`<repo>/.scitex/dev/config.yaml`:

```yaml
audit:
  root-whitelist:
    files: [architecture.svg]            # exact basenames
    patterns: ["screenshot-*.png"]       # fnmatch globs
    dirs: [apps, static, media]          # exact dir basenames
```

The same block in `~/.scitex/dev/config.yaml` (user-level) is
unioned on top — useful for scratch directories you want allowed
across every clone.

No category-based silent exemptions: `dataset`, `template`, etc.
are NOT auto-softened. Each package self-declares.

### Project-type opts out of PS-103

Three project-types skip PS-103 with different semantic intent:

| Type | Meaning | Auditor behaviour | Examples |
| :--- | :--- | :--- | :--- |
| `special` | by-design unconventional layout (no future cleanup expected) | silent skip | `scitex-writer`, `socialia`, `scitex-orochi` (monorepo), `newb` (PyPI-alias monorepo), `scitex-ui` (npm hybrid) |
| `django` | Django framework canonical (`apps/`, `static/`, `media/`, `templates/`, …) | silent skip | `scitex-cloud` |
| `deferred` | "I know it's messy; remind me later" | **emits a `[defer]` warning listing what would have fired**, so the operator has a TODO list ready when revisiting | `scitex` umbrella |

Pick one (or combine, e.g. `[pip, django, deferred]` for a Django
app whose deployment artifacts also need a future cleanup pass).

```yaml
# scitex-writer/.scitex/dev/config.yaml — research layout
project-type:
  - pip
  - special

# scitex/.scitex/dev/config.yaml — umbrella with cleanup TODOs
project-type:
  - pip
  - deferred

# scitex-cloud/.scitex/dev/config.yaml — Django + deferred
project-type:
  - pip
  - django
  - deferred
```

`special` / `django` / `deferred` skip PS-103 only; every other PS
rule still fires under `pip`. Prefer one of these over piling
entries into `audit.root-whitelist` when the layout is stable —
the project-type label communicates *intent*, while the whitelist
just enumerates exceptions.

### Cleaning up an offending root

Ecosystem-wide non-destructive cleanup:

```bash
scitex-dev ecosystem clean-root figrecipe              # preview
scitex-dev ecosystem clean-root figrecipe --yes        # apply
scitex-dev ecosystem clean-root all -j 8 --yes         # bulk

# Moves entries into:
#   <repo>/.scitex/dev/runtime/root-violations/<YYYYmmdd-HHMMSS>/
# (gitignored under §4b — restore by `mv` back; delete after review)
```

The pre-write hook `inhibit_project_root_pollution.sh` calls into
the same `is_allowed_at_root()` helper, so write-time and audit-time
share one rule definition — schemas can't drift.

## `./docs` — human-facing documentation

- README is the entry point; deeper docs live here (`./docs/installation.md`, `./docs/details/<topic>.md`).
- `./docs/sphinx/` — Sphinx source tree (`conf.py`, `index.rst`, `*.rst`/`*.md`). See [`04_docs/02_sphinx.md`](../04_docs/02_sphinx.md) for the canonical layout.
- `./docs/sphinx/_build/` — local Sphinx build output. Gitignored.
- `./docs/assets/` — figures, screenshots, diagrams referenced from README and other docs.
- `./docs/to_claude/` — agent context files (guidelines, hooks, examples). **Must be gitignored** — local-machine artifacts, not part of the shipped repo.
- `./docs/adr/` — Architecture Decision Records. See [Architecture Decision Records (ADRs)](#architecture-decision-records-adrs) below.
- `./GITIGNORED/` — catch-all file-based scratch channel.

### Production-served Sphinx HTML — bundled in `src/<pkg>/_sphinx_html/`

For a package's docs to appear on **<https://scitex.ai/apps/docs/>** after `pip install <pkg>`, the **pre-built HTML must ship inside the wheel**. Convention:

```
docs/sphinx/_build/html/        # local Sphinx output; gitignored
src/<pkg>/_sphinx_html/         # bundled in the wheel; refreshed at release
```

`scitex_dev.docs.get_docs(format="html")` resolves first to the in-wheel `_sphinx_html/`, then falls back to local `_build/`. See [04_docs/02_sphinx.md](../04_docs/02_sphinx.md) for full release recipe.

## Architecture Decision Records (ADRs)

An **ADR** captures one significant architectural decision: the context that forced it, the decision taken, and the consequences. ADRs are a **recommended (not mandated)** ecosystem convention — a repo with no `docs/adr/` is fine. But the moment you *do* keep ADRs, they follow a fixed shape so they stay scannable across the ecosystem.

**Scope: all project kinds** — package, research, grant, draft. Any repo with non-obvious architectural decisions benefits.

### Location + filename

ADRs live at `docs/adr/NNNN-<kebab-slug>.md`:

- `NNNN` — 4-digit zero-padded **sequential** number (`0001`, `0002`, …). The sequence is the chronological order decisions were taken.
- `<kebab-slug>` — lowercase kebab-case summary (`isolation-hardening`, `a2a-v1-compliance`).

```
docs/adr/
├── 0001-isolation-hardening.md
├── 0002-runtime-home-directory.md
└── 0003-a2a-v1-compliance.md
```

### Lean template (exactly five sections)

```markdown
# ADR: <Short title> (<YYYY-MM-DD>)

## Status
Proposed | Accepted | Superseded by ADR-NNNN | Deprecated.

## Context
The forces at play — what problem / pressure forced a decision. (A
`## Problem` heading is the common synonym and is accepted.)

## Decision
What we decided to do, stated as a positive assertion.

## Consequences
What becomes easier and what becomes harder as a result — the
trade-offs, follow-ups, and things now ruled out.
```

Keep it lean. The proven exemplar set is **`scitex-agent-container/docs/adr/`** (0001 isolation-hardening, 0004 a2a-v1-compliance, 0009 claude-setup-delivery) — mirror that depth and tone. Tolerated variants the auditor accepts: `**Status:**` as a bold-line instead of an H2; `## Problem` in place of `## Context`; `## Decisions` (plural) in place of `## Decision`. Sections beyond the five (Implementation, Rationale, References, Addendum, …) are welcome — the five are the *minimum*.

### Enforcement (PS-173, warn during adoption)

`scitex-dev ecosystem audit-project` runs **PS-173** *only when `docs/adr/` exists*:

- (a) every `*.md` matches `NNNN-<kebab-slug>.md` (4-digit prefix, kebab slug);
- (b) each ADR has a title (H1) plus Status / Context / Decision / Consequences.

A repo with **no** `docs/adr/` produces **no finding** (presence is recommended, not mandated). Severity is **W during adoption** — promote to E once the ecosystem's ADR dirs comply.

## `./templates` — wheel-vs-git payload separation

When a package ships **bulky content** that belongs in git but should NOT bloat the PyPI wheel (e.g. `scitex-template/templates/<id>/` ~22 MB scaffolds), vendor it under `./templates/`, exclude from the wheel via hatch, and fetch on first use into `~/.scitex/<pkg-short>/cache/`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/<pkg>"]
# templates/ NOT in the wheel — populated at runtime by a shallow clone
```

When NOT to use: anything imported by `src/`, small (<100 KB) static data, content the package can't function without.

## Hidden / scratch directories

| Dir | Use |
| :--- | :--- |
| `./.dev/` | Single scratch space — sandbox tests, parking-lot ideas, half-baked experiments. Gitignored. Organize by category subdir (`./.dev/<category>/`). **Promote** valuable code out (`→ src/`, `examples/`) or **prune** periodically. |
| `./.old/` | **Hide, don't delete** — keeps git history clean while removing visual noise. Acceptable to clear in a dedicated cleanup commit once nothing references it. |

## Production-ready always

The main branch must be publishable **today**, regardless of in-flight work:

- Half-finished features are on `feature/<verb>-<object>` branches, never on `main`.
- Obsolete files hidden under `.old/`, not littering visible paths.
- `./examples/` runs cleanly start-to-finish.
- Tests pass on `main`.
- README accurately describes current state, not aspirational state.

## Anti-patterns

- **Top-level junk** (any `*.png` debug screenshot, `tmp_test.py`, `quick_check.py`, `debug.log`, `untitled.ipynb`, `current-snapshot.yml`, …) — flagged by **PS-103** strict whitelist. Move to `./docs/assets/` (if referenced from docs), `./.dev/<category>/` (if scratch), or delete. Bulk cleanup: `scitex-dev ecosystem clean-root <pkg>` quarantines into `<repo>/.scitex/dev/runtime/root-violations/<ts>/`. Legitimate exceptions go in `audit.root-whitelist` of `.scitex/dev/config.yaml`.
- **Naked `src/` next to a real package layout** — pick one. SciTeX packages always use `src/<package_name>/`.
- **`tests/` that doesn't mirror `src/`** — see [02_package/06_project-structure-tests.md](06_project-structure-tests.md).
- **Examples with no `_out/`** — readers can't see what the demo produces. See [02_package/05_project-structure-examples.md](05_project-structure-examples.md).
- **`.dev/` with no categorization** — devolves into a junk drawer.
- **`.old/` that grows forever** — prune archives older than two release cycles.
- **Importing the umbrella `scitex` from `src/` of a scitex-* package** — see [02_package/02_project-structure-src.md](02_project-structure-src.md).

## Pre-release / major-review checklist

- [ ] Every `src/.../*.py` has a corresponding `tests/.../test_*.py` (or documented exception)
- [ ] Every example has a tracked `_out/` and a `tests/examples/test_*.py`
- [ ] No half-finished work outside a `feature/*` branch
- [ ] No top-level files outside the allowed-at-root list
- [ ] `.dev/` has only categorized subdirs; nothing rotted >1 quarter
- [ ] `.old/` doesn't dominate any directory listing
- [ ] README reflects current behavior, not aspirational
- [ ] `make ci-local` (or equivalent) passes from a clean clone
- [ ] No `scitex` umbrella import in `src/` (see [02_package/02_project-structure-src.md](02_project-structure-src.md))
- [ ] `scitex-dev ecosystem audit-project <distribution>` shows no violations
- [ ] All five required community files at root (PS-133/134/135/137/138):
      `README.md`, `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CLA.md`
- [ ] `examples/` exists with at least one runnable file (PS-136)
