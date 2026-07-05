#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem run`` — the collective ecosystem supervisor.

This is the ``ExecStart`` of ``scitex-dev-ecosystem.service`` (operator
policy 2026-06-14: the SOLE systemd ``--user`` entry for the SciTeX
fleet). Long-running foreground process; foreground because systemd
``Type=simple`` expects ExecStart to not double-fork — and because
``journalctl --user -u scitex-dev-ecosystem`` then picks up the
supervisor's stdout/stderr without any extra wiring.

The command itself is intentionally thin — almost all the work lives
in :func:`scitex_dev._supervisor.run_supervisor`. Keeping the CLI as a
thin shim means a future ``--config-file`` / ``--once`` / ``--dry-run``
option lands here without disturbing the loop body.

Backwards compat
----------------
This command is NEW in PR-1 of the supervisor migration; no prior
``ecosystem run`` existed, so we have no historical args to maintain.
"""

from __future__ import annotations

import logging
import sys

import click

from ...._supervisor import run_supervisor


def register(ecosystem):
    @ecosystem.command(
        "run",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem run\n"
            "      (Run forever — long-running foreground process; this is\n"
            "       what systemd invokes via scitex-dev-ecosystem.service.)\n"
            "\n"
            "  $ scitex-dev ecosystem run --max-ticks 3\n"
            "      (Run 3 tick cycles then exit; smoke-test path. The state\n"
            "       file is written between ticks so a follow-up\n"
            "       `scitex-dev ecosystem status` can verify the supervisor\n"
            "       wrote a snapshot without sitting through the long-poll.)\n"
            "\n"
            "Backed by scitex_dev._supervisor.run_supervisor; that module's\n"
            "docstring documents the tick budget, signal-handling, hot-\n"
            "reload (SIGHUP), and the state-file path.\n"
        ),
    )
    @click.option(
        "--max-ticks",
        type=int,
        default=None,
        help=(
            "Stop after N ticks instead of looping forever. Test seam — "
            "production omits this and the supervisor runs until SIGTERM."
        ),
    )
    @click.option(
        "-v",
        "--verbose",
        is_flag=True,
        help=(
            "Set the supervisor's log level to DEBUG (default WARNING). "
            "The supervisor's diagnostics go to stdout/stderr → captured "
            "by systemd into journalctl."
        ),
    )
    def ecosystem_run(max_ticks, verbose):
        """Run the SciTeX ecosystem supervisor (Type=simple, foreground)."""
        # Configure logging on the way in. systemd Type=simple captures
        # stdout + stderr into the journal, so logging.basicConfig with
        # the default stderr handler is correct here — no journal-specific
        # handler needed.
        logging.basicConfig(
            level=logging.DEBUG if verbose else logging.WARNING,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            stream=sys.stderr,
        )
        rc = run_supervisor(max_ticks=max_ticks)
        sys.exit(rc)


__all__ = ["register"]


# EOF
