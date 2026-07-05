---
description: |
  [TOPIC] Skills Directory Layout
  [DETAILS] Where `_skills/` sits in a package — `src/<pkg>/_skills/<pip-name>/` for standalone packages and `src/scitex/<module>/_skills/` for submodules within scitex-python. Includes the rules that every public module must have a SKILL.md, real files only (no symlinks), and the legacy `skills/` path is read-only.
tags: [scitex-general-interface-skills-directory-layout]
---

# Skills Directory Layout

## Package-level (standalone pip packages)

```
src/<pkg>/_skills/<pip-name>/
  SKILL.md                # Required index (links only, no content)
  save-and-load.md        # Focused topic with actual examples
  centralized-config.md   # Focused topic with actual examples
  supported-formats.md    # Reference table
  ...
```

Legacy `src/<pkg>/skills/SKILL.md` paths are **read-only** — do not create new ones. Migrate any encountered to `_skills/` during the next touch.

## Module-level (submodules within scitex-python)

Each public module under `src/scitex/<module>/` MUST have its own `_skills/` directory:

```
src/scitex/<module>/_skills/
  SKILL.md                # Required index — same format as package-level
  feature-topic.md        # Focused sub-skill (optional, add as needed)
  ...
```

**Rules for module-level skills:**
1. Every public module gets a `_skills/SKILL.md` — no exceptions
2. Real files only — **no symlinks** (files are bundled in wheels)
3. SKILL.md follows the same frontmatter format as package skills
4. `name` field uses `stx.<module>` format (e.g., `stx.ai`, `stx.stats`)
5. `description` is a one-line summary for AI agent discovery
6. List Python API, relevant MCP tools, and CLI commands if any
7. Sub-skill files are optional — add them when a module has complex features
8. Skip internal/private directories (`_dev`, `_mcp_tools`, `_mcp_resources`, `_sphinx_html`, `__pycache__`)

## Discovery Resolution (scitex-dev)

`scitex_dev.skills._find_skills_dir` resolves three locations in order:

1. `src/<pkg>/_skills/<pip-name>/` — **canonical**
2. `src/<pkg>/skills/` — legacy
3. `src/<pkg>/docs/MASTER/skills/` — legacy

The legacy paths are **read-only**: they are still resolvable so old packages keep working, but do not create new instances. Migrate to `_skills/<pip-name>/` when encountered.

## Cross-references

- [03_skill-md-as-index.md](03_skill-md-as-index.md) — what goes in SKILL.md vs leaf files
- [07_registration.md](07_registration.md) — entry-point wiring so the layout becomes discoverable
- [01_ecosystem/06_dot_scitex_directory.md](../../01_ecosystem/06_dot_scitex_directory.md) — private skills location
