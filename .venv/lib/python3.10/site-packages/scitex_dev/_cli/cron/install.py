#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron install <name>`` — materialise a managed job."""

from __future__ import annotations

import click

from . import _crontab
from ._jobs import get_job


def register(group: click.Group) -> None:
    @group.command("install")
    @click.argument("name")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print the cron line that would be written; do not touch crontab.",
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Confirm. Required when not --dry-run.",
    )
    def install_cmd(name: str, dry_run: bool, yes: bool) -> None:
        """Install (or replace) the managed cron line for NAME.

        \b
        Idempotent: a single line tagged
            # scitex-dev cron: <name>
        is managed in place — reinstall replaces it. Unrelated crontab
        lines are preserved verbatim.

        \b
        Example:
          $ scitex-dev cron install ci-watch --dry-run
          $ scitex-dev cron install ci-watch --yes
        """
        try:
            spec = get_job(name)
        except KeyError as exc:
            raise click.ClickException(str(exc)) from exc

        line = _crontab.build_line(spec.name, spec.schedule, spec.command)

        if dry_run:
            click.echo(line)
            return

        if not yes:
            click.echo("Refusing to write to crontab without --yes/-y.", err=True)
            raise SystemExit(2)

        try:
            current = _crontab.read_crontab()
            new = _crontab.upsert_managed(
                current, spec.name, spec.schedule, spec.command
            )
            _crontab.write_crontab(new)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(line)
        click.echo("installed.")


# EOF
