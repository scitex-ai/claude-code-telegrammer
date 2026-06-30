#!/usr/bin/env python3
"""Command-line entry point for claude-code-telegrammer.

This Python CLI is a thin launcher that forwards to the canonical TypeScript
server (``ts/telegram-server.ts``). All real logic — env-var precedence,
BOT_TOKEN_HASH, STATE_DIR/AGENT_ID/CHANNEL_SOURCE/TURN_URL resolution, the MCP
server, and the Telegram poller — lives in TS. The single source of truth is
the TS server; Python never reimplements env/hash logic, it only ``execv``s
``bun``.

Subcommands::

    claude-code-telegrammer mcp [start]   Start the MCP server + poller (default).
    claude-code-telegrammer config [...]   Print the resolved config as JSON and
                                           exit, WITHOUT starting the server.

The ``config`` subcommand exists so scitex-agent-container (sac) can preflight a
per-agent bot — assert a token maps to the expected agent identity and detect
two agents resolving to the SAME bot — without starting a poller. Extra args
are passed through, so ``claude-code-telegrammer config --check`` reaches the
TS ``config --check`` mode (single getMe call; never prints the raw token).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# ts/telegram-server.ts relative to the installed package: the repo layout is
#   <repo>/src/claude_code_telegrammer/_cli.py
#   <repo>/ts/telegram-server.ts
# so walk up from this file: _cli.py → claude_code_telegrammer → src → <repo>.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SERVER = _REPO_ROOT / "ts" / "telegram-server.ts"

_USAGE = (
    "usage: claude-code-telegrammer <command> [args]\n"
    "\n"
    "commands:\n"
    "  mcp [start]       start the Telegram MCP server + poller (default)\n"
    "  config [--check]  print the resolved config as JSON and exit, WITHOUT\n"
    "                    starting the server. --check adds a single getMe call\n"
    "                    (bot_username/bot_id). The raw token is never printed.\n"
)


def _resolve_bun() -> str:
    """Return the path to the ``bun`` executable, or exit with a clear error."""
    bun = shutil.which("bun")
    if not bun:
        sys.stderr.write(
            "claude-code-telegrammer: `bun` was not found on PATH.\n"
            "  Install bun (https://bun.sh) — the server runs on the bun runtime.\n"
        )
        raise SystemExit(127)
    return bun


def _require_server() -> str:
    """Return the absolute path to telegram-server.ts, or exit with an error."""
    if not _SERVER.is_file():
        sys.stderr.write(
            f"claude-code-telegrammer: server entry not found at {_SERVER}.\n"
            "  Expected ts/telegram-server.ts alongside the installed package.\n"
        )
        raise SystemExit(2)
    return str(_SERVER)


def _exec_server(*server_args: str) -> "int":
    """``execv`` bun on the TS server with the given args (does not return)."""
    bun = _resolve_bun()
    server = _require_server()
    os.execv(bun, [bun, "run", server, *server_args])
    # os.execv replaces the process image; unreachable on success.
    return 0


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in ("mcp",):
        # `mcp` / `mcp start` (and the bare invocation) start the server.
        passthrough = args[1:] if args else []
        return _exec_server(*passthrough)

    if args[0] == "config":
        # Forward to the TS `config` mode, passing through any extra flags
        # (e.g. --check) so `claude-code-telegrammer config --check` works.
        return _exec_server("config", *args[1:])

    if args[0] in ("-h", "--help", "help"):
        sys.stdout.write(_USAGE)
        return 0

    sys.stderr.write(f"claude-code-telegrammer: unknown command {args[0]!r}\n\n")
    sys.stderr.write(_USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
