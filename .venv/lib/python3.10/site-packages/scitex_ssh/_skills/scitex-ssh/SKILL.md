---
name: scitex-ssh
description: |
  [WHAT] Persistent, auto-reconnecting SSH reverse tunnels for NAT traversal — installs an `autossh` systemd unit on the local host so a bastion/relay server can SSH back in even through firewalls and dynamic IPs.
  [WHEN] Use whenever the user asks to "set up a reverse SSH tunnel", "keep SSH alive through NAT", "access a lab machine from outside", "tunnel through a bastion", "autossh systemd service", "check tunnel status", "remove a tunnel", "expose this machine via a jump host", or mentions bastion server, NAT traversal, autossh, reverse SSH, HPC login node.
  [HOW] `pip install scitex-ssh` then `import scitex_ssh`; see leaf skills for details.
tags: [scitex-ssh]
allowed-tools: mcp__scitex__tunnel_*
primary_interface: cli
interfaces:
  python: 1
  cli: 3
  mcp: 2
  skills: 2
  http: 0
---

# SSH Tunnels with scitex-ssh

> **Interfaces:** Python ⭐ · CLI ⭐⭐⭐ (primary) · MCP ⭐⭐ · Skills ⭐⭐ · Hook — · HTTP —

## Installation & import (two equivalent paths)

The same module is reachable via two install paths. Both forms work at
runtime; which one a user has depends on their install choice.

```python
# Standalone — pip install scitex-ssh
import scitex_ssh

# Umbrella — pip install scitex
import scitex.tunnel
```

`pip install scitex-ssh` alone does NOT expose the `scitex` namespace;
`import scitex.tunnel` raises `ModuleNotFoundError`. To use the
`scitex.tunnel` form, also `pip install scitex`.

See [../../general/02_interface-python-api.md] for the ecosystem-wide
rule and empirical verification table.

## Sub-skills

### Core
- [01_installation.md](01_installation.md) — pip install + system deps + smoke verify
- [02_quick-start.md](02_quick-start.md) — set up reverse tunnel (CLI + Python)
- [03_python-api.md](03_python-api.md) — primitives + tunnel mgmt reference
- [04_cli-reference.md](04_cli-reference.md) — full `scitex-ssh` subcommand surface

### Workflows
- [10_cli-commands.md](10_cli-commands.md) — CLI commands (legacy)
- [11_mcp-tools-for-ai-agents.md](11_mcp-tools-for-ai-agents.md) — MCP tools for AI agents
- [12_quick-start.md](12_quick-start.md) — original quick-start (legacy)
- [13_python-api.md](13_python-api.md) — original Python API page (legacy)

### Standards
- [20_env-vars.md](20_env-vars.md) — Environment variables
