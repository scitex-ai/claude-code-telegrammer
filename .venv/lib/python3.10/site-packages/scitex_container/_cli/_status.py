#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/_cli/_status.py
"""CLI status command — unified dashboard for Apptainer, host packages, Docker."""

from __future__ import annotations

import click


@click.command("show-status")
@click.option(
    "--json", "as_json", is_flag=True, help="Emit machine-readable JSON output."
)
@click.pass_context
def status(ctx, as_json):
    """Show unified status dashboard (Apptainer + host packages + Docker).

    \b
    Example:
      $ scitex-container show-status
      $ scitex-container show-status --json
    """
    ctx.ensure_object(dict)
    if not as_json:
        as_json = bool(ctx.obj.get("as_json"))

    if as_json:
        import json as _json

        click.echo(_json.dumps(_collect_status(), indent=2))
        return

    _show_apptainer_status()
    click.echo()
    _show_host_status()
    click.echo()
    _show_docker_status()


def _collect_status() -> dict:
    """Aggregate status sections into a JSON-serialisable dict."""
    payload: dict = {"apptainer": {}, "host": {}, "docker": {}}

    # Apptainer
    try:
        from pathlib import Path

        from scitex_container.apptainer import (
            find_containers_dir,
            get_active_version,
            list_versions,
        )

        cdir = find_containers_dir()
        active = get_active_version(cdir)
        versions = list_versions(cdir)
        current_link = Path(cdir) / "current.sif"
        mode = None
        if current_link.is_symlink():
            target = current_link.resolve()
            mode = "sandbox" if target.is_dir() else "SIF"
        elif active:
            mode = "SIF"
        payload["apptainer"] = {
            "containers_dir": str(cdir),
            "active": active,
            "mode": mode,
            "versions": versions,
        }
    except FileNotFoundError as exc:
        payload["apptainer"] = {"error": str(exc)}
    except Exception as exc:
        payload["apptainer"] = {"error": str(exc)}

    # Host
    try:
        from scitex_container.host import check_packages

        payload["host"] = check_packages()
    except Exception as exc:
        payload["host"] = {"error": str(exc)}

    # Docker
    docker_payload: dict = {}
    for env in ("dev", "prod"):
        try:
            from scitex_container.docker import status as docker_status

            docker_payload[env] = docker_status(env=env)
        except FileNotFoundError:
            docker_payload[env] = {"error": "no compose file found"}
        except Exception as exc:
            docker_payload[env] = {"error": str(exc)}
    payload["docker"] = docker_payload

    return payload


# ---------------------------------------------------------------------------
# Dashboard section helpers
# ---------------------------------------------------------------------------


def _show_apptainer_status() -> None:
    """Print Apptainer section of the status dashboard."""
    from pathlib import Path

    click.secho("Apptainer:", fg="cyan", bold=True)

    try:
        from scitex_container.apptainer import (
            find_containers_dir,
            get_active_version,
            list_versions,
        )

        cdir = find_containers_dir()
        active = get_active_version(cdir)
        versions = list_versions(cdir)
    except FileNotFoundError:
        click.secho("  No containers directory found.", fg="yellow")
        return
    except Exception as exc:
        click.secho(f"  Error: {exc}", fg="red")
        return

    # Detect mode: check if current.sif points to a directory (sandbox) or file (SIF)
    current_link = Path(cdir) / "current.sif"
    sandboxes = sorted(Path(cdir).glob("*-sandbox"))
    sandbox_dirs = [d for d in sandboxes if d.is_dir()]

    if current_link.is_symlink():
        target = current_link.resolve()
        if target.is_dir():
            click.secho("  Mode:    sandbox", fg="yellow", bold=True)
            click.secho(f"  Active:  {target.name}/", fg="green")
        elif active:
            click.secho("  Mode:    SIF", bold=True)
            click.secho(f"  Active:  scitex-v{active}.sif", fg="green")
        else:
            click.secho("  Active:  none", fg="yellow")
    elif active:
        click.secho("  Mode:    SIF", bold=True)
        click.secho(f"  Active:  scitex-v{active}.sif", fg="green")
    else:
        click.secho("  Active:  none", fg="yellow")

    # Show sandbox directories
    if sandbox_dirs:
        names = [d.name for d in sandbox_dirs]
        click.echo(f"  Sandboxes: {', '.join(names)}")

    # Show SIF versions
    if versions:
        parts = []
        for v in versions:
            label = f"scitex-v{v['version']}"
            if v["active"]:
                parts.append(click.style(label + " (active)", fg="green"))
            else:
                parts.append(label)
        click.echo(f"  SIF versions: {', '.join(parts)}")
    else:
        click.secho("  SIF versions: none built yet", fg="yellow")


def _show_host_status() -> None:
    """Print Host Packages section of the status dashboard."""
    click.secho("Host Packages:", fg="cyan", bold=True)

    try:
        from scitex_container.host import check_packages

        packages = check_packages()
    except Exception as exc:
        click.secho(f"  Error checking packages: {exc}", fg="red")
        return

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


def _show_docker_status() -> None:
    """Print Docker section of the status dashboard."""
    click.secho("Docker:", fg="cyan", bold=True)

    for env in ("dev", "prod"):
        try:
            from scitex_container.docker import status as docker_status

            info = docker_status(env=env)
            containers = info.get("containers", [])
            n = len(containers)
            running = sum(
                1 for c in containers if c.get("state", "").lower() == "running"
            )

            if n == 0:
                click.secho(f"  {env}: ", fg="white", nl=False)
                click.secho("no containers", fg="yellow")
            elif running == n:
                click.secho(f"  {env}: ", fg="white", nl=False)
                click.secho(
                    f"running ({n} container{'s' if n != 1 else ''})", fg="green"
                )
            else:
                click.secho(f"  {env}: ", fg="white", nl=False)
                click.secho(
                    f"{running}/{n} running",
                    fg="yellow" if running > 0 else "red",
                )
        except FileNotFoundError:
            click.secho(f"  {env}: ", fg="white", nl=False)
            click.secho("no compose file found", fg="yellow")
        except Exception as exc:
            click.secho(f"  {env}: ", fg="white", nl=False)
            click.secho(f"error ({exc})", fg="red")


# EOF
