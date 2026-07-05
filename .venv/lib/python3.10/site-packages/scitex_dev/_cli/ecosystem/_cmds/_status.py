#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem status`` — read the supervisor's state snapshot.

Cheap read against the static JSON file the supervisor writes every
``state_write_interval_sec`` (5s default). Never talks to the supervisor
process — no IPC, no signal-ping — so asking for status is always safe
and never perturbs a running child.

Two output modes:

* Default human-readable table (one row per child) — for operator eyes.
* ``--json`` raw snapshot pass-through — for scripting.

The CLI is forgiving about a missing / empty / corrupted snapshot
(``read_state`` returns ``None`` rather than raising); the operator sees
"supervisor not running" instead of a traceback. That matches the
behaviour-under-uncertainty bar everywhere else in the ecosystem
audit suite.
"""

from __future__ import annotations

import sys
import time

import click

from ...._supervisor import default_state_path
from ...._supervisor._state import read_state


def _fmt_duration(secs: float) -> str:
    """Compact h/m/s formatter for the human table."""
    if secs <= 0:
        return "—"
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m{secs % 60:02d}s"
    if secs < 86400:
        h = secs // 3600
        m = (secs % 3600) // 60
        return f"{h}h{m:02d}m"
    d = secs // 86400
    h = (secs % 86400) // 3600
    return f"{d}d{h:02d}h"


def _render_human(state) -> str:
    """Render a fixed-column table for human reading."""
    now = time.time()
    sup_uptime = _fmt_duration(now - state.started_at) if state.started_at else "—"
    snap_age = _fmt_duration(now - state.written_at) if state.written_at else "—"
    header = (
        f"supervisor: pid={state.pid} uptime={sup_uptime} "
        f"snap_age={snap_age} version={state.scitex_dev_version}\n"
    )
    if not state.children:
        return header + "  (no children — no kind='service' JobSpecs discovered)\n"
    cols = ["NAME", "STATUS", "PID", "UPTIME", "RESTARTS", "BREAKER", "LAST_EXIT"]
    widths = [max(20, max(len(c["name"]) for c in state.children) + 2)] + [
        len(h) for h in cols[1:]
    ]
    # Recompute widths against actual content for stable columns.
    rows = []
    for c in state.children:
        uptime = (
            _fmt_duration(now - c["started_at"])
            if c.get("status") == "running" and c.get("started_at")
            else "—"
        )
        breaker = "OPEN" if c.get("circuit_open") else "closed"
        last = c.get("last_exit_code")
        last_s = "—" if last is None else str(last)
        rows.append(
            [
                c["name"],
                c["status"],
                str(c.get("pid") or "—"),
                uptime,
                str(c["restart_count"]),
                breaker,
                last_s,
            ]
        )
    widths = [max(len(cols[i]), max(len(r[i]) for r in rows)) for i in range(len(cols))]
    out = [header]
    out.append("  " + "  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    out.append("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        out.append("  " + "  ".join(s.ljust(w) for s, w in zip(r, widths)))
    return "\n".join(out) + "\n"


def register(ecosystem):
    @ecosystem.command(
        "status",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem status\n"
            "      (Human-readable table — one row per child service.)\n"
            "\n"
            "  $ scitex-dev ecosystem status --json\n"
            "      (Raw state.json pass-through — for scripting.)\n"
            "\n"
            "Reads ~/.local/state/scitex-ecosystem/state.json — the snapshot\n"
            "the supervisor writes every 5s. Never talks to the supervisor\n"
            "process, so calling this is free.\n"
        ),
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help="Emit the raw state snapshot as JSON.",
    )
    @click.option(
        "--state-path",
        type=click.Path(dir_okay=False),
        default=None,
        help=(
            "Read the snapshot from PATH instead of the default "
            "~/.local/state/scitex-ecosystem/state.json. Test seam."
        ),
    )
    def ecosystem_status(as_json, state_path):
        """Show the SciTeX ecosystem supervisor's current state."""
        from pathlib import Path as _Path

        path = _Path(state_path) if state_path else default_state_path()
        state = read_state(path)
        if state is None:
            if as_json:
                click.echo("null")
            else:
                click.echo(
                    f"supervisor: no snapshot at {path} — supervisor not running, "
                    "or has not written its first state yet.",
                    err=True,
                )
            sys.exit(1)
        if as_json:
            click.echo(state.to_json())
        else:
            click.echo(_render_human(state), nl=False)


__all__ = ["register"]


# EOF
