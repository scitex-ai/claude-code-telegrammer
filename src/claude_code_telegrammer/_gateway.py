#!/usr/bin/env python3
"""Pip-installed entry point for the CCT gateway supervisor.

This Python launcher is a thin ``execve`` wrapper around the canonical
TypeScript supervisor (``ts/gateway-supervisor.ts``), mirroring
:mod:`._cli`: all real logic — token/slot self-resolution, poller spawn +
crash backoff, status file — lives in TS. Python only resolves ``bun``
and the supervisor entry, then replaces its own process image.

Commands (passed through to the supervisor)::

    cct-gateway           supervise the gateway poller (foreground)
    cct-gateway status    print gateway-status.json and exit
    cct-gateway --help    supervisor help
    cct-gateway --version print the package version and exit
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from claude_code_telegrammer import __version__

from ._cli import _resolve_bun

_PACKAGE_SUPERVISOR = (
    Path(__file__).resolve().parent / "ts" / "gateway-supervisor.ts"
)
_SOURCE_SUPERVISOR = (
    Path(__file__).resolve().parents[2] / "ts" / "gateway-supervisor.ts"
)

_USAGE = (
    "usage: cct-gateway [--help] | [status] | [--version]\n"
    "\n"
    "Host-level CCT gateway supervisor: resolves the LEAD-slot bot token\n"
    "and owns one detached ts/telegram-poller.ts for it, restarting on\n"
    "crash with backoff. Normally run as cct-gateway.service, not by hand.\n"
)


def _require_supervisor() -> str:
    """Return the absolute path to gateway-supervisor.ts, or exit."""
    for candidate in (_PACKAGE_SUPERVISOR, _SOURCE_SUPERVISOR):
        if candidate.is_file():
            return str(candidate)
    searched = "\n".join(
        f"  - {candidate}"
        for candidate in (_PACKAGE_SUPERVISOR, _SOURCE_SUPERVISOR)
    )
    sys.stderr.write(
        "cct-gateway: packaged supervisor entry is missing.\n"
        f"Searched:\n{searched}\n"
        "Reinstall claude-code-telegrammer from a wheel containing its ts runtime.\n"
    )
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in ("--version", "-V"):
        print(__version__)
        return 0

    if args and args[0] in ("-h", "--help", "help"):
        sys.stdout.write(_USAGE)
        return 0

    bun = _resolve_bun("cct-gateway")
    supervisor = _require_supervisor()
    env = os.environ.copy()
    env["_CCT_PYTHON_EXECUTABLE"] = sys.executable
    os.execve(bun, [bun, "run", supervisor, *args], env)
    # os.execve replaces the process image; unreachable on success.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
