---
description: |
  [TOPIC] scitex-ssh CLI Reference
  [DETAILS] Top-level subcommands of `scitex-ssh` — exec, copy, attach, tunnel (setup/status/remove), mcp, list-python-apis.
tags: [scitex-ssh-cli-reference]
---

# CLI Reference

`scitex-ssh` is the entry point installed by `pip install scitex-ssh`.

```text
scitex-ssh [OPTIONS] COMMAND [ARGS]...
```

## Top-level options

| Flag                 | Purpose                                              |
|----------------------|------------------------------------------------------|
| `-V / --version`     | Show version and exit                                |
| `--help-recursive`   | Show help for the root and every subcommand          |
| `--json`             | Emit structured JSON output                          |
| `-h / --help`        | Show help                                            |

Config precedence (SciTeX chain):

```
config.yaml → $SCITEX_SSH_CONFIG → ~/.scitex/ssh/config.yaml → defaults
```

## SSH primitives

| Command  | Purpose                                              |
|----------|------------------------------------------------------|
| `exec`   | Run a command on HOST via ssh                        |
| `copy`   | Copy files between local and `HOST:PATH`             |
| `attach` | Open an interactive `ssh -t` session to HOST         |

```bash
scitex-ssh exec user@host -- uname -a
scitex-ssh copy ./local.txt user@host:/tmp/
scitex-ssh attach user@host
```

## Tunnel management

| Command                 | Purpose                                              |
|-------------------------|------------------------------------------------------|
| `tunnel setup`          | Install autossh systemd unit (reverse tunnel)        |
| `tunnel check-status`   | Show one or all installed tunnels                    |
| `tunnel remove`         | Stop + uninstall a tunnel by port                    |

Backward-compat shortcuts at the top level (`scitex-ssh setup-tunnel /
scitex-ssh show-status / scitex-ssh remove-tunnel`) are still accepted
but deprecated.

```bash
scitex-ssh tunnel setup --port 22 --bastion jump.example.com \
    --secret-key ~/.ssh/id_rsa
scitex-ssh tunnel status
scitex-ssh tunnel status --port 22
scitex-ssh tunnel remove --port 22
```

## Integration

| Command            | Purpose                                              |
|--------------------|------------------------------------------------------|
| `mcp`              | MCP server management (start / stop / status)        |
| `list-python-apis` | Print the public Python API surface                  |

## Allowlist gating

All commands consult `~/.scitex/ssh/allowed_hosts.yaml`. Unlisted hosts
fail fast with a `PolicyError`. See `03_python-api.md` for the YAML
shape.

## Examples

```bash
scitex-ssh --json tunnel check-status         # machine-readable
scitex-ssh --help-recursive | head -60        # full surface dump
```

See `02_quick-start.md` for the typical end-to-end flow.
