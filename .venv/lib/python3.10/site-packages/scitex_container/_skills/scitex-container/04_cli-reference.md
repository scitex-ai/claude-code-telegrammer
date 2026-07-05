---
description: |
  [TOPIC] scitex-container CLI Reference
  [DETAILS] Top-level subcommands of `scitex-container` — apptainer, docker, host, sandbox, save-env-snapshot, show-status, mcp.
tags: [scitex-container-cli-reference]
---

# CLI Reference

`scitex-container` is the entry point installed by
`pip install scitex-container`.

```text
scitex-container [OPTIONS] COMMAND [ARGS]...
```

## Top-level options

| Flag                | Purpose                                              |
|---------------------|------------------------------------------------------|
| `-V / --version`    | Show the version and exit                            |
| `--help-recursive`  | Show help for all commands recursively               |
| `--json`            | Emit machine-readable JSON output (where supported)  |
| `-h / --help`       | Show this message and exit                           |

## Configuration precedence

```
CLI flags  →  ./config.yaml  →  $SCITEX_CONTAINER_CONFIG
           →  ~/.scitex/container/config.yaml  →  built-in defaults
```

## Commands

| Command             | Purpose                                                  |
|---------------------|----------------------------------------------------------|
| `apptainer`         | Apptainer (SIF) container operations — build / freeze / verify / status / version / rollback / deploy / clean |
| `docker`            | Manage Docker Compose services — rebuild / restart |
| `host`              | Host-side packages + mount configuration — check / install / show-mounts |
| `sandbox`           | Manage Apptainer sandbox directories — create / maintain / list / switch / rollback / clean / update / configure-ps1 / purge-sifs |
| `save-env-snapshot` | Capture environment snapshot for reproducibility (JSON)  |
| `show-status`       | Unified status dashboard (Apptainer + host + Docker)     |
| `mcp`               | MCP (Model Context Protocol) server management — start / doctor / list-tools / install |
| `skills`            | Agent-facing skills — list / get / install               |
| `list-python-apis`  | List public Python APIs (apptainer, docker, host)        |
| `install-shell-completion` | Wire up `<TAB>` completion in the user's shell rc  |
| `print-shell-completion`   | Print the click-generated completion script to stdout |

## Companion entry point

`pip install 'scitex-container[mcp]'` also installs:

| Console script             | Purpose                                       |
|----------------------------|-----------------------------------------------|
| `scitex-container-mcp`     | Standalone MCP server (14 tools)              |

## Examples

```bash
# Apptainer lifecycle
scitex-container apptainer build scitex-final
scitex-container apptainer freeze /opt/containers/scitex-v0.2.0.sif
scitex-container apptainer list
scitex-container apptainer switch 2.19.5
scitex-container apptainer rollback
scitex-container apptainer deploy
scitex-container apptainer verify /opt/containers/scitex-final.sif

# Sandbox
scitex-container sandbox create --source scitex-final.sif
scitex-container sandbox maintain -s scitex-sandbox/ -- apt-get update
scitex-container sandbox list -d ./containers

# Docker (workstation)
scitex-container docker rebuild
scitex-container docker restart

# Host setup + status
scitex-container host check
scitex-container host install
scitex-container host show-mounts
scitex-container show-status

# Reproducibility snapshot
scitex-container save-env-snapshot
```

## See also

- `17_cli-reference-detailed.md` — historical detailed CLI reference
- `11_mcp-tools.md` — MCP tool surface for AI agents
- `20_environment.md` — environment variables
