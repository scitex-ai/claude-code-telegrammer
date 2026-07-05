---
description: |
  [TOPIC] Skills General Inheritance
  [DETAILS] How ecosystem-wide `general/` skills (this very directory's rules) reach every install — scitex-dev carries a synced mirror at `src/scitex_dev/_skills/general/`, parallel to its own `src/scitex_dev/_skills/scitex-dev/`. `scitex-dev skills export` ships both as separate namespaces under `~/.claude/skills/scitex/`. Source of truth stays in scitex-python; sync runs at scitex-dev release time.
tags: [scitex-general-interface-skills-general-skills-inheritance]
---

# General-Skills Inheritance

## The problem

`general/` (this directory and its siblings under `src/scitex/_skills/general/`) holds the ecosystem-wide rules every package author and every research-project agent should follow. But it physically lives in the `scitex` umbrella package only. A user who installs just `scitex-io` or just `figrecipe` gets that package's `_skills/<pip-name>/` — and **nothing from `general/`**. The rules never reach the agent.

## The solution

`scitex-dev` is the package that ships and runs `skills export` — every install that wants to populate `~/.claude/skills/scitex/` already has scitex-dev. So scitex-dev becomes the carrier of `general/`:

```
src/scitex_dev/_skills/
  scitex-dev/                   # scitex-dev's own skills (own contents, unchanged)
    SKILL.md
    01_quick-start.md
    ...
  general/                      # synced mirror of scitex-python's general/
    SKILL.md
    01_ecosystem/01_*.md
    ...
    03_interface/04_skills/
      SKILL.md
      01_overview.md
      ...
```

The two siblings stay fully separated:
- `scitex-dev/` — owned and edited inside scitex-dev's own repo
- `general/` — **synced** from scitex-python; never edited inside scitex-dev directly

## Source of truth

| Directory | Edit here | Synced to |
|---|---|---|
| `~/proj/scitex-python/src/scitex/_skills/general/` | ✅ canonical | mirror under scitex-dev |
| `~/proj/scitex-dev/src/scitex_dev/_skills/general/` | ❌ never (auto-overwritten on sync) | itself, then exported |
| `~/proj/scitex-dev/src/scitex_dev/_skills/scitex-dev/` | ✅ canonical | itself, then exported |

A pre-tool-use hook should refuse Edit/Write to the synced mirror, parallel to the existing hook for `~/.claude/skills/scitex/`.

## Sync workflow

```bash
# Inside scitex-dev repo, before a release bump:
scitex-dev ecosystem sync-general

# What it does:
#   rsync --delete ~/proj/scitex-python/src/scitex/_skills/general/ \
#         ~/proj/scitex-dev/src/scitex_dev/_skills/general/
#   git add src/scitex_dev/_skills/general/
#   git commit -m "chore: sync general/ from scitex-python @ <sha>"
```

Sync is **release-gated**, not on every commit — pinning to a specific scitex-python SHA at scitex-dev release time gives reproducibility. The commit message records the pinned SHA.

## Export

`scitex-dev skills export` walks `_skills/<*>/` and ships each top-level subdir as its own namespace:

```
~/.claude/skills/scitex/
  scitex-dev/         # from scitex-dev/_skills/scitex-dev/
    SKILL.md
    ...
  general/            # from scitex-dev/_skills/general/
    SKILL.md
    01_ecosystem_*.md
    ...
  scitex-io/          # from scitex-io/_skills/scitex-io/  (separate package)
    ...
```

A research-project agent now sees `general/` regardless of which scitex-* packages it installs — as long as scitex-dev is among them.

## Implementation tracking

The above describes the target. Concrete work to land it:

| Step | Location | Status |
|---|---|---|
| Create `src/scitex_dev/_skills/general/` (initial sync) | scitex-dev repo | TODO |
| `scitex-dev ecosystem sync-general` CLI command | scitex-dev repo | TODO |
| Pre-tool-use hook to block edits in the mirror | `~/.claude/hooks/pre-tool-use/` | TODO |
| Update `scitex-dev skills export` to handle multi-namespace `_skills/` layout | scitex-dev repo | partially done — verify |
| Update scitex-dev's release checklist to require sync-general before bump | scitex-dev `12_quality-checklist.md` | TODO |

See [TODO.md](TODO.md) for the actionable list.

## Cross-references

- [02_directory-layout.md](02_directory-layout.md) — `_skills/<namespace>/` layout the export tool resolves
- [09_export-commands.md](09_export-commands.md) — the export command this design extends
- [10_how-to-update.md](10_how-to-update.md) — edit workflow (only the canonical scitex-python copy)
