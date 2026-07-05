#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/_cli/_docker.py
"""CLI docker sub-group for Docker Compose management."""

from __future__ import annotations

import click


@click.group()
def docker():
    """Manage Docker Compose services."""


@docker.command(name="rebuild")
@click.option(
    "--env", "-e", default="dev", show_default=True, help="Environment (dev/prod)."
)
@click.option(
    "--dry-run", is_flag=True, help="Print the planned action without executing."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Skip interactive confirmation prompts."
)
def docker_rebuild(env, dry_run, yes):
    """Rebuild Docker containers without cache.

    \b
    Example:
      $ scitex-container docker rebuild
      $ scitex-container docker rebuild --env prod
      $ scitex-container docker rebuild --dry-run
    """
    if dry_run:
        click.echo(f"[dry-run] would rebuild docker compose env={env} (no-cache)")
        return
    _ = yes
    from scitex_container.docker import rebuild as do_rebuild

    click.secho(f"Rebuilding Docker containers for env={env}...", fg="cyan")
    rc = do_rebuild(env=env)
    if rc != 0:
        click.secho(f"docker compose build exited with code {rc}", fg="red", err=True)
        raise SystemExit(rc)
    click.secho("Rebuild complete.", fg="green")


@docker.command(name="restart")
@click.option(
    "--env", "-e", default="dev", show_default=True, help="Environment (dev/prod)."
)
@click.option(
    "--dry-run", is_flag=True, help="Print the planned action without executing."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Skip interactive confirmation prompts."
)
def docker_restart(env, dry_run, yes):
    """Restart Docker containers (down then up -d).

    \b
    Example:
      $ scitex-container docker restart
      $ scitex-container docker restart --env prod
      $ scitex-container docker restart --dry-run
    """
    if dry_run:
        click.echo(f"[dry-run] would restart docker compose env={env}")
        return
    _ = yes
    from scitex_container.docker import restart as do_restart

    click.secho(f"Restarting Docker containers for env={env}...", fg="cyan")
    rc = do_restart(env=env)
    if rc != 0:
        click.secho(f"docker compose restart exited with code {rc}", fg="red", err=True)
        raise SystemExit(rc)
    click.secho("Containers restarted.", fg="green")


# EOF
