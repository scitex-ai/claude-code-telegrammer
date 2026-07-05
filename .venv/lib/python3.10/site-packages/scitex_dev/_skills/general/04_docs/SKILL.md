---
description: |
  [TOPIC] Documentation Surfaces
  [DETAILS] How a `scitex-*` package becomes understandable — the standard README template with required sections, badges, and footer; Sphinx docs (`conf.py`, troubleshooting); Read the Docs onboarding (`.readthedocs.yaml`, build config); env-vars-and-state documentation; and robust docs-CI that keeps `sphinx-build -W` strict while defending the four benign failure modes (docstring reST noise, GH006 commit-back, missing-peer autodoc, math). Use when writing or auditing a package's README, Sphinx tree, or docs CI.
tags: [scitex-general-docs-index]
---

# Documentation (SciTeX) — Index

How does *this* package become understandable? Audience: package authors.
Builds on the package layout ([../02_package/SKILL.md](../02_package/SKILL.md)).

## Sections

1. [01_readme.md](01_readme.md) — Standard README template, sections, badges, footer
2. [01_readme_template.md](01_readme_template.md) — Copy-paste README skeleton
3. [02_sphinx.md](02_sphinx.md) — Sphinx docs, conf.py, troubleshooting
4. [03_env-vars-and-state.md](03_env-vars-and-state.md) — Documenting env vars + local state surfaces
5. [03_rtd.md](03_rtd.md) — Read the Docs onboarding, `.readthedocs.yaml`, build config
6. [04_robust-ci.md](04_robust-ci.md) — Robust docs-CI: keep `sphinx-build -W` strict while defending the 4 benign failure modes
