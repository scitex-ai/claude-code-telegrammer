---
description: |
  [TOPIC] Interfaces Overview
  [DETAILS] The five interfaces every SciTeX package must expose — Python API (primary), CLI (noun-verb), MCP (fastmcp), Skills (_skills/ directory), optional HTTP (FastAPI). Includes the delegation chain (Python API is canonical; CLI/MCP/HTTP are thin wrappers with no original logic) and cross-interface parity expectations. Use as the entry point when onboarding a new package or checking that all interfaces agree on a given feature.
tags: [scitex-general-interface-overview]
---

# Five Interfaces (Required per Package)

Every SciTeX package exposes up to five interfaces. No logic duplication — all delegate to the Python API (the single source of truth).

| # | Interface | Audience | Delegates to | Required |
|---|-----------|----------|--------------|----------|
| 1 | **Python API** | Scripts, notebooks | — (source of truth) | ✅ Required |
| 2 | **CLI** | Terminal, shell | Python API | Recommended when package has a user-facing surface; optional for pure library utilities |
| 3 | **MCP Server** | AI agents (actions) | CLI commands | Recommended when package has a user-facing surface; optional for pure library utilities |
| 4 | **Skills** | AI agents (discovery) | Static markdown | ✅ Required |
| 5 | **HTTP API** | Web clients | Python API | ⚪ Optional |

## Sub-skills

* [01_python-api/](01_python-api/) — Minimal API design, no logic duplication (split into per-section files; start at [SKILL.md](01_python-api/SKILL.md))
* [02_cli/](02_cli/) — Required sub-commands, flags, consistency rules (split into per-section files; start at [SKILL.md](02_cli/SKILL.md))
* [03_mcp/SKILL.md](03_mcp/SKILL.md) — fastmcp patterns, reproducibility, standard commands
* [04_skills/](04_skills/) — `_skills/` layout, SKILL.md format, registration, export, frontmatter (split into per-section files; start at [SKILL.md](04_skills/SKILL.md))
* [05_http-api/](05_http-api/) (split into per-section files; start at [SKILL.md](05_http-api/SKILL.md)) — Optional FastAPI, delegation rules
