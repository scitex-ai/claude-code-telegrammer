---
description: |
  [TOPIC] Interface Mcp Overview
  [DETAILS] SciTeX MCP convention — overview, when to add a tool, fastmcp as canonical SDK, audience.
tags: [scitex-general-interface-mcp-overview]
---

# SciTeX MCP Convention — Overview

- Canonical MCP rules for every `scitex-*` package.
- Goal: an LLM agent that has the `scitex` MCP server attached can call any package's tools using a **predictable name shape**, with **arguments that mirror the CLI**, and **JSON output that mirrors the Python API**.

## When to add an MCP tool

Add a tool when **all** of the following are true:

1. The functionality is already a public Python API call.
2. There is already a CLI subcommand wrapping it.
3. An agent calling it from a fresh session would benefit (typical: read/list/show/get/search, structured mutations, long-running pipelines).

Do **not** add MCP tools for things that should stay user-only (interactive editors, irreversible deletes without confirm gates, secrets-handling).

## Canonical SDK

- **`fastmcp`** is the only SDK SciTeX packages use. Both 2.x and 3.x are supported via the [`safe_mount` shim](SKILL.md) in `scitex._mcp_tools._compat`.
- Each package owns a single `FastMCP` instance, exposed at `scitex_<pkg>._mcp_server.mcp` (or equivalent module path).

## Audience

- Package authors adding or maintaining MCP tools.
- Auditors verifying ecosystem-wide MCP consistency (`scitex-dev ecosystem audit-mcp-tools`, future).
- Anyone debugging why an MCP tool's signature drifted from its handler.

## Where to go next

- Server registration → [02_server-registration.md](02_server-registration.md)
- Tool naming → [03_tool-naming.md](03_tool-naming.md)
- Required subcommands → [04_required-subcommands.md](04_required-subcommands.md)
- Lessons & pitfalls → [08_lessons-and-pitfalls.md](09_lessons-and-pitfalls.md)
