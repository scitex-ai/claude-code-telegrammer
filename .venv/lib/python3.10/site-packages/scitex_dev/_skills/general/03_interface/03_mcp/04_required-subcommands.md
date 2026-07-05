---
description: |
  [TOPIC] Interface Mcp Required Subcommands
  [DETAILS] SciTeX MCP — required `mcp` subcommands every package CLI must expose (start, doctor, list-tools, install).
tags: [scitex-general-interface-mcp-required-subcommands]
---

# §3. Required MCP subcommands

Every package CLI that registers any MCP tools **must** expose **all four** of these `mcp` subcommands. Shipping only a subset (e.g. only `list-tools`, as scitex-scholar did pre-2026-05-06 — `scitex-scholar mcp start` errored with `invalid choice: 'start' (choose from 'list-tools')`) is a §3 violation: users cannot start the server, diagnose problems, or generate the install snippet.

| Subcommand                    | Required? | Purpose                                                                  |
|-------------------------------|-----------|--------------------------------------------------------------------------|
| `<cli> mcp start`             | **yes**   | Launch the MCP server (stdio by default). Without this the server cannot run. |
| `<cli> mcp doctor`            | **yes**   | Self-diagnose the MCP install (deps, config, registration).              |
| `<cli> mcp list-tools`        | **yes**   | Enumerate registered MCP tools — `-v|-vv|-vvv` and `--json` mandated.    |
| `<cli> mcp install` | **yes**   | Print the snippet to add to a Claude Code / MCP-host config.             |

Reference shape — adding the four to a click `mcp` group (one canonical helper, drop into every standalone `_cli`):

```python
# scitex_<pkg>/_cli/_mcp.py
from scitex_dev._mcp_cli import attach_mcp_subcommands

@click.group()
def mcp(): ...

attach_mcp_subcommands(mcp, server_path="scitex_<pkg>._mcp_server:mcp", cli_name="scitex-<pkg>")
```

`attach_mcp_subcommands` registers `start`, `doctor`, `list-tools`, `install` in one call. Standalones MUST use this helper rather than rolling their own — packages that hand-roll the `mcp` group (scitex-scholar pre-fix) reliably ship only `list-tools` and forget the rest.

## `mcp start`

- Default transport: stdio (newline-delimited JSON-RPC).
- Optional flags: `--http`, `--port`, `--host` for HTTP transport. Document in `--help`.
- Must exit 0 cleanly when stdio is closed; exit 2 on bad config.

## `mcp doctor`

- Verifies: fastmcp version, package install (importable), tool count, optional dep state.
- Output is human-readable on stderr; structured JSON on `--json`.
- Returns exit 0 if healthy, 1 on degradation, 2 on critical (cannot start).

## `mcp list-tools`

- See [05_list-tools-ladder.md](05_list-tools-ladder.md) for the verbosity ladder.

## `mcp install`

Print the JSON snippet a user pastes into their Claude Code / MCP host config. Example:

```bash
$ scitex-io mcp install
{
  "mcpServers": {
    "scitex-io": {
      "command": "scitex-io",
      "args": ["mcp", "start"]
    }
  }
}
```

- `--shell bash` / `--shell zsh` / `--shell fish` to print shell-specific install one-liners (optional).
- `--format claude-code` (default) / `--format other-host` for alternative MCP hosts.
