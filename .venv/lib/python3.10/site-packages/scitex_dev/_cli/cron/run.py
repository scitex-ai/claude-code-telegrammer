#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron exec <name>`` — execute a managed job's body.

This is the entry point the materialised crontab line invokes — it
delegates to the job-specific implementation module (e.g.
``_ci_watch.run_once`` for ``ci-watch``). Adding a new job means
implementing its exec-body here in addition to registering it in
``_jobs.JOB_REGISTRY``.

Verb choice: ``exec`` rather than ``run`` because the CLI audit (§1c)
intentionally treats ``run`` as a noun-only token — the canonical
verbs for "execute this thing" are ``exec`` / ``execute`` / ``start-run``.
"""

from __future__ import annotations

import click

from . import (
    _ci_watch,
    _cred_distribute,
    _quota_keepalive,
    _spartan_conn_monitor,
    _task_harvest,
    _worktree_gc,
)
from ._jobs import JOB_REGISTRY


def register(group: click.Group) -> None:
    @group.command("exec")
    @click.argument("name")
    @click.option(
        "--only",
        "only",
        default=None,
        help="(ci-watch) Restrict the pass to a single agent name.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="(ci-watch) Print the prompt that would be dispatched without "
        "calling `sac agents send`.",
    )
    def exec_cmd(name: str, only: str | None, dry_run: bool) -> None:
        """Execute the body of the managed job NAME.

        \b
        This is the verb the materialised crontab line invokes — operators
        can also run it interactively to test a job without waiting for
        the next cron tick.

        \b
        Example:
          $ scitex-dev cron exec ci-watch
          $ scitex-dev cron exec ci-watch --dry-run
          $ scitex-dev cron exec ci-watch --only proj-scitex-stats --dry-run
        """
        if name not in JOB_REGISTRY:
            known = ", ".join(sorted(JOB_REGISTRY)) or "(none)"
            raise click.ClickException(
                f"unknown cron job: {name!r}. Known jobs: {known}"
            )

        if name == "ci-watch":
            results = _ci_watch.run_once(
                only_agent=only,
                dry_run=dry_run,
            )
            errors = sum(1 for r in results if r.error is not None)
            if errors:
                # Don't crash the cron loop on a transient gh hiccup —
                # just exit non-zero so the log records the failure.
                raise SystemExit(1)
            return

        if name == "quota-keepalive":
            # Self-gating keepalive — fires only when the 2.5-hour interval
            # has elapsed (see _quota_keepalive.run_once). A keepalive miss
            # is recoverable (the next 30-min tick retries), so we always
            # exit 0 here: the log records any error but the cron loop must
            # not be marked failed for a transient `claude` hiccup.
            _quota_keepalive.run_once()
            return

        if name == "worktree-gc":
            # Best-effort cleanup loop — a per-worktree git error must
            # not crash the cron. The structured result captures every
            # decision; we exit non-zero only if the WHOLE pass failed
            # (no roots discoverable, etc.) so a clean log distinguishes
            # "ran, removed N, refused M" from "couldn't run at all".
            result = _worktree_gc.run_once(dry_run=dry_run)
            if result.error is not None:
                raise SystemExit(1)
            return

        if name == "task-harvest":
            # Best-effort classification + audit log of the shared
            # ~/.scitex/todo/tasks.yaml board. A missing/malformed
            # store sets ``result.error`` and exits non-zero so the
            # log records the failure, but the cron loop keeps
            # ticking — the next q6h tick re-tries the load. Phase-1
            # walk + Phase-2 dispatch fold into this same branch in
            # follow-up PRs without changing the dispatcher contract.
            result = _task_harvest.run_once()
            if result.error is not None:
                raise SystemExit(1)
            return

        if name == "cred-distribute":
            # Per-host credential push via `sac accounts distribute`.
            # Exit code policy:
            #   - config malformed / bootstrap failed → exit 1 so the
            #     operator's audit log records the breakage AND the
            #     cron mail (if configured) pages them.
            #   - every attempted host failed → exit 1 (systemic
            #     outage signal). One host failing while another
            #     succeeded is a transient hiccup, not a page.
            #   - sac binary / subcommand missing → exit 0 (graceful
            #     rollout-window state; the body marks those hosts
            #     skipped, the cron stays green).
            #   - all-skipped (no hosts configured OR `sac` not yet
            #     installed) → exit 0; the audit line records the
            #     no-op so the operator can confirm the loop is alive.
            result = _cred_distribute.run_once()
            if result.error is not None:
                raise SystemExit(1)
            if result.all_attempted_failed:
                raise SystemExit(1)
            return

        if name == "spartan-conn-monitor":
            # Poll the Spartan login nodes for the ywatanabe user's footprint;
            # the body logs a TSV row per node and phones the operator on a
            # threshold breach. An unreachable node or notification hiccup is
            # swallowed (cron-safe); we exit non-zero ONLY when a threshold was
            # actually crossed, so the cron log + mail flag a real regression.
            mon = _spartan_conn_monitor.run_once()
            if mon.alerts:
                raise SystemExit(1)
            return

        # Defensive — registry has an entry but no handler. Reaching here
        # means someone added a `JOB_REGISTRY` entry without wiring its
        # run-body. Fail loudly per the no-silent-stubs rule.
        raise click.ClickException(
            f"cron job {name!r} is registered but has no `exec` handler. "
            f"Add a dispatch branch in `_cli/cron/run.py`."
        )


# EOF
