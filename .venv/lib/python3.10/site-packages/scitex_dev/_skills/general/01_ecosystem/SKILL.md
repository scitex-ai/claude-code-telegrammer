---
description: |
  [TOPIC] Ecosystem Wide Rules
  [DETAILS] Cross-package conventions every `scitex-*` repo follows — the 3-layer cascade hierarchy and test scope, dependency hygiene + optional extras + version-pinning rules, the module-vs-standalone-package decision, the `SCITEX_<MODULE_NAME>_*` env-var prefix rule, the umbrella `scitex.<name>` thin-re-export bridge with lazy-import guard, the `<project>/.scitex/<pkg-short>/` + `~/.scitex/<pkg-short>/` local-state layout, AGPL-3.0-only + CLA policy, per-package linter plugins, package categories, the `project-type: research` auditor carve-outs, and the model-serving (scitex-genai) vs model-consumption (sac) HTTP-only boundary. Use when touching any `scitex-*` package or onboarding a research repo to ecosystem standards.
tags: [scitex-general-ecosystem-index]
---

# Ecosystem-wide Rules (SciTeX) — Index

Cross-package conventions every `scitex-*` repo follows. Audience: anyone
touching any `scitex-*` package. Read before the per-package tiers
([../SKILL.md](../SKILL.md)).

## Sections

1. [01_upstream-and-downstream.md](01_upstream-and-downstream.md) — 3-layer cascade, test scope, cascade pattern
2. [02_dependency-and-version-pinning.md](02_dependency-and-version-pinning.md) — Dependency hygiene, optional extras, version-pinning rules
3. [03_modules-and-standalone-packages.md](03_modules-and-standalone-packages.md) — Module vs standalone package boundaries
4. [04_environment-variables.md](04_environment-variables.md) — `SCITEX_<MODULE_NAME>_*` prefix rule; mandates per-package `NN_env-vars.md` leaf
5. [05_re-export.md](05_re-export.md) — Umbrella `scitex.<name>` thin-re-export pattern + lazy-import guard
6. [06_dot_scitex_directory.md](06_dot_scitex_directory.md) — `<project>/.scitex/<pkg-short>/` + `~/.scitex/<pkg-short>/` layout, precedence, `SCITEX_DIR`, `PathManager`
7. [07_license-and-cla.md](07_license-and-cla.md) — AGPL-3.0-only SPDX policy, CLA workflow template, `signatures/cla.json` shape, `pull_request_target` base-branch trap, bootstrap + audit recipes
8. [08_linter-plugins.md](08_linter-plugins.md) — Each package ships its own lint rules via the `scitex_dev.linter.plugins` entry point; `scitex-dev linter` aggregates; doc-block linting and ecosystem-wide `lint sweep`
9. [09_package-categories.md](09_package-categories.md) — Package category taxonomy
10. [10_research-project-type.md](10_research-project-type.md) — `project-type: research` — research repos are NOT pip packages; auditor SKIPS publish rules and KEEPS the universal ones
11. [11_model-serving-vs-consumption.md](11_model-serving-vs-consumption.md) — Model-serving (scitex-genai) vs model-consumption (sac via `ProviderSpec` `base_url`); contract is an HTTP endpoint, never a Python import — neither package imports the other
