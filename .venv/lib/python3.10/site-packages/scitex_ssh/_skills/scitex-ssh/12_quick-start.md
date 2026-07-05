---
description: |
  [TOPIC] Setup a tunnel (port 22 exposed via bastion)
  [DETAILS] Setup a tunnel (port 22 exposed via bastion) — see file body for details..
tags: [scitex-ssh-quick-start]
---

## Quick Start

```bash
# Setup a tunnel (port 22 exposed via bastion)
scitex-ssh tunnel setup --port 22 --bastion jump.example.com --secret-key ~/.ssh/id_rsa

# Check status
scitex-ssh tunnel check-status

# Check specific port
scitex-ssh tunnel check-status --port 22

# Remove tunnel
scitex-ssh tunnel remove --port 22
```

```python
from scitex_ssh import setup, status, remove

# Create tunnel
result = setup(port=22, bastion_server="jump.example.com", secret_key_path="~/.ssh/id_rsa")
# Returns: {"success": True, "stdout": "...", "stderr": "..."}

# Check all tunnels
result = status()

# Check specific port
result = status(port=22)

# Remove tunnel
result = remove(port=22)

# Check availability
from scitex_ssh import AVAILABLE, get_version
print(AVAILABLE)       # True/False
print(get_version())   # "0.x.y"
```
