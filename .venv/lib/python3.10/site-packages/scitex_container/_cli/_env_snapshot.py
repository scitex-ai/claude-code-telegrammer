#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/_cli/_env_snapshot.py
"""CLI env-snapshot command — Clew reproducibility integration."""

from __future__ import annotations

import json

import click


@click.command("save-env-snapshot")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON.")
@click.option(
    "--dev-repo",
    multiple=True,
    metavar="PATH",
    help="Git repo path to include in snapshot (repeatable).",
)
@click.option(
    "--containers-dir",
    default="",
    help="Containers directory (auto-detected if not given).",
)
@click.option(
    "--dry-run", is_flag=True, help="Print the planned action without executing."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Skip interactive confirmation prompts."
)
@click.pass_context
def env_snapshot_cmd(
    ctx,
    as_json: bool,
    dev_repo: tuple[str, ...],
    containers_dir: str,
    dry_run: bool,
    yes: bool,
) -> None:
    """Capture environment snapshot for reproducibility (Clew integration).

    Records container version, SIF hash, host package versions, dev repo
    git commits, and lock file hashes as a JSON document.

    \b
    Example:
      $ scitex-container save-env-snapshot
      $ scitex-container save-env-snapshot --json
      $ scitex-container save-env-snapshot --dev-repo ~/proj/scitex-python
    """
    if dry_run:
        click.echo(
            f"[dry-run] would capture env snapshot containers_dir="
            f"{containers_dir or '<auto>'} dev_repos={list(dev_repo)}"
        )
        return
    _ = yes
    ctx.ensure_object(dict)
    if not as_json:
        as_json = bool(ctx.obj.get("as_json"))

    from scitex_container import env_snapshot

    snap = env_snapshot(
        containers_dir=containers_dir or None,
        dev_repos=list(dev_repo) if dev_repo else None,
    )

    if as_json:
        click.echo(json.dumps(snap, indent=2))
    else:
        _print_snapshot(snap)


# ---------------------------------------------------------------------------
# Pretty-print helper
# ---------------------------------------------------------------------------


def _print_snapshot(snap: dict) -> None:
    """Display a snapshot dict in a human-readable coloured format."""
    click.secho("Environment Snapshot", fg="cyan", bold=True)
    click.echo(f"  Schema:    {snap.get('schema_version', '?')}")
    click.echo(f"  Timestamp: {snap.get('timestamp', '?')}")

    # Container section
    click.echo()
    click.secho("Container:", fg="cyan", bold=True)
    container = snap.get("container", {})
    if not container:
        click.secho("  (not available)", fg="yellow")
    else:
        version = container.get("version")
        if version:
            click.secho(f"  Version:   {version}", fg="green")
        else:
            click.secho("  Version:   (none)", fg="yellow")

        sif_path = container.get("sif_path")
        if sif_path:
            click.echo(f"  SIF:       {sif_path}")

        sif_sha = container.get("sif_sha256")
        if sif_sha:
            click.echo(f"  SHA256:    {sif_sha[:16]}...")

        def_hash = container.get("def_hash")
        if def_hash:
            click.echo(f"  .def-hash: {def_hash[:16]}...")

    # Host section
    click.echo()
    click.secho("Host Packages:", fg="cyan", bold=True)
    host = snap.get("host", {})
    if not host:
        click.secho("  (not available)", fg="yellow")
    else:
        for pkg_name, info in host.items():
            installed = info.get("installed", False)
            version = info.get("version", "")
            version_display = f" ({version})" if version else ""
            if installed:
                click.secho(f"  {pkg_name}: ", fg="white", nl=False)
                click.secho(f"installed{version_display}", fg="green")
            else:
                click.secho(f"  {pkg_name}: ", fg="white", nl=False)
                click.secho("not installed", fg="red")

    # Dev repos section
    click.echo()
    click.secho("Dev Repos:", fg="cyan", bold=True)
    dev_repos = snap.get("dev_repos", [])
    if not dev_repos:
        click.secho("  (none specified)", fg="yellow")
    else:
        for repo in dev_repos:
            name = repo.get("name", "?")
            path = repo.get("path", "?")
            commit = repo.get("commit", "")
            branch = repo.get("branch", "")
            dirty = repo.get("dirty", False)
            error = repo.get("error", "")

            if error:
                click.secho(f"  {name}: ", fg="white", nl=False)
                click.secho(f"error ({error})", fg="red")
                continue

            commit_display = commit[:9] if commit else "(unknown)"
            branch_display = f"@{branch}" if branch else ""
            dirty_display = click.style(" [dirty]", fg="yellow") if dirty else ""
            click.echo(
                f"  {click.style(name, bold=True)}{branch_display}  "
                f"{commit_display}{dirty_display}"
            )
            click.echo(f"    {path}")

    # Lock files section
    click.echo()
    click.secho("Lock Files:", fg="cyan", bold=True)
    lock_files = snap.get("lock_files", {})
    if not lock_files:
        click.secho("  (none found)", fg="yellow")
    else:
        for lock_name, sha in lock_files.items():
            sha_display = sha[:16] + "..." if sha else "(empty)"
            click.echo(f"  {lock_name}: {sha_display}")


# EOF
