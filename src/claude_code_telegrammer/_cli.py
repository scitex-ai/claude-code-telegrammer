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
    claude-code-telegrammer health         Run the health check (doctor) and
                                           print the JSON report, WITHOUT
                                           starting the server. Exit code
                                           reflects probe success, not health.
    claude-code-telegrammer --version      Print the package version and exit.

The ``config`` subcommand exists so scitex-agent-container (sac) can preflight a
per-agent bot — assert a token maps to the expected agent identity and detect
two agents resolving to the SAME bot — without starting a poller. Extra args
are passed through, so ``claude-code-telegrammer config --check`` reaches the
TS ``config --check`` mode (single getMe call; never prints the raw token).

Where the TS entry comes from is decided by
:mod:`claude_code_telegrammer._server_entry`: ``$CCT_SERVER_ENTRY`` first, then
the ``ts/`` directory shipped inside the installed package, then the
``<repo>/ts/`` source tree. Every server-bound subcommand resolves it BEFORE
doing anything else, so a broken install announces itself at startup with the
full list of paths tried rather than dying quietly at first use.
"""

from __future__ import annotations

import os
import shutil
import sys

from claude_code_telegrammer import __version__
from claude_code_telegrammer._server_entry import (
    ENV_SERVER_ENTRY,
    ServerEntryNotFound,
    resolve_server_entry,
)

_USAGE = (
    "usage: claude-code-telegrammer <command> [args]\n"
    "\n"
    "commands:\n"
    "  mcp [start]       start the Telegram MCP server + poller (default)\n"
    "  config [--check]  print the resolved config as JSON and exit, WITHOUT\n"
    "                    starting the server. --check adds a single getMe call\n"
    "                    (bot_username/bot_id). The raw token is never printed.\n"
    "  health            run the health check (doctor) and print the JSON report\n"
    "                    {package, ok, checks[], summary}, WITHOUT starting the\n"
    "                    server. Exits 0 even when unhealthy — a false `ok` is a\n"
    "                    finding, not a crash. The raw token is never printed.\n"
    "  send --chat-id <id> --text <msg> [--reply-to <message_id>]\n"
    "                    send ONE outbound Telegram message and exit, WITHOUT\n"
    "                    starting the server or the poller. The MCP-INDEPENDENT\n"
    "                    outbound path: use it when the cct MCP tools are\n"
    "                    unavailable and an agent would otherwise be unable to\n"
    "                    reach the operator at all. Exits NON-ZERO on failure.\n"
    "  --version         print the package version and exit\n"
    "\n"
    "environment:\n"
    f"  {ENV_SERVER_ENTRY}\n"
    "                    absolute path to ts/telegram-server.ts, overriding\n"
    "                    both the packaged copy and the source tree. When set\n"
    "                    it is AUTHORITATIVE: a path that does not exist is an\n"
    "                    error, never a silent fallback to another server.\n"
    "  BUN_BIN           path to the `bun` executable (default: $PATH, then\n"
    "                    ~/.bun/bin/bun)\n"
)


def _resolve_bun() -> str:
    """Return the path to the ``bun`` executable, or exit with a clear error."""
    candidates = [
        os.environ.get("BUN_BIN"),
        shutil.which("bun"),
        os.path.expanduser("~/.bun/bin/bun"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    sys.stderr.write(
        "claude-code-telegrammer: `bun` was not found.\n"
        "  Set $BUN_BIN or install bun (https://bun.sh) — the server runs on bun.\n"
    )
    raise SystemExit(127)


def _require_server() -> str:
    """Return the absolute path to telegram-server.ts, or exit with an error.

    Resolution lives in :mod:`claude_code_telegrammer._server_entry`; this
    only turns its exception into the CLI's stderr-plus-exit-2 contract. The
    message names every path that was tried, because "not found at
    <one wrong path>" told an operator nothing about which of the three
    mechanisms — override, packaged resource, source tree — had failed.
    """
    try:
        return str(resolve_server_entry())
    except ServerEntryNotFound as exc:
        sys.stderr.write(f"{exc}\n")
        raise SystemExit(2) from exc


def _exec_server(*server_args: str) -> int:
    """``execv`` bun on the TS server with the given args (does not return)."""
    # Server entry FIRST, bun second: both are required, and resolving the
    # entry up front means a packaging fault reports itself as a packaging
    # fault instead of hiding behind a missing-bun message on hosts that
    # happen to lack bun as well.
    server = _require_server()
    bun = _resolve_bun()
    os.execv(bun, [bun, "run", server, *server_args])
    # os.execv replaces the process image; unreachable on success.
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in ("--version", "-V"):
        print(__version__)
        return 0

    if args and args[0] in ("-h", "--help", "help"):
        sys.stdout.write(_USAGE)
        return 0

    if not args or args[0] == "mcp":
        # `mcp` / `mcp start` (and the bare invocation) start the server.
        passthrough = args[1:] if args else []
        if passthrough and passthrough[0] == "start":
            passthrough = passthrough[1:]
        return _exec_server(*passthrough)

    if args[0] == "config":
        # Forward to the TS `config` mode, passing through any extra flags
        # (e.g. --check) so `claude-code-telegrammer config --check` works.
        return _exec_server("config", *args[1:])

    if args[0] == "health":
        # Forward to the TS `health` mode (the doctor). Like `config`, it
        # resolves without starting the server/poller and exits 0 regardless
        # of the health verdict — the JSON `ok` field is the finding.
        return _exec_server("health", *args[1:])

    if args[0] == "send":
        # Forward to the TS `send` mode: deliver ONE outbound message and exit,
        # without starting the MCP server or the poller.
        #
        # This is the MCP-INDEPENDENT outbound path (card
        # cct-cli-send-outbound-path-independent-of-mcp). When the cct MCP
        # server is down — or when its instructions load but its TOOLS do not
        # resolve — an agent has no `reply` tool and cannot reach the operator
        # at all. It goes mute, and he reads the silence as being ignored.
        # A CLI does not depend on MCP tool-schema exposure, so an agent can
        # always shell out to this. Unlike `config`/`health`, a failure here
        # exits NON-ZERO: an agent must never believe it delivered when it did
        # not.
        return _exec_server("send", *args[1:])

    sys.stderr.write(f"claude-code-telegrammer: unknown command {args[0]!r}\n\n")
    sys.stderr.write(_USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
