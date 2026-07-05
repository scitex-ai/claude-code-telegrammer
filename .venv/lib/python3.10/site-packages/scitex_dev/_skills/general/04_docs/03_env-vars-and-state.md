---
description: |
  [TOPIC] Env Vars And Local State
  [DETAILS] Canonical convention for declaring per-package environment variables (`.env.example` at repo root, commented entries, all keys SCITEX_<MODULE>_<NAME>) and surfacing local-state directories (`~/.scitex/<pkg-short>/` and `<proj-root>/.scitex/<pkg-short>/`) in the README. Replaces the older standalone `## Environment Variables` H2 section.
tags: [scitex-general-docs-env-vars-and-state]
---

# Environment Variables & Local State

## Two acceptable styles (pick one — don't ship both)

**Style A: README table** — fine for small lists (≲5 vars). The
README's `## Environment Variables` H2 contains a 3-column table
(Variable / Description / Example). No `.env.example` at repo root.

**Style B: `.env.example` file** — cleaner for many vars. The README
references the file from `## Installation > ### Configuration`; no
table in the README. Users `cp .env.example .env` to bootstrap.

The audit (PS-130) fires only when **both** are present — the two will
drift. Pick one.

## Why no triplication

Each `scitex-*` package historically duplicated its env-var list in:
1. README markdown table
2. `_skills/<pkg>/20_env-vars.md` page
3. Inline strings inside `_cli.py`

That triplication drifts fast. Style A and Style B both keep ONE
human-edited source of truth.

## File: `.env.example` at repo root

Required for any package that reads at least one `SCITEX_<MODULE>_*`
variable. Format:

```env
# <pkg> environment variables
#
# Copy this file to `.env` (gitignored) and edit values for your setup.
# CLI flags always override env vars when both are given. Variables
# follow the SciTeX ecosystem convention: SCITEX_<MODULE>_<NAME>.
#
# Local state (per the SciTeX local-state convention) is read from:
#   ~/.scitex/<pkg-short>/               user-global config + cache
#   <proj-root>/.scitex/<pkg-short>/     project-local overrides (preferred)

# <one-line description of variable A>
# SCITEX_<MODULE>_VAR_A=<example value>

# <one-line description of variable B>
# SCITEX_<MODULE>_VAR_B=<example value>
```

Rules:
- File **must** live at the repository root (not under `docs/`, not
  under `src/`).
- Every entry is **commented out** (leading `#`) so a direct `cp
  .env.example .env` produces a usable starter where the user only
  uncomments what they need.
- One blank-line-separated stanza per variable; the comment above the
  `KEY=value` line describes what the variable does.
- `.env` itself is gitignored (add to `.gitignore` if missing).

## README integration

The README documents env vars **inside the `## Installation` section**,
NOT in a separate `## Environment Variables` H2. The canonical block:

```markdown
### Configuration

Copy [`.env.example`](.env.example) to `.env` (gitignored) at your
project root, then edit:

```bash
cp .env.example .env
$EDITOR .env
```

CLI flags always override env vars. The full list of variables (with
inline comments) lives in `.env.example`.

<details>
<summary><strong>Local state directories</strong></summary>

<br>

`<pkg>` reads optional config + cache from the canonical SciTeX
local-state locations. **`<pkg-short>` strips the `scitex-` prefix**
(e.g. `scitex-ssh` → `ssh`, `scitex-scholar` → `scholar`). See
`01_ecosystem/06_dot_scitex_directory.md` for the full rule.

| Path                              | Scope         | Purpose                              |
|-----------------------------------|---------------|--------------------------------------|
| `~/.scitex/<pkg-short>/`          | user-global   | per-user config, credentials, cache  |
| `<proj-root>/.scitex/<pkg-short>/` | project-local | overrides for the current repo       |

Project-local wins when both exist. Both are optional.

</details>
```

Local state lives inside its own collapsed `<details>` block — most
users never need to know about these directories, so we fold them by
default. Only power users opening the disclosure care.

## Why no big README table?

A markdown table in the README was the old convention. It drifted from
the actual code (variables added in code but never documented; variables
removed but still listed). `.env.example` is the docs AND the seed
config — they can't drift because users actually copy the file.

## Audit rules

| Code  | Enforces                                                                        |
|-------|---------------------------------------------------------------------------------|
| PS-129 | Package referencing `SCITEX_<MODULE>_*` env vars must ship `.env.example` at root |
| PS-130 | README has no standalone `## Environment Variables` H2 (move into Installation)  |

## Reference exemplar

`scitex-ssh` — see `.env.example` and the `## Installation > ### Configuration / ### Local state` blocks in its README.
