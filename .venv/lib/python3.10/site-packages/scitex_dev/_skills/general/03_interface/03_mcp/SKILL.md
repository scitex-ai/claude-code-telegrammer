---
description: |
  [TOPIC] Interface Mcp
  [DETAILS] Canonical MCP (Model Context Protocol) server convention for every SciTeX package — single FastMCP instance per package, `<pkg>_<verb>_<noun>` tool naming, mount-pattern delegation from the scitex umbrella, required subcommands (`mcp start | doctor | list-tools | show-installation`), `list-tools` `-v|-vv|-vvv` ladder, skills integration, Python-API parity. Embeds lessons from the 2026-04 dev.py refactor.
tags: [scitex-general-interface-mcp-index]
---

# SciTeX MCP Convention (Canonical) — Index

Canonical MCP rules for every `scitex-*` package. Split into focused files; load only the section you need.

## Open TODOs

- [TODO.md](TODO.md) — open items, future tools (`audit-mcp-tools`), package sweeps.

## Sections

| File                                                                     | Topic                                                                                  |
|--------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| [01_overview.md](01_overview.md)                                         | What MCP is for in SciTeX, fastmcp as canonical SDK                                    |
| [02_server-registration.md](02_server-registration.md)                   | §1 — single `FastMCP` per package, mount pattern from the umbrella, conventions A/B    |
| [03_tool-naming.md](03_tool-naming.md)                                   | §2 — `<pkg>_<verb>_<noun>` rule, examples, parity with CLI                             |
| [04_required-subcommands.md](04_required-subcommands.md)                 | §3 — `mcp start | doctor | list-tools | show-installation` on every package CLI       |
| [05_list-tools-ladder.md](05_list-tools-ladder.md)                       | §4 — `-v|-vv|-vvv` + `--json` verbosity ladder for `mcp list-tools`                    |
| [06_skills-integration.md](06_skills-integration.md)                     | §5 — `<pkg>_skills_list` / `<pkg>_skills_get` standard pair                            |
| [07_python-api-parity.md](07_python-api-parity.md)                       | §6 — same logical name + args + JSON shape                                             |
| [08_audit-mcp-tools.md](08_audit-mcp-tools.md)                                       | §7 — `scitex-dev ecosystem audit-mcp-tools` linter (parallels `audit-cli`)                   |
| [09_lessons-and-pitfalls.md](09_lessons-and-pitfalls.md)                 | §8 — concrete lessons from the 2026-04 refactor (mount drift, process restart, …)     |
| [10_audit-checklist.md](10_audit-checklist.md)                           | §9 — manual audit checklist                                                           |

## Related

- [03_interface/02_cli/](../02_cli/) — CLI convention (mirror discipline).
- [03_interface/01_python-api/SKILL.md](SKILL.md) — Python API surface that MCP wraps.
