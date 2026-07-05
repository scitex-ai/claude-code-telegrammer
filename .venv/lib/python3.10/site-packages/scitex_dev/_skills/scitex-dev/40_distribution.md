---
description: |
  [TOPIC] Skill distribution and update mechanics
  [DETAILS] How scitex-dev's skill tree is shipped, refreshed in `~/.claude/skills/scitex/`, and how private per-machine skills are symlinked. Source of truth = the in-package `_skills/` directory; the user-cache is a refreshable copy.
tags: [scitex-dev-distribution]
---

# Skill distribution and update

These skills are distributed inside the `scitex-dev` wheel under
`scitex_dev/_skills/scitex-dev/` — that's the **single source of truth**.
Local edits at `~/.claude/skills/scitex/` may be overwritten on update.

## Refresh the user cache

```bash
pip install --upgrade scitex-dev
scitex-dev skills export          # overwrite all (+ symlink private skills)
scitex-dev skills update          # preserve local changes
scitex-dev skills upgrade         # clean replacement
```

## Private skills (per-machine)

Private skills are symlinked into the export destination automatically:

```
~/.scitex/<suffix>/skills/<package>-private/
  → ~/.claude/skills/scitex/<package>-private/
```

Where `<suffix>` is the package name minus the `scitex-` prefix. Private
skills are never copied or shipped — the symlink keeps edits live.

## Drift detection

`scitex-dev skills export` stamps each cached leaf's frontmatter with the
exporting package version (`version: <importlib.metadata.version()>`).
On `skills get` / `skills list`, the framework compares the cached
version to the currently installed version and warns if drift is
detected (cached < installed). See the audit rule `SK-105` (forbids
`MANIFEST.md` — this leaf replaces it) and the version-stamping
behaviour documented in `13_versions.md`.
</content>
</invoke>