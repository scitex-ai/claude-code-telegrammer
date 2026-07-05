---
name: scitex-container
description: |
  [WHAT] Unified container management for Apptainer/Singularity + Docker — 14 MCP tools for the reproducible-science lifecycle.
  [WHEN] Use whenever the user asks to "build an Apptainer SIF", "rebuild Docker containers", "snapshot my environment", "rollback to a previous container", "check host container setup", "verify SIF integrity", "install Apptainer on this machine", "create a writable sandbox", "freeze my dependencies with system state", "deploy a container for SLURM/HPC", or mentions SIF, Apptainer, Singularity, Docker compose, Dockerfile, .
  [HOW] `pip install scitex-container` then `import scitex_container`; see leaf skills for details.
tags: [scitex-container]
allowed-tools: mcp__scitex__container_*, mcp__scitex__sandbox_*, mcp__scitex__docker_*, mcp__scitex__host_*
primary_interface: cli
interfaces:
  python: 2
  cli: 3
  mcp: 2
  skills: 2
  http: 0
---

# scitex-container Skills Index

> **Interfaces:** Python ⭐⭐ · CLI ⭐⭐⭐ (primary) · MCP ⭐⭐ · Skills ⭐⭐ · Hook — · HTTP —

## Installation & import (two equivalent paths)

The same module is reachable via two install paths. Both forms work at
runtime; which one a user has depends on their install choice.

```python
# Standalone — pip install scitex-container
import scitex_container
scitex_container.env_snapshot(...)

# Umbrella — pip install scitex
import scitex.container
scitex.container.env_snapshot(...)
```

`pip install scitex-container` alone does NOT expose the `scitex` namespace;
`import scitex.container` raises `ModuleNotFoundError`. To use the
`scitex.container` form, also `pip install scitex`.

See [../../general/02_interface-python-api.md] for the ecosystem-wide
rule and empirical verification table.

## Sub-skills

### Core
- [01_installation.md](01_installation.md) — pip install + runtime deps + smoke verify
- [02_quick-start.md](02_quick-start.md) — build a SIF + snapshot env (Apptainer default)
- [03_python-api.md](03_python-api.md) — top-level Python surface (re-exports + submodules)
- [04_cli-reference.md](04_cli-reference.md) — full `scitex-container` subcommand surface

### Workflows
- [11_mcp-tools.md](11_mcp-tools.md) — MCP tools for AI agents
- [12_quick-start.md](12_quick-start.md) — original quick-start (legacy)
- [13_python-api.md](13_python-api.md) — apptainer module reference
- [14_python-api-sandbox.md](14_python-api-sandbox.md) — sandbox management & versioning
- [15_python-api-builders.md](15_python-api-builders.md) — SLURM / exec command builders
- [16_python-api-docker-host.md](16_python-api-docker-host.md) — docker, host, top-level `env_snapshot`
- [17_cli-reference-detailed.md](17_cli-reference-detailed.md) — historical detailed CLI reference

### Standards
- [20_environment.md](20_environment.md) — Environment variables
