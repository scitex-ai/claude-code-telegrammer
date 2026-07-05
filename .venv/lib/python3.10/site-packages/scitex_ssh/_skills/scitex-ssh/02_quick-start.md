---
description: |
  [TOPIC] scitex-ssh Quick Start
  [DETAILS] Smallest example — set up a reverse SSH tunnel via the CLI, then check status.
tags: [scitex-ssh-quick-start]
---

# Quick Start

## CLI: install a reverse tunnel

```bash
scitex-ssh tunnel setup \
    --port 22 \
    --bastion jump.example.com \
    --secret-key ~/.ssh/id_rsa
```

Installs an `autossh`-backed systemd unit on the local host that
maintains a reverse tunnel from `jump.example.com:<port>` back to this
machine, surviving network drops and dynamic IPs.

```bash
scitex-ssh tunnel check-status          # list all tunnels
scitex-ssh tunnel check-status --port 22    # status of one tunnel
scitex-ssh tunnel remove --port 22      # tear down + remove unit
```

## Python equivalent

```python
from scitex_ssh import setup, status, remove

setup(port=22, bastion_server="jump.example.com",
      secret_key_path="~/.ssh/id_rsa")
status(port=22)
remove(port=22)
```

Each call returns a dict: `{"success": bool, "stdout": ..., "stderr": ...}`.

## One-shot SSH primitives

```python
from scitex_ssh import exec_remote, copy_to, copy_from, attach

exec_remote("user@host", "uname -a")
copy_to("user@host", "local.txt", "/tmp/")
copy_from("user@host", "/tmp/log.txt", "./")
attach("user@host")              # interactive shell
```

All primitives are gated by the host allowlist
(`~/.scitex/ssh/config.yaml`); unlisted hosts raise
`PolicyError`.
