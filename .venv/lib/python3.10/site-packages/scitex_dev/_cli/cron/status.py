#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron status`` — last-run / next-run for managed jobs."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import click

from . import _crontab
from ._jobs import JOB_REGISTRY


def _last_run_from_log(name: str) -> str:
    """Best-effort last-run timestamp from the job's log file.

    Convention: each job writes to ``~/.scitex/dev/logs/cron-<name>.log``
    (the registry's command line does this via ``mkdir -p && >>``).
    We report the file's mtime — exact enough for an operator to see
    "the loop is alive" without parsing the log body.
    """
    log = Path.home() / ".scitex" / "dev" / "logs" / f"cron-{name}.log"
    if not log.exists():
        return "(no log yet)"
    mtime = _dt.datetime.fromtimestamp(log.stat().st_mtime)
    return mtime.isoformat(timespec="seconds")


def register(group: click.Group) -> None:
    @group.command("status")
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Output as structured JSON.",
    )
    def status_cmd(as_json: bool) -> None:
        """Show last-run / next-run hints for every managed cron job.

        \b
        Reports per-job:
          - installed?   — line is present in `crontab -l`
          - schedule     — declared schedule (registry) and installed
                           schedule (crontab); flagged if they drift
          - last-run     — mtime of `~/.scitex/dev/logs/cron-<name>.log`
          - next-run     — raw schedule (operator interprets)

        \b
        Example:
          $ scitex-dev cron status
          $ scitex-dev cron status --json
        """
        try:
            current = _crontab.read_crontab()
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        managed = {m.name: m for m in _crontab.parse_managed(current)}

        rows: list[dict] = []
        for name in sorted(JOB_REGISTRY):
            spec = JOB_REGISTRY[name]
            line = managed.get(name)
            if line is None:
                installed = "no"
                schedule = spec.schedule
            elif line.schedule != spec.schedule or line.command != spec.command:
                installed = "drifted"
                schedule = f"{line.schedule} (was {spec.schedule})"
            else:
                installed = "yes"
                schedule = line.schedule
            rows.append(
                {
                    "name": name,
                    "installed": installed,
                    "schedule": schedule,
                    "last_run": _last_run_from_log(name),
                    "description": spec.description,
                }
            )

        unknown = [
            {"name": m.name, "raw": m.raw}
            for m in managed.values()
            if m.name not in JOB_REGISTRY
        ]

        if as_json:
            click.echo(json.dumps({"jobs": rows, "unknown": unknown}, indent=2))
            return

        click.secho(
            f"{'name':16s} {'installed':10s} {'schedule':14s} "
            f"{'last-run':25s} description",
            bold=True,
        )
        for r in rows:
            click.echo(
                f"{r['name']:16s} {r['installed']:10s} {r['schedule']:14s} "
                f"{r['last_run']:25s} {r['description']}"
            )

        if unknown:
            click.echo("")
            click.secho("unknown managed lines:", bold=True, fg="yellow")
            for u in unknown:
                click.echo(f"  {u['name']:16s} {u['raw']}")


# EOF
