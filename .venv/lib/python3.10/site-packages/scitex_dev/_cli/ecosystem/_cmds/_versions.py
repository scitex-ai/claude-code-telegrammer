#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `check-versions`, `fix-mismatches` (+ deprecated `packages` alias)."""

import json

import click


def register(ecosystem):
    @ecosystem.command("check-versions")
    @click.option(
        "--host",
        "-h",
        "hosts",
        multiple=True,
        help="Host name(s). Default: all enabled hosts.",
    )
    @click.option(
        "--package",
        "-p",
        "packages",
        multiple=True,
        help="Package name(s). Default: all.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Mode 2: print commands that would run on out-of-sync hosts.",
    )
    @click.option(
        "--apply",
        "do_apply",
        is_flag=True,
        help="Mode 3: actually execute the sync. Mutually exclusive with --dry-run.",
    )
    @click.option(
        "--unsafe",
        is_flag=True,
        help="Skip ahead-check; allow clobbering remote unpushed commits.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.pass_context
    def ecosystem_packages(ctx, hosts, packages, dry_run, do_apply, unsafe, as_json):
        """Audit ecosystem package versions across hosts (3 modes).

        \b
        Example:
            $ scitex-dev ecosystem check-versions                  # observe
            $ scitex-dev ecosystem check-versions --dry-run        # preview sync
            $ scitex-dev ecosystem check-versions --apply          # execute sync
        """
        if dry_run and do_apply:
            click.echo("error: --dry-run and --apply are mutually exclusive", err=True)
            ctx.exit(2)

        from ...._ecosystem._packages import packages_audit

        host_list = list(hosts) if hosts else None
        pkg_list = list(packages) if packages else None
        if host_list == ["all"]:
            host_list = None

        if do_apply:
            mode = "apply"
        elif dry_run:
            mode = "dry-run"
        else:
            mode = "observe"

        result = packages_audit(
            mode=mode, hosts=host_list, packages=pkg_list, unsafe=unsafe
        )

        if as_json:
            # Drop the rendered table from JSON; "state" is the structured form.
            payload = {k: v for k, v in result.items() if k != "table"}
            click.echo(json.dumps(payload, indent=2, default=str))
        else:
            if mode == "observe":
                click.echo(result["table"])
                summ = result["summary"]
                click.echo()
                click.echo(f"{summ['matching']}/{summ['total']} cells up-to-date")
                if summ["needing_sync"]:
                    click.echo("needing sync:")
                    for n in summ["needing_sync"]:
                        click.echo(f"  - {n['host']}: {n['pkg']}")
            elif mode == "dry-run":
                cmds = result["commands"]
                if not cmds:
                    click.echo("# everything in sync — no commands to preview")
                for host, pkgs_ in cmds.items():
                    for pkg, lines in pkgs_.items():
                        click.echo(f"# {host} :: {pkg}")
                        for line in lines:
                            click.echo(f"  {line}")
            else:  # apply
                click.echo(json.dumps(result, indent=2, default=str))

        # Exit code: observe returns 1 if anything mismatches (or unknown).
        if mode == "observe":
            summ = result["summary"]
            ctx.exit(
                0 if summ["matching"] == summ["total"] and summ["total"] > 0 else 1
            )
        ctx.exit(0)

    # Deprecated alias for the §1 noun-verb fix (packages → check-versions).
    # Removed in 0.11.0.
    @ecosystem.command(
        "packages",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def _ecosystem_packages_deprecated(ctx):
        """(deprecated) Use `ecosystem check-versions`. Removed in 0.11.0."""
        click.echo(
            "warning: `ecosystem packages` was renamed to `ecosystem check-versions`.",
            err=True,
        )
        target = ecosystem.get_command(ctx, "check-versions")
        if target is None:
            ctx.exit(2)
        ctx.invoke(target, *ctx.args)

    @ecosystem.command("fix-mismatches", hidden=True)
    @click.option(
        "--confirm", is_flag=True, help="Apply fixes (default: preview only)."
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.pass_context
    def ecosystem_fix_mismatches(ctx, confirm, as_json):
        """(deprecated) Renamed to `packages`. Forwards to `packages [--apply]`."""
        click.echo(
            "warning: `ecosystem fix-mismatches` is deprecated; "
            "use `ecosystem packages` (or `packages --apply` to execute).",
            err=True,
        )
        from .... import fix_mismatches
        from ..._utils import wrap_as_cli

        wrap_as_cli(fix_mismatches, as_json=as_json, confirm=confirm)
