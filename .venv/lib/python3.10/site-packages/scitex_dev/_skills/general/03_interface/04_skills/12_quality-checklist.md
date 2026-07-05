---
description: |
  [TOPIC] Skills Quality Checklist
  [DETAILS] Release-gate checklist that every `_skills/` directory in every SciTeX package must pass before a version bump — directory layout (one `_skills/` per package, one SKILL.md per sub-skill, no `legacy/` or `.old/`), two-level `NN_<category>_NN_<topic>.md` naming with `git mv` for renames, SKILL.md as index-only (≤~4 KB, ≤~80 lines), leaf-file no-monolith rule (≤10 KB per leaf, one topic each), no-duplication with `general/` rules, cache-friendly stable leaf ordering, and the concrete release-gate command to verify links. Use as the pre-release sign-off for the skills tree.
tags: [scitex-general-interface-skills-quality-checklist]
---

# SciTeX Package Skills — Quality Checklist

Canonical reference: this directory (`src/scitex/_skills/general/`). Every
SciTeX ecosystem package **MUST** pass this checklist before release; audit
findings from 2026-04-23 drove the concrete rules below.

## 0. Scope

Applies to every `src/<pkg>/_skills/<skill>/` directory in every package in
the ecosystem. Does **not** apply to private skills under
`~/.scitex/<pkg>/shared/skills/` (those follow the private-skill schema in
`06_public-vs-private.md`).

## 1. Directory structure

- [ ] One `_skills/` directory per package at `src/<pkg>/_skills/`.
- [ ] Each sub-skill lives in its own subdirectory: `_skills/<skill-name>/`.
- [ ] **Exactly one** `SKILL.md` per sub-skill directory. **NEVER** ship a
      parallel `SKILL_INDEX.md`, nested `_skills/<pkg>/SKILL.md`, or any
      other alias index — one sub-skill → one index.
- [ ] **NEVER** ship `legacy/` or `.old/` subdirectories inside `_skills/`.
      Delete before release; if retention is required, move outside
      `_skills/`.

## 2. File naming & ordering

- [ ] Every leaf `.md` carries a **2-digit zero-padded numeric prefix**:
      `01_`, `02_`, …, `99_`. No gaps within a group.
- [ ] Prefixes express **logical order**, not alphabetical. Recommended
      grouping (mirrors `general/`):
      - `01–09` core concepts / interfaces
      - `10–19` workflows / guides
      - `20–29` standards / conventions
      - `30–39` architecture / internals
      - `40–49` lessons, scratch, playground
- [ ] `SKILL.md` itself has **no** numeric prefix.
- [ ] Filenames are **kebab-case** after the prefix:
      `01_ecosystem/01_upstream-and-downstream.md`.
- [ ] **NEVER** rename a prefixed file by hand; use `git mv` so history is
      preserved.

## 2a. Frontmatter must be first bytes — no header/footer

- [ ] No file in `_skills/` opens with an HTML-comment banner (`<!-- --- … --- -->`) or any other content before the YAML `---`. Any such block pushes the frontmatter below line 1 and the Claude Code loader sees no metadata.
- [ ] No file ends with `<!-- EOF -->` or similar trailing markers — adds noise and risks last-block parser confusion.
- [ ] Lint check: `python3 -c "import pathlib; print([str(f) for f in pathlib.Path('src/scitex/_skills').rglob('*.md') if f.read_text().startswith('<!-- ---') or f.read_text().rstrip().endswith('<!-- EOF -->')])"` returns `[]`.
- [ ] If your editor auto-inserts these on save, disable that behavior for files under `_skills/`, `skills/`, `agents/`, `commands/`, and `.claude/`. Run the cleanup script in [05_frontmatter-metadata.md](05_frontmatter-metadata.md) §0 as a backstop before commit.

## 3. SKILL.md as index only

- [ ] `SKILL.md` contains frontmatter (`name`, `description`,
      `user-invocable`) plus a short intro plus **grouped links** to every
      sibling `.md`. **MUST NOT** contain substantive content beyond the
      intro.
- [ ] Every sibling `.md` leaf is listed exactly once in `SKILL.md`. No
      missing entries, no dead links.
- [ ] Links use the **new prefixed filenames**; no stale references to
      un-prefixed legacy names.
- [ ] `SKILL.md` itself stays under **~4 KB / ~80 lines**. If growing
      beyond, split the content into a new leaf — do not let the index
      itself become a monolith.

## 4. Leaf file size — no-monolith rule

- [ ] No leaf `.md` exceeds **~10 KB** (~200 lines). Split if larger.
- [ ] No leaf is a near-empty stub (<300 B) unless it is an explicit
      placeholder with a `TODO` marker.
- [ ] Each leaf covers **one focused topic**. The filename describes the
      topic precisely in 2–5 words.

## 5. No duplication / no parallel content

- [ ] **NEVER** maintain two versions of the same topic in one package
      (e.g. top-level `app-lifecycle.md` AND `references/app-lifecycle.md`).
      Pick one canonical location.
- [ ] A `references/` subdirectory is allowed **only** when every file
      inside is a pure technical reference that differs in kind (not in
      depth) from top-level guides, and every file is indexed from
      `SKILL.md`.
- [ ] **NEVER** restate general-ecosystem rules (four interfaces, env-var
      prefix, branding, version management) inside a package skill. Link
      to `general/` instead:
      `See [../general/01_ecosystem/04_environment-variables.md] for the canonical rule.`

## 6. No contradictions with `general/`

