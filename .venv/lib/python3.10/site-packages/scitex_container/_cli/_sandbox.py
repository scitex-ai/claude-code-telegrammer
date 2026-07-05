#!/usr/bin/env python3
# File: src/scitex_container/_cli/_sandbox.py
"""CLI sandbox sub-group for Apptainer sandbox management."""

from __future__ import annotations

import click


@click.group()
def sandbox():
    """Manage Apptainer sandbox directories."""


@sandbox.command(name="create")
@click.option(
    "--source", "-s", "source_path", type=click.Path(), help="Source .sif or .def file."
)
@click.option(
    "--dir", "-d", "containers_dir", type=click.Path(), help="Containers directory."
)
@click.option(
    "--output", "-o", "output_dir", type=click.Path(), help="Explicit output directory."
)
@click.option(
    "--dry-run", is_flag=True, help="Print the planned action without executing."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Skip interactive confirmation prompts."
)
def sandbox_create(source_path, containers_dir, output_dir, dry_run, yes):
    """Build a sandbox from a SIF image or .def file (timestamped).

    \b
    Example:
      $ scitex-container sandbox create -s ./scitex.sif
      $ scitex-container sandbox create -s ./scitex.def -o ./containers
      $ scitex-container sandbox create -s ./scitex.sif --dry-run
    """
    if dry_run:
        click.echo(
            f"[dry-run] would create sandbox from source={source_path} "
            f"dir={containers_dir or '<auto>'} output={output_dir or '<auto>'}"
        )
        return
    _ = yes
    from pathlib import Path

    from scitex_container.apptainer import sandbox_create as do_create

    if not source_path:
        click.secho("Error: --source/-s is required.", fg="red", err=True)
        raise SystemExit(1)

    try:
        result = do_create(
            source=Path(source_path),
            containers_dir=Path(containers_dir) if containers_dir else None,
            output_dir=Path(output_dir) if output_dir else None,
        )
        click.secho(f"Sandbox created: {result}", fg="green")
    except FileNotFoundError as exc:
        click.secho(str(exc), fg="red", err=True)
        raise SystemExit(1)
    except RuntimeError as exc:
        click.secho(f"Sandbox creation failed: {exc}", fg="red", err=True)
        raise SystemExit(1)


@sandbox.command(name="maintain")
@click.argument("command", nargs=-1, required=True)
@click.option("--sandbox-dir", "-s", type=click.Path(), help="Sandbox directory path.")
def sandbox_maintain(command, sandbox_dir):
    """Run a maintenance COMMAND inside a sandbox (writable + fakeroot).

    \b
    Example:
      $ scitex-container sandbox maintain -s ./scitex-sandbox apt-get update
      $ scitex-container sandbox maintain -s ./scitex-sandbox pip install foo
    """
    from pathlib import Path

    from scitex_container.apptainer import sandbox_maintain as do_maintain

    if not sandbox_dir:
        click.secho("Error: --sandbox-dir/-s is required.", fg="red", err=True)
        raise SystemExit(1)

    try:
        rc = do_maintain(sandbox_dir=Path(sandbox_dir), command=list(command))
        if rc != 0:
            click.secho(f"Command exited with code {rc}", fg="yellow", err=True)
            raise SystemExit(rc)
        click.secho("Maintenance command completed.", fg="green")
    except FileNotFoundError as exc:
        click.secho(str(exc), fg="red", err=True)
        raise SystemExit(1)


@sandbox.command(name="list")
@click.option(
    "--dir", "-d", "containers_dir", type=click.Path(), help="Containers directory."
)
@click.option(
    "--json", "as_json", is_flag=True, help="Emit machine-readable JSON output."
)
@click.pass_context
def sandbox_list(ctx, containers_dir, as_json):
    """List versioned sandbox directories.

    \b
    Example:
      $ scitex-container sandbox list
      $ scitex-container sandbox list --json
      $ scitex-container sandbox list -d ./containers
    """
    import json as _json
    from pathlib import Path

    from scitex_container.apptainer import get_active_sandbox, list_sandboxes

    ctx.ensure_object(dict)
    if not as_json:
        as_json = bool(ctx.obj.get("as_json"))

    cdir = Path(containers_dir) if containers_dir else Path.cwd()
    sandboxes = list_sandboxes(cdir)
    active = get_active_sandbox(cdir)

    if as_json:
        click.echo(
            _json.dumps(
                {
                    "containers_dir": str(cdir),
                    "active": active,
                    "sandboxes": sandboxes,
                },
                indent=2,
            )
        )
        return

    if not sandboxes:
        click.echo(f"No versioned sandboxes found in {cdir}")
        return

    click.secho(f"Sandboxes in {cdir}:", fg="cyan")
    for sb in sandboxes:
        marker = click.style(" *", fg="green") if sb["active"] else "  "
        ver = click.style(sb["version"], fg="green" if sb["active"] else "white")
        click.echo(f"  {marker} {ver}  {sb['date']}")

    if active:
        click.echo()
        click.echo(f"  Active: {click.style(active, fg='green', bold=True)}")


