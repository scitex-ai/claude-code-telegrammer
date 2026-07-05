---
description: |
  [TOPIC] scitex-ssh Python API
  [DETAILS] Top-level public callables — primitives (exec_remote/copy_to/copy_from/attach) + tunnel mgmt (setup/status/remove) + PolicyError + SSHResult.
tags: [scitex-ssh-python-api]
---

# Python API

Public surface re-exported from `scitex_ssh`.

## Public symbols

| Name                  | Kind     | Purpose                                              |
|-----------------------|----------|------------------------------------------------------|
| `__version__`         | str      | Installed package version                            |
| `get_version()`       | function | Same as `__version__` (callable)                     |
| `AVAILABLE`           | bool     | Whether tunnel deps are installed                    |
| `PolicyError`         | exc      | Raised when target host not in SSH allowlist         |
| `SSHResult`           | class    | Return type of primitives — `returncode/stdout/stderr` |
| `exec_remote(host, cmd)` | function | Run a command on a remote host                    |
| `copy_to(host, src, dst)`   | function | scp local → remote                              |
| `copy_from(host, src, dst)` | function | scp remote → local                              |
| `attach(host)`        | function | Interactive SSH session                              |
| `setup(port, ...)`    | function | Install autossh systemd unit (reverse tunnel)        |
| `status(port=None)`   | function | List one or all installed tunnels                    |
| `remove(port)`        | function | Stop + uninstall a tunnel                            |

## Primitive return type

```python
from scitex_ssh import exec_remote, SSHResult

result: SSHResult = exec_remote("user@host", "ls /tmp")
result.returncode      # int
result.stdout          # str
result.stderr          # str
```

## Tunnel return shape

```python
from scitex_ssh import setup
result = setup(port=22, bastion_server="jump.example.com",
               secret_key_path="~/.ssh/id_rsa")
# {"success": bool, "stdout": "...", "stderr": "..."}
```

## Allowlist

All primitives consult `~/.scitex/ssh/config.yaml`. Unlisted
hosts raise `PolicyError` before any SSH call is dispatched. Append
hosts manually:

```yaml
# ~/.scitex/ssh/config.yaml
hosts:
  - host.example.com
  - jump.example.com
```

## Not exposed (private)

- `_allowlist.is_allowed`, `_allowlist.require` — internal gate helpers.
- Systemd unit templates under `scitex_ssh/scripts/` — opaque, may
  change between releases.
