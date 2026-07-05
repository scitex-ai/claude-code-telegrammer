---
description: |
  [TOPIC] CLI reference
  [DETAILS] `scitex-dev` subcommands grouped by category (Ecosystem, Development, Documentation, Interface, Shell) — entry-point summary, with pointers to per-command leaves.
tags: [scitex-dev-cli-reference]
---

# CLI reference

```
scitex-dev [OPTIONS] COMMAND [ARGS]...
```

## Global options

| Flag | Effect |
|---|---|
| `-V`, `--version` | Print version and exit |
| `-h`, `--help` | Show help |
| `--help-recursive` | Show help for every subcommand |
| `--json` | Emit structured JSON (propagated to subcommands that honour it) |

Config path resolution:
`./config.yaml → $SCITEX_DEV_CONFIG → ~/.scitex/dev/config.yaml → defaults`
(see [20_env-vars.md](20_env-vars.md)).

## Ecosystem

| Command | Description | Deep dive |
|---|---|---|
| `doctor` | Diagnose the health of the full SciTeX ecosystem | [02_quick-start.md](02_quick-start.md) |
| `ecosystem list` | Registry + installed/PyPI versions | [14_ecosystem.md](14_ecosystem.md) |
| `ecosystem fix-mismatches` | Repair version drift | [13_versions.md](13_versions.md) |
| `ecosystem sync-local` / `sync-host` | Editable / SSH sync | [14_ecosystem.md](14_ecosystem.md) |
| `ecosystem audit-*` | Skills / project / docs audits | [21_dynamic-audit.md](21_dynamic-audit.md) |

## Development

| Command | Description | Deep dive |
|---|---|---|
| `show-config` | Print the resolved `DevConfig` | [12_config.md](12_config.md) |
| `rename-symbols` | Bulk rename with cross-reference updates | [15_rename.md](15_rename.md) |

## Documentation

| Command | Description | Deep dive |
|---|---|---|
| `docs get / search / build` | View / search / rebuild aggregated docs | [16_docs-search.md](16_docs-search.md) |
| `skills list / get / export` | Manage skills across the ecosystem | spec under `_skills/general/03_interface/04_skills/` |

## Interface

| Command | Description |
|---|---|
| `mcp start / stop / status` | MCP (Model Context Protocol) server |
| `list-python-apis` | Tree of public Python callables |

## Shell

| Command | Description |
|---|---|
| `install-tab-completion` | Append a one-line eval to your shell's rc file |

## See also

- Full per-subcommand help: `scitex-dev --help-recursive`
- Test runner CLI: [17_test-runner.md](17_test-runner.md)
- Release pipeline: [18_full-update.md](18_full-update.md), [19_release-deploy.md](19_release-deploy.md)
