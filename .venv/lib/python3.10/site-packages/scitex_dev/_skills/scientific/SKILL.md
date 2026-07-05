---
name: scientific
description: |
  [WHAT] Scientific-methodology skills for the SciTeX ecosystem — publication-quality figures, statistics, experiment reproducibility. Distinct from `general/` (which covers package engineering) and per-package skills (which cover package-specific APIs). Load when authoring analysis scripts, preparing figures for manuscripts, or checking scientific rigour of ecosystem output.
  [WHEN] Authoring analysis scripts, preparing figures or PDF reports for manuscripts, or auditing scientific outputs of any ecosystem package.
  [HOW] Read SKILL.md as the index, then drill into the numbered sub-skill leaves (`01_figures_*`, `02_research-project_*`, `03_reporting_*`) for the relevant topic.
tags: [scitex-scientific]
user-invocable: false
primary_interface: mixed
interfaces:
  python: 0-3
  cli: 0-3
  mcp: 0-3
  skills: 3
  http: 0
---

# SciTeX Scientific Standards

`pip install scitex` — scientific-methodology conventions shared across every ecosystem package that produces research artefacts.

These complement (never duplicate) the engineering rules in [../general/SKILL.md](../general/SKILL.md). General covers *how a package is built*; scientific covers *how the research outputs should look*.

## Sub-skills

### 0. Planning
- [00_planning_01_hypotheses-agreement.md](00_planning_01_hypotheses-agreement.md) — Numbered, falsifiable hypotheses (H1/H2/...) with metric + prediction + baseline + falsification. Required **before** writing any experiment script. Research-project counterpart of the architecture agreement for pip packages.
- [00_planning_02_paper-structure.md](00_planning_02_paper-structure.md) — How to design and compact a manuscript: one-claim-one-figure-one-Result spine, lead with dataset+experimental-design Result, explicit float manifest over implicit glob, write Introduction & Discussion last, simplify redundant designs, flag provisional storyless results, panel-level figure sketches bound to build scripts.

### 1. Figures
- [01_figures_01_standards.md](01_figures_01_standards.md) — Universal scientific-figure standards: comparison rules (shared color scale, aligned axes), multi-panel layout, color maps, PDF report layout. Pairs with `figrecipe/21_scientific-figure-patterns.md` for matplotlib code.
- [01_figures_02_provenance-and-verification.md](01_figures_02_provenance-and-verification.md) — A figure is a generative, verifiable artefact: figrecipe (recipe YAML + DATA + media, WHAT vs HOW), paper consumes media via symlink, every figure a Clew claim with a hash-verified Source->Figure DAG; the verification-boundary concept (expensive upstream steps as hashed Source leaves) and the rule that Clew-unverified means *unmachine-checkable, not wrong*.
- [01_figures_03_no-synthetic-data-policy.md](01_figures_03_no-synthetic-data-policy.md) — Ecosystem policy: publication / paper / representative figures must use real data; fail loud when absent. Canonical home (figrecipe `23_*` cross-links).

### 2. Research project — how a research project *consumes* SciTeX
Project structure split into one leaf per top-level directory:
- [02_research-project_01_project-structure-root.md](02_research-project_01_project-structure-root.md) — Repo-root rules, allowed files, forbidden top-level dirs, `./docs/`, hidden dirs (`.dev`, `.old`, `./.scitex/<pkg-short>/`)
- [02_research-project_02_project-structure-scripts.md](02_research-project_02_project-structure-scripts.md) — `./scripts/` as the primary code location, `@stx.session` entry-point pattern, numbered analysis pipelines
- [02_research-project_03_project-structure-config-and-data.md](02_research-project_03_project-structure-config-and-data.md) — `./config/` YAML tree, `./data/` inputs+intermediate, project-scope `./.scitex/<pkg-short>/`, output discipline
- [02_research-project_04_project-structure-makefile.md](02_research-project_04_project-structure-makefile.md) — `./scripts/makefile/` dispatcher + research-specific targets (run-pipeline / repro / eval)
- [02_research-project_05_project-structure-examples.md](02_research-project_05_project-structure-examples.md) — Numbered examples + `_out/` artefacts; how research-project examples differ from package examples
- [02_research-project_06_project-structure-tests.md](02_research-project_06_project-structure-tests.md) — `tests/scripts/` mandatory parent, allowed subdirs, public/private mirroring, `audit-project` rules
- [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md) — `@stx.session` and the `CONFIG` object (`SDIR_OUT`, `SDIR_RUN`, YAML deep-merge, CLI/env overrides). Use when adding parameters to a script, debugging config resolution, or auditing an experiment for reproducibility.
- [02_research-project_08_cohort-datasets.md](02_research-project_08_cohort-datasets.md) — Multi-dataset projects: uniform `data/<cohort>/{capsules,src}/` tree, mirrored `scripts/cohorts/<cohort>/dataset/` and `tests/scripts/cohorts/<cohort>/dataset/`, generic filenames + cohort-in-path, `shared/` orchestrator pattern.
- [02_research-project_09_id-readability-and-data-immutability.md](02_research-project_09_id-readability-and-data-immutability.md) — UUID/random upstream IDs → readable ordinal symlinks (provenance preserved in target name); raw data stays compressed in `src/capsules/`; extractions in mirrored `src/capsules_extracted/`; strategies for very large datasets.
- [02_research-project_10_naming-and-numbering.md](02_research-project_10_naming-and-numbering.md) — Three rules: zero-fill all numbering to max-ID width (lex-sort = numeric-sort); mirror naming across `scripts/` / `tests/` / `data/`; cohort/group context in the path, not the filename.

