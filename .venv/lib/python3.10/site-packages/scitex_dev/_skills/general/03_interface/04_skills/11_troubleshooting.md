---
description: |
  [TOPIC] Skills Troubleshooting
  [DETAILS] Common `scitex-dev skills` failure modes and fixes — missing entry points, flat `_skills/` layout the exporter cannot discover, leaves lacking frontmatter or empty descriptions. Use as the first stop when `skills export` says "no skills found" or files are skipped.
tags: [scitex-general-interface-skills-troubleshooting]
---

# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `scitex-dev skills export` says "No skills found" | missing `scitex_dev.skills` / `scitex_dev.docs` entry point | add to `pyproject.toml` and `pip install --force-reinstall` (see [07_registration.md](07_registration.md)) |
| Skills land at `_skills/*.md` (flat) but exporter can't find them | `_find_skills_dir` expects `_skills/<pip-name>/` subdir | move under `src/<pkg>/_skills/<pip-name>/` (see [02_directory-layout.md](02_directory-layout.md)) |
| Some files exported, others skipped | files lack frontmatter or have empty `description` | give every leaf a YAML frontmatter block (see [05_frontmatter-metadata.md](05_frontmatter-metadata.md)) |
| Edits to `~/.claude/skills/scitex/...` are blocked | pre-tool-use hook protects export copies | edit `src/<pkg>/_skills/<pip-name>/...` instead, then re-export (see [10_how-to-update.md](10_how-to-update.md)) |
| Editable-install edits don't appear in agent session | reading wheel copy, not source | reinstall with `pip install -e . --force-reinstall`; verify symlink under `~/.claude/skills/scitex/<pkg>/` |
| `pip install scitex-<pkg>` from PyPI ships no skills | `_skills/` not in package data | add `[tool.setuptools.package-data]` block (see [07_registration.md](07_registration.md)) |
| Hatch build error: duplicate `_skills` files | redundant `force-include` block | remove `[tool.hatch.build.targets.wheel.force-include]` for `_skills/` |
