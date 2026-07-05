---
description: |
  [TOPIC] Interfaces Overview And Sub Interfaces
  [DETAILS] The five interfaces every SciTeX package must expose — Python API (primary, source of truth), CLI (noun-verb), MCP (fastmcp), Skills (`_skills/` directory), optional HTTP (FastAPI) — plus the delegation chain (CLI/MCP/HTTP are thin wrappers with no original logic) and cross-interface parity expectations. This index lifts the interfaces overview and points at the five per-interface sub-directories, each with its own `SKILL.md`. Use as the entry point when onboarding a new package or checking that all interfaces agree on a feature.
tags: [scitex-general-interface-index]
---

# Five Interfaces (Required per Package) — Index

Every SciTeX package exposes up to five interfaces. No logic duplication —
all delegate to the Python API (the single source of truth). Full overview
in [00_overview.md](00_overview.md).

| # | Interface | Audience | Delegates to | Required |
|---|-----------|----------|--------------|----------|
| 1 | **Python API** | Scripts, notebooks | — (source of truth) | ✅ Required |
| 2 | **CLI** | Terminal, shell | Python API | Recommended when user-facing; optional for pure libraries |
| 3 | **MCP Server** | AI agents (actions) | CLI commands | Recommended when user-facing; optional for pure libraries |
| 4 | **Skills** | AI agents (discovery) | Static markdown | ✅ Required |
| 5 | **HTTP API** | Web clients | Python API | ⚪ Optional |

## Sections

- [00_overview.md](00_overview.md) — Five interfaces: overview and delegation chain
- [01_python-api/](01_python-api/) — Minimal API, `__all__`, lazy imports, NumPy docstrings, version strategy (start at [SKILL.md](01_python-api/SKILL.md))
- [02_cli/](02_cli/) — Required sub-commands, flags, noun-verb convention, AI-friendly rules (start at [SKILL.md](02_cli/SKILL.md))
- [03_mcp/](03_mcp/) — fastmcp, tool naming, reproducibility, standard commands (start at [SKILL.md](03_mcp/SKILL.md))
- [04_skills/](04_skills/) — `_skills/` layout, SKILL.md format, registration, export, frontmatter, public-vs-private (start at [SKILL.md](04_skills/SKILL.md))
- [05_http-api/](05_http-api/) — Optional FastAPI delegation (start at [SKILL.md](05_http-api/SKILL.md))