### 3. Reporting
- [03_reporting_01_pdf-reports.md](03_reporting_01_pdf-reports.md) — Recurring scientific PDF analysis reports — timestamped filenames, mandatory section structure, navigable bookmarks (`fpdf2` / `pikepdf`), aspect-preserving figure embedding, size management for email (<10 MB, DPI/ghostscript/split), and delivery tracking via email + issue-tracker comment.

### 4. Clew adoption — translating any project into a Clew-verifiable form
- [04_clew_01_dag-as-map-and-evidence.md](04_clew_01_dag-as-map-and-evidence.md) — Conceptual: same SHA-256 DAG in two modes — *map* (live, read-write, used during build/exploration by agents and authors) and *evidence* (post-hoc, read-only, used by reviewers). Read first when adopting Clew on any project.
- [04_clew_02_translation-playbook.md](04_clew_02_translation-playbook.md) — Universal agent prompt: 5 inputs (CAPSULE_ID, CAPSULE_PATH, QUESTIONS_PATH, ORACLE_PATH, WORKDIR), tier dispatch (easy / notebook / medium / hard), agent-vs-verifier split, scoring schema, DONE signal. Loadable as `spec.skills.required` on any sac agent yaml.
- [04_clew_03_translation-template.md](04_clew_03_translation-template.md) — Concrete project skeleton: pre-flight checklist, agent-vs-verifier directory layout, clean-DAG Makefile pattern, six-step procedure (inputs → pre-flight → scaffold → implement+iterate → validity gate → DONE).
- [04_clew_04_translation-notebook-delta.md](04_clew_04_translation-notebook-delta.md) — Notebook-cohort delta: two-stage flow (`scitex-notebook convert` → flat `.py` → standard SciTeX translation), kernel/determinism/cached-API rules, per-`eval_mode` scoring (range / str / llm).

### 5. Private skills for consumer projects (research repos, paper repos, internal apps)
- [05_private-skills_01_consumer-project.md](05_private-skills_01_consumer-project.md) — 4-layer skill stack (public-package, fleet-private, consumer-project private, gitignored notes), where each lives, decision tree for "where does this new agent-facing doc go?", lift-up rule (transient → reusable → public), concrete `paper-scitex-clew` layout. Pairs with `../general/03_interface/04_skills/06_public-vs-private.md` (which is for *package* authors); this leaf is for *consumer* projects.

### 6. Scitexification — translating existing code into SciTeX form
- [06_scitexification/SKILL.md](06_scitexification/SKILL.md) — Single source of truth for the *translation act* itself, package-agnostic. 5-stage arc (io, session/config, plt, repro+clew, naming) each holding independently. Load BEFORE picking the per-chapter topic. Chapters drill into specific stage patterns; per-package APIs delegate to the per-pkg SKILL.md (`scitex-io`, `figrecipe`, `scitex-clew`, ...). Clew-specific specialization lives in `04_clew_*`; this skill is the general form.
  - [06_scitexification/00_playbook.md](06_scitexification/00_playbook.md) — Canonical universal playbook. Coins the vocabulary (`scitexify`/`scitexification`/`scitexified`), fixes the universal contract (inputs, pre-flight, phase dispatch, done condition, forbidden), and frames the **honest source-grounding** principle — "attempt every claim, ground where possible, include the ungroundable with `null` + reason, NEVER silently omit" — as a general scientific-integrity norm, independent of any evaluator. Read first when scitexifying any artefact.
