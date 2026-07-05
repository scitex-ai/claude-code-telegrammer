#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem systemd {list,install,uninstall}``.

Generates systemd *user* timer + service unit files under
``~/.config/systemd/user/`` for systemd-kind jobs. We never invoke
``systemctl`` ourselves — install prints the
``systemctl --user enable --now <name>.timer`` hint for the operator.
"""

from __future__ import annotations

from pathlib import Path

import click


def _unit_dir() -> Path:
    """Resolve ``~/.config/systemd/user`` honouring ``$HOME`` (test seam)."""
    return Path.home() / ".config" / "systemd" / "user"


def register(ecosystem) -> None:
    @ecosystem.group("systemd", invoke_without_command=True)
    @click.pass_context
    def systemd(ctx):
        """Federated systemd user timers across the SciTeX ecosystem.

        \b
        Generates `<name>.service` (Type=oneshot) and `<name>.timer`
        (Persistent=true) unit files under ~/.config/systemd/user/ for
        every systemd-kind job. Does NOT run systemctl — prints the
        enable hint instead.

        \b
        Verbs:
          list       — show all discovered systemd jobs + source package
          install    — write unit files (prints `systemctl --user` hint)
          uninstall  — remove the unit files
        """
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @systemd.command("list")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def systemd_list(as_json):
        """List all discovered systemd-kind jobs.

        \b
        Example:
          $ scitex-dev ecosystem systemd list
        """
        from ....jobs import jobs_of_kind

        jobs = jobs_of_kind("timer") + jobs_of_kind("service")
        if as_json:
            import json

            click.echo(
                json.dumps(
                    [
                        {
                            "name": j.name,
                            "on_boot_sec": j.on_boot_sec,
                            "on_unit_active_sec": j.on_unit_active_sec,
                            "schedule": j.schedule,
                            "description": j.description,
                        }
                        for j in jobs
                    ]
                )
            )
            return
        if not jobs:
            click.echo("No systemd-kind jobs discovered.")
            return
        for j in jobs:
            cadence = j.on_unit_active_sec or f"(derived from {j.schedule})"
            click.echo(f"  {j.name:30s} every {cadence}")
            click.echo(f"  {'':30s} {j.description}")

    @systemd.command("install")
    @click.option("--name", default=None, help="Install only the named job.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print the unit files that would be written; do not touch disk.",
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Confirm. Required when not --dry-run.",
    )
    def systemd_install(name, dry_run, yes):
        """Write `<name>.service` + `<name>.timer` for systemd-kind jobs.

        \b
        Example:
          $ scitex-dev ecosystem systemd install --dry-run
          $ scitex-dev ecosystem systemd install --yes
          $ scitex-dev ecosystem systemd install --name sac.accounts-refresh --yes
        """
        from ....jobs import jobs_of_kind
        from ....jobs import _systemd as sd

        jobs = jobs_of_kind("timer") + jobs_of_kind("service")
        if name is not None:
            jobs = [j for j in jobs if j.name == name]
            if not jobs:
                raise click.ClickException(f"no systemd-kind job named {name!r}")
        if not jobs:
            click.echo("No systemd-kind jobs discovered.")
            return

        if not dry_run and not yes:
            click.echo("Refusing to write unit files without --yes/-y.", err=True)
            raise SystemExit(2)

        unit_dir = _unit_dir()
        for j in jobs:
            service_text = sd.build_service_unit(j)
            timer_text = (
                sd.build_timer_unit(j) if j.kind == "timer" else None
            )
            if dry_run:
                click.echo(f"# {j.name}.service")
                click.echo(service_text)
                if timer_text is not None:
                    click.echo(f"# {j.name}.timer")
                    click.echo(timer_text)
                continue
            unit_dir.mkdir(parents=True, exist_ok=True)
            (unit_dir / f"{j.name}.service").write_text(
                service_text, encoding="utf-8"
            )
            click.echo(f"wrote {unit_dir / (j.name + '.service')}")
            if timer_text is not None:
                (unit_dir / f"{j.name}.timer").write_text(
                    timer_text, encoding="utf-8"
                )
                click.echo(f"wrote {unit_dir / (j.name + '.timer')}")

        if not dry_run:
            click.echo("")
            click.echo("Enable with:")
            click.echo("  systemctl --user daemon-reload")
            for j in jobs:
                click.echo(
                    f"  systemctl --user enable --now {sd.systemd_unit_name(j)}"
                )

    @systemd.command("uninstall")
    @click.option("--name", default=None, help="Remove only the named job's units.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print which unit files would be removed; do not touch disk.",
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Confirm. Required when not --dry-run.",
    )
    def systemd_uninstall(name, dry_run, yes):
        """Remove `<name>.service` + `<name>.timer` unit files.

        \b
        Example:
          $ scitex-dev ecosystem systemd uninstall --dry-run
          $ scitex-dev ecosystem systemd uninstall --yes
          $ scitex-dev ecosystem systemd uninstall --name sac.accounts-refresh --yes
        """
        from ....jobs import jobs_of_kind

        jobs = jobs_of_kind("timer") + jobs_of_kind("service")
        if name is not None:
            jobs = [j for j in jobs if j.name == name]
            if not jobs:
                raise click.ClickException(f"no systemd-kind job named {name!r}")

        unit_dir = _unit_dir()

        if dry_run:
            for j in jobs:
                for suffix in (".service", ".timer"):
                    path = unit_dir / f"{j.name}{suffix}"
                    if path.exists():
                        click.echo(f"would remove {path}")
            return

        if not yes:
            click.echo("Refusing to remove unit files without --yes/-y.", err=True)
            raise SystemExit(2)

        removed = 0
        for j in jobs:
            for suffix in (".service", ".timer"):
                path = unit_dir / f"{j.name}{suffix}"
                if path.exists():
                    path.unlink()
                    removed += 1
                    click.echo(f"removed {path}")
        if removed == 0:
            click.echo("No unit files found to remove.")
        else:
            click.echo("")
            click.echo("Run: systemctl --user daemon-reload")


# EOF
