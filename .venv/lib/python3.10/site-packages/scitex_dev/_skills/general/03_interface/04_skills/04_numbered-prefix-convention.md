---
description: |
  [TOPIC] Skills Numbered Prefix Convention
  [DETAILS] Two-level `NN_<category>_NN_<topic>.md` numbering rule for `_skills/` leaves — `01-09` interfaces (quick start, Python API, CLI, MCP), `10-19` features, `20-29` meta. Gives a fresh agent an implicit reading order so SKILL.md links are sortable. Use whenever a package's skill count exceeds 3-4 leaves.
tags: [scitex-general-interface-skills-numbered-prefix-convention]
---

# Numbered-Prefix File Convention

Once a package has more than 3-4 skill files, use **numbered prefixes** so scitex-scholar / scitex-io / scitex-template all share the same browsing layout.

## Buckets

| Range | Purpose | Examples |
|---|---|---|
| `01-09` | Onboarding + interfaces — install, quick start, Python API, CLI, MCP, HTTP | `01_installation.md`, `02_quick-start.md`, `03_python-api.md`, `04_cli-reference.md`, `05_mcp-tools.md`, `06_http-api.md` |
| `10-19` | Workflows — one focused capability per file | `10_save-and-load.md`, `11_centralized-config.md`, `12_supported-formats.md` |
| `20-29` | Meta — env vars, config, logging | `20_env-vars.md`, `21_config.md`, `22_logging.md` |
| `30-39` | Architecture / internals (optional) | `30_architecture.md` |
| `40-49` | Lessons / playground (optional) | `40_lessons.md` |

## Reasoning

A fresh agent landing on the package can read 01-04 to understand the surface in under 5 minutes, then drill into a 10-series file only when relevant. Without numbering the index has no implicit reading order; with numbering the SKILL.md links are sortable.

## Standard-7 leaf set

Every package should ship these seven leaves (mandatory or conditional on the package's interfaces). The auditor enforces presence via SK-105–SK-111 — see [12_quality-checklist.md](12_quality-checklist.md).

| Leaf | Required when |
|---|---|
| `01_installation.md` | always |
| `02_quick-start.md` | always |
| `03_python-api.md` | package exposes Python API |
| `04_cli-reference.md` | package ships CLI |
| `05_mcp-tools.md` | package registers MCP tools |
| `06_http-api.md` | package ships HTTP routes |
| `20_env-vars.md` | package reads any `SCITEX_<MODULE>_*` env var |

Beyond these seven, leaves are package-specific (workflows in 10–19, deeper meta in 20–29, architecture in 30+, lessons in 40+). The scaffold in [13_standard-template.md](13_standard-template.md) creates the standard set as the starting point.

## Rules

- 2-digit zero-padded: `01_`, `02_`, …, `99_`. No gaps within a group.
- Prefixes express **logical** order, not alphabetical.
- `SKILL.md` itself has **no** numeric prefix.
- Filenames are **kebab-case** after the prefix: `01_ecosystem/01_upstream-and-downstream.md`.
- **NEVER** rename a prefixed file by hand; use `git mv` so history is preserved.

## Optional second-level grouping (`general/` mirror)

For very large skill trees that need an extra level of grouping, use the two-level form `NN_<category>_NN_<topic>.md` — e.g. `01_ecosystem/04_environment-variables.md`. The first `NN` is the section, the trailing `NN_<topic>` orders leaves within the section. `general/` itself uses this form.

## Cross-references

- [03_skill-md-as-index.md](03_skill-md-as-index.md) — index links should be in prefix order
- [12_quality-checklist.md](12_quality-checklist.md) — naming/ordering checks at release-gate