@sandbox.command(name="switch")
@click.argument("version")
@click.option(
    "--dir", "-d", "containers_dir", type=click.Path(), help="Containers directory."
)
@click.option("--sudo", "use_sudo", is_flag=True, help="Use sudo for symlinks.")
def sandbox_switch(version, containers_dir, use_sudo):
    """Switch active sandbox to VERSION (timestamp).

    \b
    Example:
      $ scitex-container sandbox switch 20260301T120000
      $ scitex-container sandbox switch 20260301T120000 --sudo
    """
    from pathlib import Path

    from scitex_container.apptainer import get_active_sandbox, switch_sandbox

    cdir = Path(containers_dir) if containers_dir else Path.cwd()
    old = get_active_sandbox(cdir)

    try:
        switch_sandbox(version, cdir, use_sudo=use_sudo)
    except FileNotFoundError as exc:
        click.secho(str(exc), fg="red", err=True)
        raise SystemExit(1)
    except RuntimeError as exc:
        click.secho(f"Switch failed: {exc}", fg="red", err=True)
        raise SystemExit(1)

    if old:
        click.secho(f"Switched sandbox {old} -> {version}", fg="green")
    else:
        click.secho(f"Activated sandbox {version}", fg="green")


@sandbox.command(name="rollback")
@click.option(
    "--dir", "-d", "containers_dir", type=click.Path(), help="Containers directory."
)
@click.option("--sudo", "use_sudo", is_flag=True, help="Use sudo for symlinks.")
@click.option(
    "--dry-run", is_flag=True, help="Print the planned action without executing."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Skip interactive confirmation prompts."
)
def sandbox_rollback(containers_dir, use_sudo, dry_run, yes):
    """Revert to the previous sandbox version.

    \b
    Example:
      $ scitex-container sandbox rollback
      $ scitex-container sandbox rollback --sudo
      $ scitex-container sandbox rollback --dry-run
    """
    if dry_run:
        click.echo(
            f"[dry-run] would rollback sandbox in dir={containers_dir or '<cwd>'} "
            f"sudo={use_sudo}"
        )
        return
    _ = yes
    from pathlib import Path

    from scitex_container.apptainer import get_active_sandbox, rollback_sandbox

    cdir = Path(containers_dir) if containers_dir else Path.cwd()
    old = get_active_sandbox(cdir)

    try:
        new_ver = rollback_sandbox(cdir, use_sudo=use_sudo)
    except RuntimeError as exc:
        click.secho(f"Rollback failed: {exc}", fg="red", err=True)
        raise SystemExit(1)

    click.secho(f"Rolled back sandbox {old} -> {new_ver}", fg="green")


