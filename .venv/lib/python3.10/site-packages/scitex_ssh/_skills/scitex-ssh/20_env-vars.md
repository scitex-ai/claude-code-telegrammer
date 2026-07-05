---
description: |
  [TOPIC] Environment Variables
  [DETAILS] ## Environment Variables.
tags: [scitex-ssh-env-vars]
---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `SCITEX_SSH_BASTION_SERVER` | Default bastion server (if --bastion not provided) |
| `SCITEX_SSH_SECRET_KEY_PATH` | Default SSH key path (if --secret-key not provided) |

Set these in `~/.bashrc` / `~/.zshenv` or a project `.env` to avoid
passing the same bastion + key path on every invocation. Both the
Python API (`setup()`) and the MCP tools (`tunnel_setup`) fall back
to the env vars when their corresponding parameters are omitted.
