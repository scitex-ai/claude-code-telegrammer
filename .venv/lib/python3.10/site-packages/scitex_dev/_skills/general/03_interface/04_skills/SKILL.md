---
description: |
  [TOPIC] Interface Skills
  [DETAILS] How a SciTeX package exposes agent-facing skills — `_skills/<pip-name>/` directory layout, SKILL.md as index-only, two-level `NN_<category>_NN_<topic>.md` naming, no-monolith leaf-file rule (≤10 KB per file, ≤80 lines per SKILL.md), registration via `[project.entry-points."scitex_dev.skills"]`, editable-vs-wheel install resolution, public-vs-private split, frontmatter metadata, ecosystem-wide `general/` inheritance via scitex-dev, scaffold template (`scitex-dev skills init`), export workflow to `~/.claude/skills/scitex/`, and the release-gate quality checklist. Use when adding or auditing `_skills/` in a package.
tags: [scitex-general-interface-skills-index]
---

# SciTeX Skills Interface — Index

Canonical rules for the **Skills** interface (the fourth of the five — Python API, CLI, MCP, **Skills**, optional HTTP). Skills provide structured documentation for AI agents to discover package capabilities. Rules below are **abstracted from convergence across the ~25 main packages** in `scitex_dev.ecosystem.ECOSYSTEM` that have substantive skills (≥5 leaves); see [01_overview.md](01_overview.md) for the reference cohort. Split into focused leaves; load only the section you need.

## Open TODOs

- [TODO.md](TODO.md) — open items, audit tools, package sweeps, scitex-dev implementation work.

## Sections

| File                                                                       | Topic                                                              |
|----------------------------------------------------------------------------|--------------------------------------------------------------------|
| [01_overview.md](01_overview.md)                                           | Practical guide: workflow, lessons, reference cohort               |
| [02_directory-layout.md](02_directory-layout.md)                           | Package-level + module-level `_skills/` directory layout           |
| [03_skill-md-as-index.md](03_skill-md-as-index.md)                         | SKILL.md as index-only; sub-skill file format; converged template  |
| [04_numbered-prefix-convention.md](04_numbered-prefix-convention.md)       | Two-level `NN_<category>_NN_<topic>.md` naming + standard-5 leaves |
| [05_frontmatter-metadata.md](05_frontmatter-metadata.md)                   | YAML frontmatter — required, recommended, dropped fields           |
| [06_public-vs-private.md](06_public-vs-private.md)                         | Where a skill belongs — public package vs `~/.scitex/<pkg>/`       |
| [07_registration.md](07_registration.md)                                   | Entry points, hatch config, force-reinstall verification           |
| [08_editable-installation.md](08_editable-installation.md)                 | Editable (`pip install -e`) vs wheel (PyPI) source resolution      |
| [09_export-commands.md](09_export-commands.md)                             | `scitex-dev skills` commands; source-of-truth discipline           |
| [10_how-to-update.md](10_how-to-update.md)                                 | Edit workflow, verification, non-editable install fallback         |
| [11_troubleshooting.md](11_troubleshooting.md)                             | Common failure modes and fixes                                     |
| [12_quality-checklist.md](12_quality-checklist.md)                         | Release-gate checklist for `_skills/` directories                  |
| [13_standard-template.md](13_standard-template.md)                         | Scaffold template — `scitex-dev skills init` clones this           |
| [14_general-skills-inheritance.md](14_general-skills-inheritance.md)       | How `general/` ships via scitex-dev so every install gets the rules|

## Related

- [03_interface/00_overview.md](../00_overview.md) — five-interface delegation chain
- [03_interface/01_python-api/](../01_python-api/), [03_interface/02_cli/](../02_cli/), [03_interface/03_mcp/](../03_mcp/) — sibling interfaces
- [01_ecosystem/06_dot_scitex_directory.md](../../01_ecosystem/06_dot_scitex_directory.md) — `~/.scitex/<pkg-short>/` layout for private skills
