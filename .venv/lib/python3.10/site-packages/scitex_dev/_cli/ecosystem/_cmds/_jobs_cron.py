#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem cron {list,install,uninstall}``.

Federated cron management: aggregates cron-kind ``JobSpec``s from every
ecosystem package (via the ``scitex_dev.jobs`` entry-point group plus
scitex-dev's own built-ins) and materialises them into an idempotent
BEGIN/END managed crontab block.
"""

from __future__ import annotations

import click


def register(ecosystem) -> None:
    @ecosystem.group("cron", invoke_without_command=True)
    @click.pass_context
    def cron(ctx):
        """Federated cron jobs across the SciTeX ecosystem.

        \b
        Aggregates cron-kind jobs from every package registered under the
        `scitex_dev.jobs` entry-point group (plus scitex-dev's built-ins)
        and materialises them into a single idempotent crontab block.

        \b
        Verbs:
          list       — show all discovered cron jobs + source package
          install    — write the managed crontab block (idempotent)
          uninstall  — remove the managed block (or one line)
        """
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @cron.command("list")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def cron_list(as_json):
        """List all discovered cron-kind jobs.

        \b
        Example:
          $ scitex-dev ecosystem cron list
          $ scitex-dev ecosystem cron list --json
        """
        from ....jobs import jobs_of_kind

        jobs = jobs_of_kind("cron")
        if as_json:
            import json

            click.echo(
                json.dumps(
                    [
                        {
                            "name": j.name,
                            "schedule": j.schedule,
                            "description": j.description,
                            "source": _source_of(j.name),
                        }
                        for j in jobs
                    ]
                )
            )
            return
        if not jobs:
            click.echo("No cron-kind jobs discovered.")
            return
        for j in jobs:
            click.echo(f"  {j.name:30s} {j.schedule:16s} [{_source_of(j.name)}]")
            click.echo(f"  {'':30s} {j.description}")

    @cron.command("install")
    @click.option("--name", default=None, help="Install only the named job.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print the managed block that would be written; do not touch crontab.",
    )
    @click.option(
        "-y", "--yes", is_flag=True, default=False, help="Confirm the crontab write."
    )
    def cron_install(name, dry_run, yes):
        """Write the managed crontab block for cron-kind jobs.

        \b
        Idempotent: the block delimited by
            # >>> scitex-dev-ecosystem ... >>>  /  # <<< ... <<<
        is replaced in place — re-running never duplicates lines.

        \b
        Example:
          $ scitex-dev ecosystem cron install --dry-run
          $ scitex-dev ecosystem cron install --yes
          $ scitex-dev ecosystem cron install --name ci-watch --yes
        """
        from ....jobs import jobs_of_kind
        from ....jobs import _cron_block as cb
        from ...cron import _crontab

        jobs = jobs_of_kind("cron")
        if name is not None:
            jobs = [j for j in jobs if j.name == name]
            if not jobs:
                raise click.ClickException(f"no cron-kind job named {name!r}")

        if dry_run:
            click.echo(cb.render_block(jobs))
            return

        if not yes:
            click.echo("Refusing to write to crontab without --yes/-y.", err=True)
            raise SystemExit(2)

        try:
            current = _crontab.read_crontab()
            new = cb.upsert_block(current, jobs)
            _crontab.write_crontab(new)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(f"installed {len(jobs)} cron job(s) into managed block.")

    @cron.command("uninstall")
    @click.option("--name", default=None, help="Remove only the named line.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print the crontab that would result; do not touch crontab.",
    )
    @click.option(
        "-y", "--yes", is_flag=True, default=False, help="Confirm the crontab write."
    )
    def cron_uninstall(name, dry_run, yes):
        """Remove the managed crontab block (or one line).

        \b
        Example:
          $ scitex-dev ecosystem cron uninstall --dry-run
          $ scitex-dev ecosystem cron uninstall --yes
          $ scitex-dev ecosystem cron uninstall --name ci-watch --yes
        """
        from ....jobs import _cron_block as cb
        from ...cron import _crontab

        if dry_run:
            current = _crontab.read_crontab()
            if name is not None:
                new, _ = cb.remove_line(current, name)
            else:
                new = cb.upsert_block(current, [])
            click.echo(new, nl=False)
            return

        if not yes:
            click.echo("Refusing to write to crontab without --yes/-y.", err=True)
            raise SystemExit(2)

        try:
            current = _crontab.read_crontab()
            if name is not None:
                new, removed = cb.remove_line(current, name)
                if removed == 0:
                    raise click.ClickException(f"no managed line named {name!r}")
                _crontab.write_crontab(new)
                click.echo(f"removed managed line {name!r}.")
            else:
                new = cb.upsert_block(current, [])
                _crontab.write_crontab(new)
                click.echo("removed managed cron block.")
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

    @cron.command("exec")
    @click.argument("name")
    @click.option(
        "--apply",
        is_flag=True,
        default=False,
        help=(
            "(deploy-freshness) Repair drift instead of dry-run. WHEEL "
            "leaf (installed version trails latest PyPI): run `pip install "
            "-U <pkg>` + `systemctl --user restart <unit>`. EDITABLE leaf "
            "(PEP 660 install whose git source is newer than the unit's "
            "last start): `systemctl --user restart <unit>` only (no pip)."
        ),
    )
    def cron_exec(name: str, apply: bool) -> None:
        """Execute the body of the federated cron job NAME.

        \b
        Discovers the JobSpec via the `scitex_dev.jobs` entry-point
        federation (the SAME aggregator that `ecosystem cron install`
        uses), then dispatches to the owning module's run_once. This is
        the verb the materialised crontab line invokes; operators can
        also run it interactively to test a job without waiting for
        the next cron tick.

        \b
        Example:
          $ scitex-dev ecosystem cron exec deploy-freshness
          $ scitex-dev ecosystem cron exec deploy-freshness --apply
        """
        from ....jobs import jobs_of_kind

        # Verify the named job is actually in the federation.
        all_cron_jobs = jobs_of_kind("cron")
        names = {j.name for j in all_cron_jobs}
        if name not in names:
            known = ", ".join(sorted(names)) or "(none)"
            raise click.ClickException(
                f"unknown federated cron job: {name!r}. Discovered: {known}"
            )

        if name == "deploy-freshness":
            from ...._ecosystem_jobs import _deploy_freshness

            result = _deploy_freshness.run_once(apply=apply)
            if result.error is not None:
                raise click.ClickException(result.error)
            return

        # Defensive — a JobSpec is discovered but no dispatch branch
        # exists. Means a leaf registered a federated cron job that
        # scitex-dev's ecosystem cron exec doesn't know how to run.
        # That's OK for the OTHER cron-kind jobs leaves declare —
        # they shell out to the leaf's OWN CLI via JobSpec.command,
        # and we never reach this dispatch (the crontab line invokes
        # the leaf's CLI directly, not `ecosystem cron exec`).
        # But if someone DID call `ecosystem cron exec <leaf-job>`,
        # the right thing is to shell out to the JobSpec.command
        # itself rather than crash.
        import shlex
        import subprocess

        spec = next(j for j in all_cron_jobs if j.name == name)
        # Strip the wrapper `mkdir ...; <cmd> >> log 2>&1` if present
        # — the operator's interactive `cron exec` shouldn't double-write.
        # Best-effort: take the last `;`-delimited segment.
        cmd_str = spec.command.split(";")[-1].strip()
        # Drop any trailing `>> log 2>&1` redirect.
        for redir in (" >> ", " > ", " 2>>", " 2>"):
            idx = cmd_str.find(redir)
            if idx > 0:
                cmd_str = cmd_str[:idx].strip()
        argv = shlex.split(cmd_str)
        if not argv:
            raise click.ClickException(
                f"cron job {name!r}: empty command after wrapper strip"
            )
        r = subprocess.run(argv, check=False)
        if r.returncode != 0:
            raise SystemExit(r.returncode)


def _source_of(name: str) -> str:
    """Best-effort source label: package prefix before the first dot."""
    if "." in name:
        return name.split(".", 1)[0]
    return "scitex-dev"


# EOF
