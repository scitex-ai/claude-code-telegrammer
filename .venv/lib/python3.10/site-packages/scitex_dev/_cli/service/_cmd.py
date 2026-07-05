#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev service`` Click group + ``ensure`` subcommand."""

from __future__ import annotations

import click


def register_service_commands(main_group: click.Group) -> click.Group:
    """Register ``scitex-dev service`` on the given main group."""

    @main_group.group("service", invoke_without_command=True)
    @click.pass_context
    def service(ctx: click.Context) -> None:
        """Keep a declared ``kind='service'`` daemon alive, fleet-wide.

        \b
        Leaves declare a long-running daemon as a `kind="service"`
        JobSpec via the `scitex_dev.jobs` entry-point group; scitex-dev
        owns keeping it running. Two backends are chosen automatically:
          * systemd --user   when a user manager is reachable
          * respawn loop      otherwise (keep-alive under
                              ~/.scitex/<pkg>/runtime/)

        \b
        Verbs:
          ensure  — install + start the named service (idempotent)
        """
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    _register_ensure(service)
    return service


def _register_ensure(service: click.Group) -> None:
    @service.command("ensure")
    @click.argument("name")
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Emit the ensure result as structured JSON.",
    )
    @click.option(
        "--respawn",
        "force_respawn",
        is_flag=True,
        default=False,
        help=(
            "Force the respawn-loop backend even if systemd --user is "
            "available (for hosts where the user manager is present but "
            "unwanted for this daemon)."
        ),
    )
    def ensure(name: str, as_json: bool, force_respawn: bool) -> None:
        """Ensure the `kind='service'` daemon NAME is installed AND running.

        \b
        Resolves NAME from the scitex_dev.jobs federation (same lookup
        as `ecosystem systemd`), then:
          * systemd --user available  → write the .service unit,
            daemon-reload, enable --now (idempotent).
          * otherwise                 → write + launch a respawn
            keep-alive loop under ~/.scitex/<pkg>/runtime/.

        \b
        Example:
          $ scitex-dev service ensure sac.listen
          $ scitex-dev service ensure sac.listen --respawn
          $ scitex-dev service ensure sac.listen --json
        """
        from ...jobs._ensure import ensure_service

        avail_fn = (lambda: False) if force_respawn else None
        try:
            result = ensure_service(name, systemd_available_fn=avail_fn)
        except KeyError as exc:
            raise click.ClickException(str(exc)) from exc

        if as_json:
            import json

            click.echo(
                json.dumps(
                    {
                        "name": result.name,
                        "backend": result.backend,
                        "unit_path": (
                            str(result.unit_path) if result.unit_path else None
                        ),
                        "script_path": (
                            str(result.script_path)
                            if result.script_path
                            else None
                        ),
                        "already_running": result.already_running,
                        "messages": list(result.messages),
                    }
                )
            )
            return

        click.echo(f"service ensure {result.name}: backend={result.backend}")
        for msg in result.messages:
            click.echo(f"  {msg}")


__all__ = ["register_service_commands"]


# EOF
