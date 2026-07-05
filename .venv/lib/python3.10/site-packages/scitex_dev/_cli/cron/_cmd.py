#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron`` Click group + subcommand registration."""

from __future__ import annotations

import click

from . import install, list as list_mod, remove, run, status


def register_cron_commands(main_group: click.Group) -> click.Group:
    """Register ``scitex-dev cron`` on the given main group."""

    @main_group.group("cron", invoke_without_command=True)
    @click.pass_context
    def cron(ctx: click.Context) -> None:
        """Ecosystem-wide cron management.

        \b
        Manages a registry of named cron jobs across the SciTeX ecosystem.
        Each managed crontab line is tagged with
            # scitex-dev cron: <name>
        so install / remove operations target only that line and never
        disturb unrelated entries.

        \b
        First registered job: `ci-watch` — polls each sac agent's owned
        repo for CI red on develop and dispatches a fix-forward A2A turn
        to the responsible agent when failures are detected.

        \b
        Verbs:
          list     — show registry + installed lines
          install  — install the named job (idempotent)
          remove   — strip the named job
          status   — last-run / next-run hints
          exec     — execute a job's body (used by cron itself)
        """
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    install.register(cron)
    list_mod.register(cron)
    remove.register(cron)
    status.register(cron)
    run.register(cron)
    return cron


# EOF
