---
description: |
  [TOPIC] Interface Cli Overview
  [DETAILS] SciTeX CLI convention — overview and scope. What's covered (every entry point in pyproject.toml [project.scripts]) vs what isn't (third-party CLIs).
tags: [scitex-general-interface-cli-overview]
---

# SciTeX CLI Convention — Overview

- Canonical CLI rules for every `scitex-*` package.
- Goal: one **unsurprising** CLI surface across the ecosystem — same flag semantics, exit codes, help format everywhere.
- Each repo keeps a short specialization skill (concrete nouns + exceptions) that back-links to this directory.

## Scope

- **In scope:** every entry point declared in a `scitex-*` repo's `pyproject.toml` `[project.scripts]` + shipped aliases.
- **Out of scope:** third-party CLIs invoked by scitex code (`git`, `ssh`, `docker`, `slurm`, `uv`) — keep their upstream surface.

## Where to go next

- Subcommand structure → [02_subcommand-structure-noun-verb.md](02_subcommand-structure-noun-verb.md)
- Single-token exceptions → [04_exceptions.md](04_exceptions.md)
- Vocabulary catalog → [06_noun-verb-catalog.md](06_noun-verb-catalog.md)
- Required flags → [08_universal-flags.md](08_universal-flags.md)
- Audit checklist → [15_audit-checklist.md](15_audit-checklist.md)
