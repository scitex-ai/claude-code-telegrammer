#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-job shell-line builders for the managed cron registry.

Extracted VERBATIM from ``_jobs.py`` (512-line cap refactor): every
``_*_command()`` builder plus the shared 1-MiB log-rotation guard.
``_jobs.py`` re-imports these under their original names, so
``_jobs._ecosystem_sync_command`` etc. keep resolving for callers and
tests. The builders are pure string constructors -- no side effects.
"""

from __future__ import annotations

def _ci_watch_command() -> str:
    """The shell line installed for the ``ci-watch`` cron job.

    We invoke the console script (``scitex-dev cron exec ci-watch``) so
    the line stays stable across virtual-env shuffles — ``scitex-dev`` is
    on PATH wherever this CLI is installed.

    Output is appended to ``~/.scitex/dev/logs/cron-ci-watch.log``; size
    rotation is intentionally not done here (cron-watch is low-volume
    and the log is operator-facing, not a hot path).
    """
    log = "$HOME/.scitex/dev/logs/cron-ci-watch.log"
    return f"mkdir -p $(dirname {log}); scitex-dev cron exec ci-watch >> {log} 2>&1"


def _worktree_gc_command() -> str:
    """The shell line installed for the ``worktree-gc`` cron job.

    Same shape as ``ci-watch`` / ``quota-keepalive``: invoke the console
    script so the line stays stable across virtual-env shuffles,
    ``mkdir -p`` the log dir first, append output to a per-job log.

    Schedule rationale: every 6 hours is conservative — a single sweep
    is short (find git dirs, ``git worktree list``, mtime check), and
    proj-scitex-agent-container is concurrently working on the
    RELOCATION half (stopping ``.claude/worktrees`` from being created
    in the first place), so the cleanup loop's load will fall over
    time. Until that ships, 4 sweeps per day keeps the orphan count
    bounded without spending CI on a constant background walk.
    """
    log = "$HOME/.scitex/dev/logs/cron-worktree-gc.log"
    return f"mkdir -p $(dirname {log}); scitex-dev cron exec worktree-gc >> {log} 2>&1"


def _quota_keepalive_command() -> str:
    """The shell line installed for the ``quota-keepalive`` cron job.

    Same shape as ``ci-watch``: invoke the console script so the line
    stays stable across virtual-env shuffles, ``mkdir -p`` the log dir
    first, append output to a per-job log.

    The crontab schedule is ``*/30 * * * *`` (every 30 minutes), but the
    body self-gates to fire only every 2.5 hours — see
    ``_quota_keepalive.run_once`` for why 2.5 h cannot be one cron
    interval and how the timestamp gate enforces exact spacing.
    """
    log = "$HOME/.scitex/dev/logs/cron-quota-keepalive.log"
    return (
        f"mkdir -p $(dirname {log}); scitex-dev cron exec quota-keepalive >> {log} 2>&1"
    )


def _cred_distribute_command() -> str:
    """The shell line installed for the ``cred-distribute`` cron job.

    Same shape as ``ci-watch`` / ``worktree-gc`` / ``task-harvest``:
    invoke the console script so the line stays stable across
    virtual-env shuffles, ``mkdir -p`` the log dir first, append output
    to a per-job log.

    Schedule rationale: every 2 hours (``0 */2 * * *``) — matches the
    operator's pre-existing ad-hoc ``spartan-cred-push`` cadence (the
    stop-gap this job subsumes) and is conservative for credentials
    that turn over on a multi-hour window. Operator-tunable: change
    the schedule HERE (one diff + one test) and re-install.

    Body lives in ``_cred_distribute.run_once``; the per-host list and
    credential selector are read from
    ``~/.scitex/dev/cred-distribute.yaml`` so switching behaviour does
    not require any code change. Coordinates with
    proj-scitex-agent-container which is concurrently building the
    ``sac accounts distribute`` capability — the body is fail-open
    until that capability lands.
    """
    log = "$HOME/.scitex/dev/logs/cron-cred-distribute.log"
    return (
        f"mkdir -p $(dirname {log}); scitex-dev cron exec cred-distribute >> {log} 2>&1"
    )


def _task_harvest_command() -> str:
    """The shell line installed for the ``task-harvest`` cron job.

    Same shape as ``ci-watch`` / ``worktree-gc`` / ``quota-keepalive``:
    invoke the console script so the line stays stable across
    virtual-env shuffles, ``mkdir -p`` the log dir first, append
    output to a per-job log.

    Schedule rationale: every 6 hours (``0 */6 * * *``) — the harvest
    walks the shared task store, re-checks blockers, and (in the
    follow-up that adds Phase-2 dispatch) a2a-escalates RUNNABLE
    tasks to their owning agents. 4 sweeps per day keeps
    consumption-rate pressure on the board without spamming agent
    inboxes. Operator-tunable: change the schedule HERE (one diff +
    one test) and re-install.

    Body lives in ``_task_harvest.run_once``; the operator-facing
    PROTOCOL lives in ``scitex_todo._skills.scitex-todo.40_task-harvest``
    (the skill the operator commissioned, scitex-todo PR #72).
    """
    log = "$HOME/.scitex/dev/logs/cron-task-harvest.log"
    return f"mkdir -p $(dirname {log}); scitex-dev cron exec task-harvest >> {log} 2>&1"


def _spartan_conn_monitor_command() -> str:
    """The shell line installed for the ``spartan-conn-monitor`` cron job.

    Same shape as the other jobs: invoke the console script so the line stays
    stable across virtual-env shuffles, ``mkdir -p`` the log dir, append to a
    per-job log. Schedule ``*/30 * * * *`` (every 30 min) — light (one
    multiplexed ssh + pgrep/ps/who per login node), enough to catch a
    connection/agent regression long before the HPC admin would. Body in
    ``_spartan_conn_monitor.run_once``; metrics history is the TSV at
    ``~/.scitex/dev/runtime/spartan-conn-monitor.tsv``.
    """
    log = "$HOME/.scitex/dev/logs/cron-spartan-conn-monitor.log"
    return (
        f"mkdir -p $(dirname {log}); "
        f"scitex-dev cron exec spartan-conn-monitor >> {log} 2>&1"
    )


# 1 MiB — the size at which the per-job log is rotated to ``<log>.1``
# before the job runs. Mirrors ``_creds._cron._LOG_ROTATE_BYTES`` (the
# ad-hoc creds-rotate installer this federation subsumes) so the
# managed line keeps the exact rotation behaviour the host line had.
_LOG_ROTATE_BYTES = 1_048_576


def _log_rotate_guard(log: str) -> str:
    """Inline shell that rotates ``log`` to ``<log>.1`` when it exceeds 1 MiB.

    Same shell-fu as ``_creds._cron.build_cron_line``: when the log grows
    past ``_LOG_ROTATE_BYTES`` move it aside so the running line re-opens a
    fresh file. Returned with a trailing ``; `` so it composes directly in
    front of the command body.
    """
    return (
        f'[ -f {log} ] && [ "$(stat -c%s {log} 2>/dev/null || echo 0)" '
        f"-gt {_LOG_ROTATE_BYTES} ] && mv {log} {log}.1; "
    )


def _creds_rotate_all_command() -> str:
    """The shell line installed for the ``creds-rotate-all`` cron job.

    This federates the operator's pre-existing ad-hoc crontab line
    (tagged ``# scitex-dev creds-rotate (managed)`` — see
    ``_creds._cron``) into the managed block. The body is identical to
    that installer's: ``mkdir -p`` the log dir, run the 1-MiB log-
    rotation guard, then run ``scitex-dev creds rotate-all --yes``
    appending to ``~/.scitex/dev/logs/creds-rotate.log``.

    NOTE the log slug is ``creds-rotate.log`` (NO ``cron-`` prefix) to
    match the existing ad-hoc line byte-for-byte — the line this entry
    retires writes to exactly that path, and operators / dashboards that
    tail it must keep working across the move.
    """
    log = "$HOME/.scitex/dev/logs/creds-rotate.log"
    return (
        f"mkdir -p $(dirname {log}); {_log_rotate_guard(log)}"
        f"scitex-dev creds rotate-all --yes >> {log} 2>&1"
    )


def _ci_runner_ensure_command() -> str:
    """The shell line installed for the ``ci-runner-ensure`` cron job.

    Federates the operator's ad-hoc ``ci-runner-ensure`` crontab line into
    the managed block. The job body is the standalone host script
    ``~/.scitex/dev/ci-runner-ensure-cron.sh`` (already deployed on the
    host); this entry only records the resulting cron line so the
    federation materialises it. ``mkdir -p`` the log dir first, then run
    the script appending to ``~/.scitex/dev/logs/ci-runner-ensure.log``.
    """
    log = "$HOME/.scitex/dev/logs/ci-runner-ensure.log"
    script = "$HOME/.scitex/dev/ci-runner-ensure-cron.sh"
    return f"mkdir -p $(dirname {log}); {script} >> {log} 2>&1"


def _ci_runner_workgc_command() -> str:
    """The shell line installed for the ``ci-runner-workgc`` cron job.

    Federates the operator's ad-hoc ``ci-runner-workgc`` crontab line into
    the managed block. The job body is the standalone host script
    ``~/.scitex/dev/ci-runner-workgc-cron.sh`` (already deployed on the
    host); this entry only records the resulting cron line so the
    federation materialises it. ``mkdir -p`` the log dir first, then run
    the script appending to ``~/.scitex/dev/logs/ci-runner-workgc.log``.
    """
    log = "$HOME/.scitex/dev/logs/ci-runner-workgc.log"
    script = "$HOME/.scitex/dev/ci-runner-workgc-cron.sh"
    return f"mkdir -p $(dirname {log}); {script} >> {log} 2>&1"


def _ecosystem_sync_command() -> str:
    """The shell line installed for the ``ecosystem-sync`` cron job.

    Runs the WRITE self-pull ``scitex-dev ecosystem sync --yes`` (see
    ``_cmds/_sync.py``), which fast-forwards every editable checkout's
    ``develop`` to ``origin/develop``. Safe by construction: develop-only,
    ``git merge --ff-only``, and dirty / off-develop / diverged checkouts
    are reported and SKIPPED — never clobbered, so the operator's
    un-pushed work is never touched.

    Why this is a MANAGED job and not merely an available command: the
    ecosystem runs on editable installs that import their own working
    tree, but ``origin/develop`` advances on its own (CI commits docs-HTML
    and version bumps back). Without a periodic self-pull a checkout
    silently serves stale code — the workstation's own ``scitex-dev``
    checkout was found 18 commits behind tag v0.21.0 (2026-07-01) and the
    Spartan runner 145 behind. Scheduling the sweep closes that self-pull
    leg of the loop so no editable install drifts unnoticed again.

    ``mkdir -p`` the log dir, run the 1-MiB log-rotation guard (a sweep
    over ~60 repos writes a table each run), then append output to
    ``~/.scitex/dev/logs/cron-ecosystem-sync.log``.
    """
    log = "$HOME/.scitex/dev/logs/cron-ecosystem-sync.log"
    return (
        f"mkdir -p $(dirname {log}); {_log_rotate_guard(log)}"
        f"scitex-dev ecosystem sync --yes >> {log} 2>&1"
    )


def _scholar_library_sync_command() -> str:
    """The shell line installed for the ``scholar-library-sync`` cron job.

    One-way rsync of the scholar library, host-WSL → Spartan, via
    ``scitex-ssh sync`` (the ``sync_dir`` primitive shipped in
    scitex-ssh>=1.1.0). Design locked with scitex-scholar + scitex-ssh
    (card scholar-library-cross-machine-sync-20260701):

    - WSL is the AUTHORITY; the push is one-way and ``--delete`` is never
      passed, so a Spartan-side mistake cannot propagate back and a
      WSL-side pruning does not silently reap Spartan copies.
    - ``index.db`` + its journal/WAL/SHM siblings are EXCLUDED: the index
      is DERIVED state (per scitex-scholar), rebuilt on the destination
      after each push — shipping a live SQLite file mid-write corrupts it.
    - ``ssh spartan mkdir -p`` precedes the rsync instead of rsync's
      ``--mkpath`` because Spartan's system rsync predates 3.2.3.
    - Post-sync, the DERIVED index is rebuilt on Spartan
      (``scitex-scholar library db build``); a failed rsync short-circuits
      the rebuild (``&&``) so a partial tree is never indexed.
    - PRE-SYNC DEDUPE on the WSL (authority) side:
      ``scitex-scholar library dedupe --apply`` (public CLI, scholar
      PR #62, ships in scitex-scholar>=1.4.3) quarantines duplicate-DOI
      losers to ``MASTER_quarantine/`` (reversible, never hard-deletes).
      Exit-code contract pinned with scholar: ``--apply`` exits 0 once
      clean (or none existed) so the one-run pipeline proceeds; non-zero
      ONLY on unresolved-after-apply or apply/IO error — so a new
      duplicate never wedges the sync, but a genuinely stuck conflict
      blocks the push (and the remote rebuild) fail-loud.

    Requires ``scitex-ssh`` (>=1.1.0) + ``scitex-scholar`` (>=1.4.3) —
    both in the ``[sync]`` extra — and ``rsync`` on the host, declared
    via scitex-dev's SystemDepSpec provider (``scitex_dev._system_deps``).
    A missing binary fails loudly in the log ("command not found") rather
    than half-syncing.

    ``mkdir -p`` the log dir first; the log lives under the SCHOLAR leaf's
    user-level runtime dir per the 2026-07-01 operator directive ("logs
    must be under runtime for the user-level leaf state directories") —
    the data being synced is scholar state, so its log lives with it.
    """
    log = "$HOME/.scitex/scholar/runtime/logs/cron-library-sync.log"
    lib = "$HOME/.scitex/scholar/library"
    excludes = (
        "--exclude index.db --exclude index.db-journal "
        "--exclude index.db-wal --exclude index.db-shm"
    )
    return (
        f"mkdir -p $(dirname {log}); {_log_rotate_guard(log)}"
        f"{{ scitex-scholar library dedupe --apply --library-root {lib} && "
        "ssh spartan 'mkdir -p ~/.scitex/scholar/library' && "
        f"scitex-ssh sync {lib}/ spartan:.scitex/scholar/library/ "
        f"{excludes} --yes && "
        "ssh spartan 'bash -lc \"scitex-scholar library db build "
        "--library-root ~/.scitex/scholar/library\"'; } "
        f">> {log} 2>&1"
    )
