#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/_cli/_host.py
"""CLI host sub-group for host package management."""

from __future__ import annotations

import click


@click.group()
def host():
    """Manage host-side packages and mount configuration."""


@host.command(name="install")
@click.option("--texlive", is_flag=True, help="Install TeXLive.")
@click.option("--imagemagick", is_flag=True, help="Install ImageMagick.")
@click.option(
    "--all", "install_all", is_flag=True, default=False, help="Install all packages."
)
@click.option(
    "--dry-run", is_flag=True, help="Print the planned action without executing."
)
@click.option(
    "-y", "--yes", is_flag=True, help="Skip interactive confirmation prompts."
)
def host_install(texlive, imagemagick, install_all, dry_run, yes):
    """Install host packages required by SciTeX containers (requires sudo).

    \b
    Example:
      $ scitex-container host install
      $ scitex-container host install --texlive
      $ scitex-container host install --all --dry-run
    """
    if dry_run:
        # If no specific flag, default to all (mirrors live behaviour).
        if not texlive and not imagemagick:
            install_all = True
        click.echo(
            f"[dry-run] would install host packages "
            f"texlive={texlive} imagemagick={imagemagick} all={install_all}"
        )
        return
    _ = yes  # accepted for parity; install_packages may prompt via sudo
    from scitex_container.host import install_packages

    # Default to all when no specific flag given
    if not texlive and not imagemagick:
        install_all = True

    click.secho("Installing host packages (requires sudo)...", fg="cyan")

    try:
        result = install_packages(
            texlive=texlive,
            imagemagick=imagemagick,
            all=install_all,
        )
    except FileNotFoundError as exc:
        click.secho(str(exc), fg="red", err=True)
        raise SystemExit(1)

    for pkg, info in result.items():
        if pkg == "script":
            continue
        status_str = info.get("status", "unknown")
        if status_str == "installed":
            click.secho(f"  {pkg}: {status_str}", fg="green")
        elif status_str == "failed":
            click.secho(f"  {pkg}: {status_str}", fg="red")
        else:
            click.secho(f"  {pkg}: {status_str}", fg="yellow")


@host.command(name="check")
def host_check():
    """Check which host packages are installed.

    \b
    Example:
      $ scitex-container host check
    """
    from scitex_container.host import check_packages

    packages = check_packages()

    click.secho("Host Packages:", fg="cyan", bold=True)
    for pkg_name, info in packages.items():
        if info["installed"]:
            binaries = ", ".join(info.get("binaries", []))
            version_str = info.get("version", "")
            version_display = f" ({version_str})" if version_str else ""
            click.secho(f"  {pkg_name}: ", fg="white", nl=False)
            click.secho(f"installed{version_display}", fg="green", nl=False)
            click.echo(f"  [{binaries}]")
        else:
            click.secho(f"  {pkg_name}: ", fg="white", nl=False)
            click.secho("not installed", fg="red")
            click.secho(
                f"    Tip: run 'scitex-container host install --{pkg_name}' to install.",
                fg="yellow",
            )


@host.command(
    name="mounts",
    hidden=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.pass_context
def host_mounts_deprecated(ctx):
    """(deprecated) Renamed to `show-mounts`."""
    click.echo(
        "error: `scitex-container host mounts` was renamed to "
        "`scitex-container host show-mounts`.\n"
        "Re-run with: scitex-container host show-mounts [...]",
        err=True,
    )
    ctx.exit(2)


@host.command(name="show-mounts")
@click.option(
    "--texlive-prefix",
    default="/usr",
    show_default=True,
    help="TeXLive installation prefix.",
)
@click.option(
    "--json", "as_json", is_flag=True, help="Emit machine-readable JSON output."
)
@click.pass_context
def host_mounts(ctx, texlive_prefix, as_json):
    """Show bind mount configuration for host packages.

    \b
    Example:
      $ scitex-container host show-mounts
      $ scitex-container host show-mounts --json
      $ scitex-container host show-mounts --texlive-prefix /opt/texlive
    """
    import json as _json

    from scitex_container.host import get_mount_config

    ctx.ensure_object(dict)
    if not as_json:
        as_json = bool(ctx.obj.get("as_json"))

    config = get_mount_config(texlive_prefix=texlive_prefix)
    mounts = config.get("mounts", [])

    if as_json:
        click.echo(_json.dumps(config, indent=2))
        return

    if not mounts:
        click.secho("No host mounts configured.", fg="yellow")
        return

    click.secho(f"Host bind mounts ({len(mounts)} total):", fg="cyan", bold=True)
    for m in mounts:
        click.echo(f"  {m['host']} -> {m['container']}  [{m['mode']}]")

    path_additions = config.get("path_additions", [])
    if path_additions:
        click.echo()
        click.secho("PATH additions:", fg="cyan")
        for p in path_additions:
            click.echo(f"  {p}")


# EOF
