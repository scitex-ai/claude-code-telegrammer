---
description: |
  [TOPIC] Todo
  [DETAILS] TODO — Skills Interface — see file body for details.
tags: [scitex-general-interface-skills-TODO]
---

# TODO — Skills Interface

## scitex-dev work

- [ ] Implement `scitex-dev skills init --package <name> [--dest <path>]` — clone scaffold from `src/scitex_dev/_skills_template/<pip-name>/`
- [ ] Create `~/proj/scitex-dev/src/scitex_dev/_skills_template/<pip-name>/` scaffold per [13_standard-template.md](13_standard-template.md)
- [ ] Refactor `scitex-dev/_cli_ecosystem.py` (now over 512-line limit) — extract all `audit-*` commands into a sibling `_cli_ecosystem_audits.py` (mechanical; tracked in `GITIGNORED/REFACTORING.md`)

## Documentation work

- [ ] Update [14_general-skills-inheritance.md](14_general-skills-inheritance.md) — design now describes the realised state (canonical home in scitex-dev, no sync needed) rather than the old "sync mirror" plan
- [ ] Convention sweep — bring outliers in line with [04_numbered-prefix-convention.md](04_numbered-prefix-convention.md)
  - `scitex-notification` — leaves are unprefixed; rename via `git mv` to `01_python-api.md`, `02_cli-reference.md`, `03_mcp-tools.md`, `10_backends.md`, `11_configuration.md`
  - `scitex-stats` — numbering jumps from `02` to `10–14`; close the gap or document the bucket meaning
  - `scitex-tunnel` — has no `_skills/` at all; scaffold via `scitex-dev skills init`
- [ ] Sweep downstream packages so every `scitex-*` repo's `_skills/<pip-name>/SKILL.md` references this directory (not the old `03_interface/04_skills.md` monolith)

## Done

- [x] 2026-04-30 — consolidate `03_interface/04_skills.md` (monolith) + `06_skills_*.md` (six leaves) into this directory; remove section 6 from parent SKILL.md
- [x] 2026-04-30 — content audit against `scitex-dev` source + 6 downstream packages; fixed `skills export` flag list, three legacy-path resolution chain, setuptools example (`scitex-cloud`), `scitex-dev quality audit-frontmatter` correct command path
- [x] 2026-04-30 — Tier-A 12-package pattern audit; converged on the standard-5 leaf set, SKILL.md template (`allowed-tools` + `primary_interface` + `interfaces`), and dropped under-adopted frontmatter extensions
- [x] 2026-04-30 — added [13_standard-template.md](13_standard-template.md) (scaffold reference) and [14_general-skills-inheritance.md](14_general-skills-inheritance.md)
- [x] 2026-04-30 — documented `scitex-dev skills collect` vs `export` semantics in [09_export-commands.md](09_export-commands.md)
- [x] 2026-04-30 — frontmatter cleanup sweep across 55 files in `general/`: stripped `invocation`, `context_tokens`, `context_tokens_total`, `canonical-location`, `see-also` per [05_frontmatter-metadata.md](05_frontmatter-metadata.md) §4
- [x] 2026-04-30 — implemented `scitex-dev ecosystem audit-skills` linter: 17 rules SK-101–SK-704; 17 smoke tests pass; rule catalog documented in [12_quality-checklist.md](12_quality-checklist.md) §9
- [x] 2026-04-30 — **migrated `general/` (94 files) + `scientific/` (2 files) from scitex-python to scitex-dev as canonical home**; deletions staged on scitex-python `develop`. Distribution: every scitex-* package already declares `scitex-dev` as a runtime dep, so `pip install scitex-io` (etc.) transitively pulls these rules
- [x] 2026-04-30 — fixed `_collect_skills_from_dir` recursion + `export_skills` to preserve nested rel_paths so `general/03_interface/04_skills/SKILL.md` survives the round-trip; smoke-tested with `scitex-dev skills collect /tmp/...` exporting 113 files across 3 namespaces
