#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron remove <name>`` — strip a managed cron line."""

from __future__ import annotations

import click

from . import _crontab


def register(group: click.Group) -> None:
    @group.command("remove")
    @click.argument("name")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Report how many lines would be removed; do not write.",
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Confirm. Required when not --dry-run.",
    )
    def remove_cmd(name: str, dry_run: bool, yes: bool) -> None:
        """Remove the managed cron line for NAME.

        \b
        Operates only on lines tagged with the marker
            # scitex-dev cron: <name>
        Every other line in the crontab is preserved verbatim.

        \b
        Example:
          $ scitex-dev cron remove ci-watch --dry-run
          $ scitex-dev cron remove ci-watch --yes
        """
        try:
            current = _crontab.read_crontab()
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        new, removed = _crontab.remove_managed(current, name)

        if dry_run:
            click.echo(f"would remove {removed} managed line(s) for {name!r}.")
            return

        if removed == 0:
            click.echo(f"no managed line found for {name!r}; nothing to do.")
            return

        if not yes:
            click.echo(
                f"would remove {removed} managed line(s) for {name!r}. "
                "Re-run with --yes to apply.",
                err=True,
            )
            raise SystemExit(2)

        try:
            _crontab.write_crontab(new)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(f"removed {removed} managed line(s) for {name!r}.")


# EOF