@sandbox.command(
    name="cleanup",
    hidden=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.pass_context
def sandbox_cleanup_deprecated(ctx):
    """(deprecated) Renamed to `clean`."""
    click.echo(
        "error: `scitex-container sandbox cleanup` was renamed to "
        "`scitex-container sandbox clean`.\n"
        "Re-run with: scitex-container sandbox clean [...]",
        err=True,
    )
    ctx.exit(2)


@sandbox.command(name="clean")
@click.option(
    "--keep",
    "-k",
    type=int,
    default=5,
    show_default=True,
    help="Number of recent sandboxes to keep.",
)
@click.option(
    "--dir", "-d", "containers_dir", type=click.Path(), help="Containers directory."
)
@click.option(
    "--dry-run", is_flag=True, help="Print the planned action without executing."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Skip interactive confirmation prompts."
)
def sandbox_cleanup(keep, containers_dir, dry_run, yes):
    """Remove old sandbox directories, keeping the N most recent.

    \b
    Example:
      $ scitex-container sandbox clean
      $ scitex-container sandbox clean --keep 3
      $ scitex-container sandbox clean --dry-run
    """
    if dry_run:
        click.echo(
            f"[dry-run] would clean sandboxes in dir={containers_dir or '<cwd>'} "
            f"keep={keep}"
        )
        return
    _ = yes
    from pathlib import Path

    from scitex_container.apptainer import cleanup_sandboxes

    cdir = Path(containers_dir) if containers_dir else Path.cwd()
    removed = cleanup_sandboxes(cdir, keep=keep)

    if removed:
        click.secho(f"Removed {len(removed)} old sandbox(es):", fg="yellow")
        for path in removed:
            click.echo(f"  {path.name}")
    else:
        click.secho("No old sandboxes to remove.", fg="green")


@sandbox.command(name="update")
@click.option("--sandbox-dir", "-s", type=click.Path(), help="Sandbox directory path.")
@click.option(
    "--proj-root",
    "-r",
    type=click.Path(),
    help="Project root containing repos (default: ~/proj).",
)
@click.option("--pkg", "-p", "package", type=str, help="Update only this package.")
@click.option("--deps", is_flag=True, help="Install dependencies too (slower).")
@click.option(
    "--dry-run", is_flag=True, help="Print the planned action without executing."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Skip interactive confirmation prompts."
)
def sandbox_update(sandbox_dir, proj_root, package, deps, dry_run, yes):
    """Incrementally update ecosystem packages in the sandbox (fast).

    \b
    Example:
      $ scitex-container sandbox update -s ./scitex-sandbox
      $ scitex-container sandbox update -s ./scitex-sandbox -p scitex-io
      $ scitex-container sandbox update -s ./scitex-sandbox --deps
    """
    if dry_run:
        click.echo(
            f"[dry-run] would update sandbox={sandbox_dir} "
            f"proj_root={proj_root or '<auto>'} package={package or '<all>'} "
            f"deps={deps}"
        )
        return
    _ = yes
    from pathlib import Path

    from scitex_container.apptainer import sandbox_update as do_update

    if not sandbox_dir:
        click.secho("Error: --sandbox-dir/-s is required.", fg="red", err=True)
        raise SystemExit(1)

    packages = (package,) if package else None

    try:
        results = do_update(
            sandbox_dir=Path(sandbox_dir),
            proj_root=Path(proj_root) if proj_root else None,
            packages=packages,
            install_deps=deps,
        )
    except FileNotFoundError as exc:
        click.secho(str(exc), fg="red", err=True)
        raise SystemExit(1)

    ok = sum(1 for v in results.values() if v == "ok")
    failed = sum(1 for v in results.values() if v == "failed")
    skipped = sum(1 for v in results.values() if v == "skipped")

    for pkg, status in results.items():
        color = {"ok": "green", "failed": "red", "skipped": "yellow"}[status]
        click.secho(f"  {status.upper():7s} {pkg}", fg=color)

    click.echo()
    if failed:
        click.secho(f"Done: {ok} ok, {failed} failed, {skipped} skipped", fg="yellow")
        click.echo("Tip: use --deps if packages have new dependencies")
        raise SystemExit(1)
    else:
        click.secho(f"Done: {ok} ok, {skipped} skipped", fg="green")


@sandbox.command(name="configure-ps1")
@click.option("--sandbox-dir", "-s", type=click.Path(), help="Sandbox directory path.")
@click.option("--ps1", default=r"\W $ ", show_default=True, help="PS1 prompt string.")
def sandbox_configure_ps1(sandbox_dir, ps1):
    r"""Configure PS1 prompt in a sandbox (default: \\W $ ).

    \b
    Example:
      $ scitex-container sandbox configure-ps1 -s ./scitex-sandbox
      $ scitex-container sandbox configure-ps1 -s ./scitex-sandbox --ps1 "[scitex] $ "
    """
    from pathlib import Path

    from scitex_container.apptainer import sandbox_configure_ps1 as do_configure

    if not sandbox_dir:
        click.secho("Error: --sandbox-dir/-s is required.", fg="red", err=True)
        raise SystemExit(1)

    do_configure(sandbox_dir=Path(sandbox_dir), ps1=ps1)
    click.secho(f"PS1 configured: {ps1}", fg="green")


@sandbox.command(name="purge-sifs")
@click.option(
    "--dir", "-d", "containers_dir", type=click.Path(), help="Containers directory."
)
@click.option(
    "--keep",
    "-k",
    type=int,
    default=0,
    show_default=True,
    help="Number of versioned SIFs to keep.",
)
@click.option(
    "--dry-run", is_flag=True, help="Print the planned action without executing."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Skip interactive confirmation prompts."
)
def sandbox_purge_sifs(containers_dir, keep, dry_run, yes):
    """Remove SIF files and related artifacts (*.sif, *.sif.old, *.sif.backup.*).

    \b
    Example:
      $ scitex-container sandbox purge-sifs
      $ scitex-container sandbox purge-sifs --keep 2
      $ scitex-container sandbox purge-sifs --dry-run
    """
    if dry_run:
        click.echo(
            f"[dry-run] would purge SIFs in dir={containers_dir or '<cwd>'} keep={keep}"
        )
        return
    _ = yes
    from pathlib import Path

    from scitex_container.apptainer import cleanup_sifs

    cdir = Path(containers_dir) if containers_dir else Path.cwd()
    removed = cleanup_sifs(cdir, keep=keep)

    if removed:
        click.secho(f"Removed {len(removed)} SIF file(s):", fg="yellow")
        for path in removed:
            click.echo(f"  {path.name}")
    else:
        click.secho("No SIF files to remove.", fg="green")


# EOF
