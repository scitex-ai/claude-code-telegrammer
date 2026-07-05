---
description: |
  [TOPIC] Mcp Tools for Ai Agents
  [DETAILS] ## MCP Tools (for AI agents).
tags: [scitex-ssh-mcp-tools-for-ai-agents]
---

## MCP Tools (for AI agents)

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `tunnel_setup` | `port`, `bastion_server`, `secret_key_path` | Create persistent SSH tunnel |
| `tunnel_status` | `port` (optional) | Check tunnel status |
| `tunnel_remove` | `port` | Remove tunnel |

Defaults for `bastion_server` and `secret_key_path` come from
`SCITEX_SSH_BASTION_SERVER` / `SCITEX_SSH_SECRET_KEY_PATH` env vars
when the parameters are omitted.
