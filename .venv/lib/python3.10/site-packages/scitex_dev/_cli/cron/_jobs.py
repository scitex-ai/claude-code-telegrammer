#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registry of managed cron jobs for `scitex-dev cron`.

A "managed job" is identified by a short slug (the ``name`` argument
passed to ``install`` / ``remove`` / ``status``). The registry maps that
slug to a 5-field cron schedule and the literal shell command that gets
materialised into the user's crontab — tagged with
``# scitex-dev cron: <name>`` so we can find it again.

Why a registry (vs. a free-form ``add <schedule> <command>``):

  * Ecosystem-wide cron jobs are *known* artifacts that other parts of
    the ecosystem expect to be present (e.g. the ci-watch loop is part of
    how sac agents notice they have a fix-forward turn to take).
  * Operators install / remove by *name*, not by reconstructing the
    schedule + command line from memory.
  * Adding a new job is a one-entry diff here, plus the implementation
    module under this package. Nothing else in the CLI changes.

To add a new managed job:

  1. Implement the job. Either as a Python entry point invoked via the
     console script (``scitex-dev cron run <name>``) or as a standalone
     shell command — either is fine; the registry just records the
     resulting cron line.
  2. Add an entry to ``JOB_REGISTRY`` below: ``name → (schedule, command,
     description)``. Keep the schedule conservative (every 5-15 minutes
     is plenty for poll loops).
  3. Write the unit test that pins the registry entry — see
     ``tests/scitex_dev/_cli/cron/test__jobs.py``.

The registry is intentionally a module-level dict (no YAML loader, no
dynamic discovery): one diff, one commit, one PR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class JobSpec:
    """One managed cron job."""

    name: str
    schedule: str
    command: str
    description: str


# Per-job shell-line builders live in ``_job_commands`` (extracted under
# the 512-line cap); re-imported under their original names so existing
# callers and tests (``_jobs._ecosystem_sync_command`` ...) keep resolving.
from ._job_commands import (  # noqa: F401
    _ci_runner_ensure_command,
    _ci_runner_workgc_command,
    _ci_watch_command,
    _cred_distribute_command,
    _creds_rotate_all_command,
    _ecosystem_sync_command,
    _log_rotate_guard,
    _quota_keepalive_command,
    _scholar_library_sync_command,
    _spartan_conn_monitor_command,
    _task_harvest_command,
    _worktree_gc_command,
)