- [ ] Package must not redefine or contradict any rule documented in
      `src/scitex/_skills/general/`. Specifically:
  - [ ] Env-var prefix is `SCITEX_<MODULE>_*` (never bare `SCITEX_*`).
  - [ ] Four-interface delegation chain is Python API → CLI → MCP → Skills
        (optional HTTP). No custom interface layering.
  - [ ] `import scitex` in docs/READMEs (never `import scitex as stx`).
  - [ ] No `ywatanabe@scitex.ai` signature in package-shipped docs.
  - [ ] Skill source of truth is `src/<pkg>/_skills/…` — **NEVER** edit
        the exported copies under `~/.claude/skills/scitex/` directly.

## 7. Cache-friendliness (context-cost hygiene)

- [ ] Leaf ordering in `SKILL.md` is **stable** across releases —
      re-ordering busts prompt cache for every downstream consumer.
- [ ] Edits that only add content append near the end of a leaf where
      possible; refactors that split a file are acceptable cache
      invalidation but should not happen more than once per release cycle.
- [ ] SKILL.md index is **markdown-linked** (`[text](file.md)`) by default,
      not `@`-included, so agents can lazy-load leaves. Promote a leaf to
      `@`-include only when it is genuinely always-needed for the skill.

## 8. Release gate

Before bumping the package version:

- [ ] `find src/<pkg>/_skills -name '*.md' | sort` matches the links in
      every `SKILL.md` (no dead links, no orphans).
- [ ] No file in `_skills/` exceeds 10 KB.
- [ ] No `_skills/legacy/` or `_skills/.old/` present.
- [ ] Exported skills refreshed via `scitex-dev skills export` so
      `~/.claude/skills/scitex/<pkg>/` mirrors source.

## 9. Automation

Programmatic linter ships as `scitex-dev ecosystem audit-skills <distribution>` —
mirrors `audit-cli`, `audit-mcp-tools`, `audit-python-apis`. Rule codes
`SK<§><idx>`:

| Rule | §  | What it checks |
|------|----|----------------|
| SK-101 | §1 | `_skills/` directory exists in package source |
| SK-102 | §1 | `_skills/<pip-name>/SKILL.md` index file present |
| SK-103 | §1 | no forbidden subdirectories (`legacy/`, `.old/`) |
| SK-104 | §1 | no duplicate index (`SKILL_INDEX.md`, `INDEX.md`, `README.md` shadowing) |
| SK-201 | §2 | every leaf `.md` carries a 2-digit numeric prefix |
| SK-202 | §2 | `SKILL.md` itself has no numeric prefix |
| SK-203 | §2 | filenames are kebab-case after the prefix |
| SK-210 | §2a | no HTML-comment header banner above frontmatter |
| SK-211 | §2a | no `<!-- EOF -->` trailing marker |
| SK-301 | §3 | `SKILL.md` ≤ 4 KB / 80 lines |
| SK-302 | §3 | every sibling leaf is referenced from `SKILL.md` (no orphans) |
| SK-401 | §4 | no leaf exceeds 10 KB / 200 lines |
| SK-601 | §6 | skill text uses bare `import scitex` (not `as stx`) |
| SK-105 | §1 | `01_installation.md` present (mandatory) |
| SK-106 | §1 | `02_quick-start.md` present (mandatory) |
| SK-107 | §1 | `03_python-api.md` present iff package exposes any public Python API |
| SK-108 | §1 | `04_cli-reference.md` present iff `[project.scripts]` ships any entry |
| SK-109 | §1 | `05_mcp-tools.md` present iff MCP server entry-point registered |
| SK-110 | §1 | `06_http-api.md` present iff package ships HTTP routes |
| SK-111 | §1 | `20_env-vars.md` present iff source references any `SCITEX_<MOD>_*` env var |
| SK-701 | FM | every file has a `---` frontmatter block at line 1 |
| SK-702 | FM | frontmatter contains required `name:` |
| SK-703 | FM | frontmatter contains required `description:` |
| SK-704 | FM | frontmatter contains required `tags:` |
| SK-705 | FM | leaf MUST NOT carry `name:` field (filename = identity) |
| SK-706 | FM | SKILL.md `description:` contains inline markers `[WHAT]`, `[WHEN]`, `[HOW]` (each on its own line is fine) |
| SK-708 | FM | SKILL.md `name:` exactly matches the package's pip-name |
| SK-709 | FM | SKILL.md `tags:` equals `[scitex-<pkg>]` exactly (one canonical tag) |
| SK-710 | FM | leaf `tags[0]` equals `scitex-<pkg>-<slug>` (canonical-first ordering) |
| SK-711 | FM | leaf `description:` contains inline markers `[TOPIC]` and `[DETAILS]` |

### §1 Conditionality

SK-105–SK-106 are unconditional. SK-107–SK-111 are gated by pyproject.toml inspection / source scanning — auditor checks whether the package actually ships the interface (public Python API / `[project.scripts]` / MCP entry-point / HTTP framework import / `SCITEX_<MOD>_*` env reference) before nagging for the missing leaf.

### §FM Auto-fix

`scitex-dev ecosystem audit-skills <pkg> --fix` mechanically fixes SK-705 (strip leaf `name:`), SK-709 (rewrite SKILL.md `tags:` to `[scitex-<pkg>]`), and SK-710 (prepend canonical `scitex-<pkg>-<slug>` to leaf `tags`). Frontmatter-only, idempotent, prints a diff. SK-706 / SK-711 (description marker presence) require manual edits — description is the source of truth.

Run examples:

```bash
scitex-dev ecosystem audit-skills scitex-io
scitex-dev ecosystem audit-skills scitex-io --json
scitex-dev ecosystem audit-skills scitex-io --rule SK-210 --rule SK-211
```

Exit codes: `0` = clean, `1` = violations, `2` = package not installed.

Tracking: see `02_package/03_quality.md` (sibling) for the broader release
checklist.
