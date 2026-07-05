---
description: |
  [TOPIC] Core
  [DETAILS] Core — see file body for details..
tags: [scitex-ssh-cli-commands]
---

## CLI Commands

```bash
# Core
scitex-ssh tunnel setup --port <port> --bastion <host> --secret-key <path>
scitex-ssh tunnel check-status [--port <port>]
scitex-ssh tunnel remove --port <port>

# MCP server
scitex-ssh mcp start [--transport <str>] [--host <host>] [--port <port>]
scitex-ssh mcp doctor
scitex-ssh mcp list-tools
scitex-ssh mcp show-installation

# Introspection
scitex-ssh list-python-apis [-v]
```
