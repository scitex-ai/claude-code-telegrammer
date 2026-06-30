#!/usr/bin/env python3
"""Console entry point launching the TypeScript Telegram MCP server."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from claude_code_telegrammer import __version__

# <root>/src/claude_code_telegrammer/_cli.py -> <root>
_ROOT = Path(__file__).resolve().parents[2]
_SERVER = _ROOT / "ts" / "telegram-server.ts"


def _resolve_bun() -> str | None:
    candidates = [
        os.environ.get("BUN_BIN"),
        shutil.which("bun"),
        os.path.expanduser("~/.bun/bin/bun"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _launch(passthrough: list[str]) -> None:
    bun = _resolve_bun()
    if not bun:
        sys.exit("error: 'bun' not found; set $BUN_BIN or install bun")
    if not _SERVER.exists():
        sys.exit(f"error: TS MCP server not found at {_SERVER}")
    os.execv(bun, [bun, "run", str(_SERVER), *passthrough])


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(
        prog="claude-code-telegrammer",
        description="Launch the Telegram MCP server (bun run ts/telegram-server.ts).",
        add_help=True,
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")

    args, rest = parser.parse_known_args(argv)

    if args.version:
        print(__version__)
        return

    if not rest:
        _launch([])
        return

    command, *tail = rest
    if command == "mcp":
        if tail and tail[0] == "start":
            tail = tail[1:]
        _launch(tail)
        return

    sys.stderr.write(
        f"usage: claude-code-telegrammer [--version] [mcp [start]]\n"
        f"unknown subcommand: {command}\n"
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
