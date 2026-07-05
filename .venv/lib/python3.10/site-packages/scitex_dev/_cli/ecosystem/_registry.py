#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI commands for ecosystem management -- registered on main CLI group.

Thin orchestrator. The previously-monolithic command callbacks were split
out into per-area modules under ``_cmds/`` to stay under the line-limit
hook; see ``GITIGNORED/REFACTORING.md`` (2026-05-16 entry). The public
entry point ``register_ecosystem_commands(main_group)`` and the
``scitex_dev._cli.ecosystem._registry`` import path are preserved exactly
so external callers keep working.
"""

import click

from ..._ecosystem.click_helpers import make_categorized_group
from ._categories import ECOSYSTEM_COMMAND_CATEGORIES
from ._cmds import (
    _audit_all,
    _audit_per_target,
    _audit_summary,
    _branch_protection,
    _ci_template,
    _clean,
    _dashboard,
    _git,
    _install_gate,
    _jobs_cron,
    _jobs_systemd,
    _list,
    _up,
    _prune_merged,
    _regen_umbrella,
    _run,
    _status,
    _sync,
    _sync_status,
    _system_deps,
    _test_remote,
    _versions,
)


def register_ecosystem_commands(main_group):
    """Register ecosystem command group on the main CLI.

    Returns the ``ecosystem`` Click group so additional subcommands
    (stats, audit-frontmatter, audit-docs, audit-lines, audit-scope)
    can be registered on it from outside this module.
    """

    @main_group.group(
        invoke_without_command=True,
        cls=make_categorized_group(ECOSYSTEM_COMMAND_CATEGORIES),
    )
    @click.option(
        "--help-recursive", is_flag=True, help="Show help for all subcommands."
    )
    @click.pass_context
    def ecosystem(ctx, help_recursive):
        """Manage the SciTeX ecosystem (versions, sync, audits, stats)."""
        if help_recursive:
            _print_ecosystem_help_recursive(ctx)
            ctx.exit(0)
        elif ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    def _print_ecosystem_help_recursive(ctx):
        fake_parent = click.Context(click.Group(), info_name="scitex-dev")
        parent_ctx = click.Context(ecosystem, info_name="ecosystem", parent=fake_parent)

        click.secho("=== scitex-dev ecosystem ===", fg="cyan", bold=True)
        click.echo(ecosystem.get_help(parent_ctx))

        for name in sorted(ecosystem.list_commands(ctx) or []):
            cmd = ecosystem.get_command(ctx, name)
            if cmd is None:
                continue
            click.echo()
            click.secho(f"=== scitex-dev ecosystem {name} ===", fg="cyan", bold=True)
            with click.Context(cmd, info_name=name, parent=parent_ctx) as sub_ctx:
                click.echo(cmd.get_help(sub_ctx))

    # Per-area command modules. Order is mostly stylistic, but
    # `_dashboard` MUST register the deprecated `dashboard` Click
    # command BEFORE the live `dashboard` Group so the Group wins on
    # name collision (Click later-wins). The module enforces that
    # internal ordering.
    _list.register(ecosystem)
    _versions.register(ecosystem)
    _git.register(ecosystem)
    _audit_per_target.register(ecosystem)
    _audit_summary.register(ecosystem)
    _dashboard.register(ecosystem)
    _audit_all.register(ecosystem)
    _clean.register(ecosystem)
    _install_gate.register(ecosystem)
    _test_remote.register(ecosystem)
    _sync_status.register(ecosystem)
    _sync.register(ecosystem)
    _system_deps.register(ecosystem)
    _prune_merged.register(ecosystem)
    _branch_protection.register(ecosystem)
    _ci_template.register(ecosystem)
    _regen_umbrella.register(ecosystem)

    # Federated scheduled-job aggregation (scitex_dev.jobs entry-points).
    # `ecosystem systemd` handles BOTH long-running services
    # (kind="service") and periodic timers (kind="timer") since the
    # service|timer|cron taxonomy refactor; the prior `ecosystem
    # daemon` subcommand was removed as a duplicate surface.
    _jobs_cron.register(ecosystem)
    _jobs_systemd.register(ecosystem)

    # Headline ecosystem-up one-shot. Post-2026-06-14 redesign: writes
    # the ONE collective `scitex-dev-ecosystem.service` (supervisor
    # unit) + the merged crontab block (cron-native + timer-lowered).
    # See `_up`'s docstring for the operator policy.
    _up.register(ecosystem)

    # Collective supervisor — `ecosystem run` is the systemd ExecStart;
    # `ecosystem status` reads the supervisor's state snapshot.
    _run.register(ecosystem)
    _status.register(ecosystem)

    return ecosystem
