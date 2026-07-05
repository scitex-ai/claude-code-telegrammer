#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/gate/_cmd.py
"""``scitex-dev gate`` — run the aggregated submission gate for a workdir.

The cohort pre-submission hook calls::

    scitex-dev gate --stage=pre-submission <capsule-workdir> --json

and blocks the submit on exit code 2 (a check failed AND is enforced in
``.scitex/dev/config.yaml``), rendering each finding's ``fix_hint`` to the
solver. Exit 0 = pass or advisory-only failures. Exit 1 = usage error.
"""

from __future__ import annotations

import click


def register_gate_command(main_group: click.Group) -> None:
    """Register ``scitex-dev gate`` on the given main group."""

    @main_group.command("gate")
    @click.argument("workdir", type=click.Path(), required=False)
    @click.option(
        "--stage",
        type=click.Choice(["pre-submission", "post-submission"]),
        default="pre-submission",
        show_default=True,
        help="Which submission stage's checks to run.",
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Emit the full report as JSON (for hook consumption).",
    )
    @click.option(
        "--list",
        "list_only",
        is_flag=True,
        default=False,
        help="List the registered checks for the stage and exit 0 (no run).",
    )
    def gate(workdir: str, stage: str, as_json: bool, list_only: bool) -> None:
        """Aggregate per-package submission checks for WORKDIR at STAGE.

        \b
        Checks are contributed by packages via the `scitex_dev.gate.checks`
        entry-point group; a failed check BLOCKS (exit 2) only when its id
        is under `gate.enforce` in `.scitex/dev/config.yaml` (warn-default).

        \b
        Example:
          $ scitex-dev gate --stage=pre-submission ./capsule-007 --json
        """
        import json as _json

        from ...gate import discover_gate_checks, report_to_dict, run_gate

        if list_only:
            checks = discover_gate_checks(stage)
            if as_json:
                click.echo(
                    _json.dumps(
                        [
                            {
                                "id": c.id,
                                "stage": c.stage,
                                "requires": c.requires,
                                "description": c.description,
                            }
                            for c in checks
                        ]
                    )
                )
            else:
                if not checks:
                    click.echo(f"(no gate checks registered for stage {stage!r})")
                for c in checks:
                    click.echo(f"{c.id}  [{c.stage}]  {c.description}")
            raise SystemExit(0)

        if not workdir:
            raise click.UsageError("WORKDIR is required unless --list is given.")

        report = run_gate(workdir, stage)

        if as_json:
            click.echo(_json.dumps(report_to_dict(report)))
            raise SystemExit(2 if report.blocking else 0)

        _render_human(report)
        raise SystemExit(2 if report.blocking else 0)

    return None


def _render_human(report) -> None:
    """Human-readable gate report to stdout/stderr."""
    header = (
        f"gate [{report.stage}] {report.workdir}: "
        f"{'BLOCK' if report.blocking else 'PASS'}"
    )
    click.secho(header, fg="red" if report.blocking else "green", bold=True)
    for o in report.outcomes:
        if not o.ran:
            click.echo(f"  - {o.id}: skipped ({o.skipped_reason})")
            continue
        tag = "BLOCK" if o.blocked else ("fail" if o.passed is False else "ok")
        enforce = " [enforced]" if o.enforced else ""
        click.echo(f"  - {o.id}: {tag}{enforce}")
        for f in o.findings:
            click.echo(f"      {f.severity}: {f.message}")
            if f.fix_hint:
                click.echo(f"      fix: {f.fix_hint}")


__all__ = ["register_gate_command"]
