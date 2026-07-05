---
description: |
  [TOPIC] Installation
  [DETAILS] pip install scitex-dev + extras (cli, mcp, dev) and a smoke verify via `scitex-dev --version`.
tags: [scitex-dev-installation]
---

# Installation

## Basic install

```bash
pip install scitex-dev
```

## Optional extras

```bash
pip install 'scitex-dev[cli]'        # adds click + rich for the CLI
pip install 'scitex-dev[mcp]'        # adds fastmcp for the MCP server
pip install 'scitex-dev[dev]'        # adds pytest, ruff, mypy for development
pip install 'scitex-dev[cli,mcp]'    # combine
```

| Extra | Provides |
|---|---|
| `cli` | `scitex-dev` console script (click, rich) |
| `mcp` | `scitex-dev mcp start` server (fastmcp) |
| `dev` | Test/lint toolchain |

## Editable / dev install

```bash
git clone https://github.com/scitex/scitex-dev.git
cd scitex-dev
pip install -e '.[cli,mcp,dev]'
```

## Smoke verify

```bash
scitex-dev --version
# scitex-dev, version 0.11.x

scitex-dev doctor
# Health check: Python, ecosystem packages, env vars, optional services
```

If `scitex-dev` is not on PATH after install, ensure your pip user-base `bin/`
is on `$PATH` (e.g. `~/.local/bin`).

## Troubleshooting

- **`scitex-dev: command not found`** — install the `cli` extra (the entry
  point depends on `click`).
- **`mcp start` fails with `ModuleNotFoundError: fastmcp`** — install the
  `mcp` extra.
- **Version mismatches across the ecosystem** — run
  `scitex-dev ecosystem fix-mismatches --dry-run` (see [13_versions.md](13_versions.md)).

See [02_quick-start.md](02_quick-start.md) for a guided first run.
