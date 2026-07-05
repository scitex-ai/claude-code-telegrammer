#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev creds`` Click commands.

Sub-commands
------------
- ``rotate-all``      — push local ``~/.claude/.credentials.json`` to the
                         ``CLAUDE_CODE_CREDENTIALS_JSON`` secret slot of
                         every package in the ecosystem registry whose
                         sha256 sidecar differs from the local file.
- ``install-cron``    — install / replace the managed crontab line.
- ``uninstall-cron``  — remove the managed crontab line.

NEVER logs raw credential content — only sha256 and byte counts.
"""

from __future__ import annotations

from pathlib import Path

import click

from ..._creds import (
    CREDENTIALS_PATH,
    CREDENTIALS_SLOT,
    SHA256_VAR,
    rotate_all,
    validate_source,
)
from ..._creds import _cron as cron_mod


def register_creds_commands(main_group) -> click.Group:
    """Register ``scitex-dev creds`` on the given Click main group."""

    @main_group.group("creds", invoke_without_command=True)
    @click.pass_context
    def creds(ctx: click.Context) -> None:
        """Ecosystem-wide Claude Code credential rotation.

        \b
        Uploads ~/.claude/.credentials.json as the GitHub Actions secret
        CLAUDE_CODE_CREDENTIALS_JSON (with sha256 sidecar variable
        CLAUDE_CODE_CREDENTIALS_JSON_SHA256) across every scitex package.

        \b
        This is the un-prefixed multiplexer. The package-prefixed sac
        single-repo command (`sac dev upload-credentials-to-github`,
        slot `SAC_CLAUDE_CODE_CREDENTIALS_JSON`) is unaffected.
        """
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    _register_rotate_all(creds)
    _register_install_cron(creds)
    _register_uninstall_cron(creds)
    return creds


def _register_rotate_all(creds: click.Group) -> None:
    @creds.command("rotate-all")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Resolve repos and compare hashes, but never call `gh`.",
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Confirm rotation. Required when --dry-run is not set "
        "AND at least one repo would actually be rotated.",
    )
    @click.option(
        "--force",
        is_flag=True,
        default=False,
        help="Push even if the sha256 sidecar already matches.",
    )
    @click.option(
        "--only",
        "only",
        multiple=True,
        metavar="PKG",
        help="Restrict to these packages (repeatable).",
    )
    @click.option(
        "--exclude",
        "exclude",
        multiple=True,
        metavar="PKG",
        help="Skip these packages (repeatable).",
    )
    @click.option(
        "--source",
        "source",
        type=click.Path(path_type=Path),
        default=None,
        help="Override the source credentials file path.",
    )
    def rotate_all_cmd(
        dry_run: bool,
        yes: bool,
        force: bool,
        only: tuple[str, ...],
        exclude: tuple[str, ...],
        source: Path | None,
    ) -> None:
        """Rotate CLAUDE_CODE_CREDENTIALS_JSON across the ecosystem.

        \b
        Per-package status:
          unchanged | rotated | skipped (no remote) | error: <msg>

        \b
        Exits 0 if every reachable repo is unchanged-or-rotated. Exits
        non-zero if any repo reports `error`. Exits 0 silently if the
        local credentials file is missing or its OAuth token has expired
        (operator must `claude /login` first; don't push a stale token).

        \b
        Example:
          $ scitex-dev creds rotate-all --dry-run
          $ scitex-dev creds rotate-all --yes
          $ scitex-dev creds rotate-all --only scitex-io --only scitex-stats --yes
        """
        source_path = source or CREDENTIALS_PATH

        # Source validation runs once up-front so we can give a single
        # actionable error (or silently exit 0) before we ever touch gh.
        try:
            state = validate_source(source_path)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        if state is None:
            # File missing or token expired — silent no-op so the cron
            # doesn't spam every hour.
            return

        click.echo(f"source:      {source_path}")
        click.echo(f"local bytes: {state.byte_count}")
        click.echo(f"local sha:   {state.sha256}")
        click.echo(f"slot:        {CREDENTIALS_SLOT}")
        click.echo(f"sha var:     {SHA256_VAR}")
        click.echo("")

        # First do a dry-run pass so we can require --yes only when at
        # least one repo would actually be touched.
        try:
            preview = rotate_all(
                only=only or None,
                exclude=exclude or None,
                source_path=source_path,
                dry_run=True,
                force=force,
            )
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        would_rotate = [r for r in preview if r.status == "dry-run"]
        if dry_run or not would_rotate:
            results = preview
        else:
            if not yes:
                click.echo(
                    f"Refusing to rotate {len(would_rotate)} repo(s) without --yes/-y.",
                    err=True,
                )
                raise SystemExit(2)
            try:
                results = rotate_all(
                    only=only or None,
                    exclude=exclude or None,
                    source_path=source_path,
                    dry_run=False,
                    force=force,
                )
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc

        errors = 0
        for r in results:
            repo = r.repo or "-"
            line = f"  {r.package:32s}  {repo:42s}  {r.status:9s}  {r.message}"
            if r.is_error():
                errors += 1
                click.secho(line, fg="red")
            elif r.status == "rotated":
                click.secho(line, fg="green")
            elif r.status == "skipped":
                click.secho(line, fg="yellow")
            else:
                click.echo(line)

        click.echo("")
        click.echo(
            f"summary: {len(results)} package(s); "
            f"errors={errors}; "
            f"rotated={sum(1 for r in results if r.status == 'rotated')}; "
            f"unchanged={sum(1 for r in results if r.status == 'unchanged')}; "
            f"dry-run={sum(1 for r in results if r.status == 'dry-run')}; "
            f"skipped={sum(1 for r in results if r.status == 'skipped')}"
        )
        if errors:
            raise SystemExit(1)


def _register_install_cron(creds: click.Group) -> None:
    @creds.command("install-cron")
    @click.option(
        "--interval-minutes",
        type=int,
        default=60,
        help="Cron interval (default: 60 → `0 * * * *`).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print the cron line that would be installed.",
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Confirm the install. Required when not --dry-run.",
    )
    def install_cron_cmd(interval_minutes: int, dry_run: bool, yes: bool) -> None:
        """Install a crontab line that runs `creds rotate-all` periodically.

        \b
        Idempotent: a single line tagged
            # scitex-dev creds-rotate (managed)
        is managed in place — reinstall replaces it.

        \b
        Logs to ~/.scitex/dev/logs/creds-rotate.log (size-rotated at 1 MiB).

        \b
        Example:
          $ scitex-dev creds install-cron --dry-run
          $ scitex-dev creds install-cron --yes
          $ scitex-dev creds install-cron --interval-minutes 30 --yes
        """
        if dry_run:
            line = cron_mod.install(interval_minutes, dry_run=True)
            click.echo(line)
            return
        if not yes:
            click.echo(
                "Refusing to write to crontab without --yes/-y.",
                err=True,
            )
            raise SystemExit(2)
        try:
            line = cron_mod.install(interval_minutes, dry_run=False)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(line)
        click.echo("installed.")


def _register_uninstall_cron(creds: click.Group) -> None:
    @creds.command("uninstall-cron")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Show how many managed lines would be removed without writing.",
    )
    @click.option(
        "-y", "--yes", is_flag=True, default=False, help="Confirm the uninstall."
    )
    def uninstall_cron_cmd(dry_run: bool, yes: bool) -> None:
        """Remove the managed crontab line.

        \b
        Example:
          $ scitex-dev creds uninstall-cron --dry-run
          $ scitex-dev creds uninstall-cron --yes
        """
        if dry_run:
            preview = cron_mod.uninstall(dry_run=True)
            click.echo(f"would remove {preview} managed line(s).")
            return
        if not yes:
            preview = cron_mod.uninstall(dry_run=True)
            click.echo(
                f"would remove {preview} managed line(s). Re-run with --yes to apply."
            )
            raise SystemExit(0 if preview == 0 else 2)
        try:
            removed = cron_mod.uninstall(dry_run=False)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"removed {removed} managed line(s).")


# EOF