JOB_REGISTRY: Mapping[str, JobSpec] = {
    "ci-watch": JobSpec(
        name="ci-watch",
        schedule="*/10 * * * *",
        command=_ci_watch_command(),
        description=(
            "Poll each sac agent's owned repo for CI red on develop; "
            "dispatch a fix-forward A2A turn to the responsible agent "
            "when failures are seen."
        ),
    ),
    "quota-keepalive": JobSpec(
        name="quota-keepalive",
        # Crontab ticks every 30 min; the body self-gates to a 2.5-hour
        # cadence (2.5 h is not expressible as a single cron interval).
        schedule="*/30 * * * *",
        command=_quota_keepalive_command(),
        description=(
            "Fire a trivial 'hello' turn every 2.5 hours (self-gated) to "
            "pre-start Claude's rolling 5-hour quota window, so real work "
            "begins against a window that is already partway elapsed."
        ),
    ),
    "worktree-gc": JobSpec(
        name="worktree-gc",
        # Every 6 hours: 4 sweeps per day, generous headroom over the
        # mtime threshold (default 3 days). See _worktree_gc_command's
        # docstring for the schedule rationale.
        schedule="0 */6 * * *",
        command=_worktree_gc_command(),
        description=(
            "Periodic cleanup of stale `.claude/worktrees/` directories "
            "left behind by subagents. mtime-gated, git-worktree-aware, "
            "never touches the operator's `.worktrees/`. See _worktree_gc."
        ),
    ),
    "task-harvest": JobSpec(
        name="task-harvest",
        # Every 6 hours: 4 harvest sweeps per day over the shared
        # ~/.scitex/todo/tasks.yaml board. Matches the q6h default the
        # operator picked in the skill (scitex-todo PR #72,
        # 40_task-harvest.md). Operator may want q1h during a busy
        # phase or q12h during a quiet phase — change THIS schedule
        # (one diff + one test) and re-install.
        schedule="0 */6 * * *",
        command=_task_harvest_command(),
        description=(
            "scitex-todo task-harvest: classify the shared "
            "~/.scitex/todo/tasks.yaml (blocked vs runnable + blocker "
            "kind), log an audit line, return a structured result the "
            "follow-up PRs extend with Phase-1 walk + Phase-2 a2a "
            "dispatch. Protocol: skill 40_task-harvest. See "
            "_task_harvest.run_once."
        ),
    ),
    "cred-distribute": JobSpec(
        name="cred-distribute",
        # Every 2 hours on the hour. Matches the operator's pre-
        # existing ad-hoc spartan-cred-push cadence (the host crontab
        # marker this job subsumes per directive 2026-06-11) and is
        # conservative for credentials that turn over on a multi-hour
        # window. The per-host target list lives in
        # ~/.scitex/dev/cred-distribute.yaml — switching behaviour
        # (add/remove host, change account selector) is a YAML edit
        # alone, no code change required.
        schedule="0 */2 * * *",
        command=_cred_distribute_command(),
        description=(
            "Push the freshest Claude credentials to peer hosts via "
            "`sac accounts distribute --to-host <h> --account <a>`. "
            "Host list + credential selector live in "
            "~/.scitex/dev/cred-distribute.yaml so behaviour is "
            "switched by config alone. Subsumes the host-side ad-hoc "
            "push-freshest-cred-to-spartan.sh (crontab marker "
            "# spartan-cred-push). Fail-open while "
            "proj-scitex-agent-container is still landing the "
            "`sac accounts distribute` capability. See "
            "_cred_distribute.run_once."
        ),
    ),
    "spartan-conn-monitor": JobSpec(
        name="spartan-conn-monitor",
        # Every 30 min. Light: one multiplexed ssh + pgrep/ps/who per login
        # node. Watches the ywatanabe user's ssh-agent / connection / proc
        # footprint on the Spartan login nodes (2026-06-17 admin incident) and
        # phones the operator if a threshold is crossed. Replaces the
        # session-bound monitor loop, which died on context compaction.
        schedule="*/30 * * * *",
        command=_spartan_conn_monitor_command(),
        description=(
            "Poll the 3 Spartan login nodes for the ywatanabe user's "
            "ssh-agents / login sessions / total procs / srun; append a TSV "
            "row per node to ~/.scitex/dev/runtime/spartan-conn-monitor.tsv; "
            "audio-notify + PHONE-CALL the operator if ssh-agents>15, srun>50, "
            "or procs>250 (early warning before the HPC admin notices). See "
            "_spartan_conn_monitor.run_once."
        ),
    ),
    "creds-rotate-all": JobSpec(
        name="creds-rotate-all",
        # Top of every hour. Matches the operator's pre-existing ad-hoc
        # `# scitex-dev creds-rotate (managed)` crontab line (the
        # default `creds rotate-all` install cadence, see
        # `_creds._cron._interval_to_schedule(60)` => "0 * * * *") that
        # this entry federates into the managed block.
        schedule="0 * * * *",
        command=_creds_rotate_all_command(),
        description=(
            "Push the freshest local ~/.claude/.credentials.json to every "
            "managed ecosystem checkout via `scitex-dev creds rotate-all "
            "--yes`. Federates the ad-hoc host line "
            "(# scitex-dev creds-rotate (managed)) into the managed block; "
            "keeps that line's 1-MiB log-rotation guard and writes to "
            "~/.scitex/dev/logs/creds-rotate.log. See _creds._cron / "
            "_creds._rotate."
        ),
    ),
    "ci-runner-ensure": JobSpec(
        name="ci-runner-ensure",
        # Every 30 minutes. Federates the operator's ad-hoc
        # ci-runner-ensure crontab line; the body is the standalone host
        # script ~/.scitex/dev/ci-runner-ensure-cron.sh (already
        # deployed). Schedule mirrors the retired ad-hoc line exactly.
        schedule="*/30 * * * *",
        command=_ci_runner_ensure_command(),
        description=(
            "Ensure the self-hosted GitHub Actions runners are present & "
            "alive by running ~/.scitex/dev/ci-runner-ensure-cron.sh. "
            "Federates the ad-hoc host crontab line into the managed "
            "block. Log at ~/.scitex/dev/logs/ci-runner-ensure.log."
        ),
    ),
    "ci-runner-workgc": JobSpec(
        name="ci-runner-workgc",
        # Every 6 hours on the hour. Federates the operator's ad-hoc
        # ci-runner-workgc crontab line; the body is the standalone host
        # script ~/.scitex/dev/ci-runner-workgc-cron.sh (already
        # deployed). Schedule mirrors the retired ad-hoc line exactly.
        schedule="0 */6 * * *",
        command=_ci_runner_workgc_command(),
        description=(
            "Garbage-collect the self-hosted CI runners' _work/ staging "
            "trees by running ~/.scitex/dev/ci-runner-workgc-cron.sh. "
            "Federates the ad-hoc host crontab line into the managed "
            "block. Log at ~/.scitex/dev/logs/ci-runner-workgc.log."
        ),
    ),
    "ecosystem-sync": JobSpec(
        name="ecosystem-sync",
        # Top of every hour. A git fetch of an already-current checkout is
        # a couple KB and the ff-merge only runs when actually behind, so
        # hourly is cheap even across ~60 repos while bounding drift to
        # <=1h. Tunable: change THIS schedule (one diff + one test) and
        # re-install. See _ecosystem_sync_command for why it exists.
        schedule="0 * * * *",
        command=_ecosystem_sync_command(),
        description=(
            "Fast-forward every editable ecosystem checkout's develop to "
            "origin (self-pull) via `scitex-dev ecosystem sync --yes`. "
            "ff-only, develop-only, skips dirty/off-develop/diverged so "
            "un-pushed work is never clobbered. Closes the drift loop that "
            "let checkouts silently serve stale code (the workstation's own "
            "scitex-dev was 18 commits behind v0.21.0; the Spartan runner "
            "145 behind). Log at ~/.scitex/dev/logs/cron-ecosystem-sync.log."
        ),
    ),
    "scholar-library-sync": JobSpec(
        name="scholar-library-sync",
        # Every 6 hours at :30 (offset from the 0-minute crowd so it never
        # contends with ecosystem-sync/creds-rotate for the hour tick). The
        # library grows by a few PDFs a day; rsync's delta transfer makes an
        # already-current push a no-op, so 4 syncs/day bounds WSL↔Spartan
        # drift to <=6h at negligible cost. Tunable: change THIS schedule
        # (one diff + one test) and re-install.
        schedule="30 */6 * * *",
        command=_scholar_library_sync_command(),
        description=(
            "One-way rsync of ~/.scitex/scholar/library from the host WSL "
            "(authority) to Spartan via `scitex-ssh sync` — no --delete, "
            "index.db* excluded (derived state), remote "
            "`scitex-scholar library db build` rebuilds the index after "
            "each push. Requires scitex-ssh>=1.1.0 ([sync] extra) + rsync "
            "(scitex-dev SystemDepSpec). Card scholar-library-cross-"
            "machine-sync-20260701. Log at "
            "~/.scitex/scholar/runtime/logs/cron-library-sync.log."
        ),
    ),
    # Future entries land here. Suggested naming pattern: short
    # action-noun like `rotate-all`, `audit-sweep`, `pypi-publish-watch`.
}


def get_job(name: str) -> JobSpec:
    """Return the registered ``JobSpec`` for ``name`` or raise KeyError."""
    try:
        return JOB_REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(JOB_REGISTRY)) or "(none)"
        raise KeyError(f"unknown cron job: {name!r}. Known jobs: {known}") from None


def list_jobs() -> list[JobSpec]:
    """Return every registered ``JobSpec`` sorted by name."""
    return [JOB_REGISTRY[k] for k in sorted(JOB_REGISTRY)]


# EOF
