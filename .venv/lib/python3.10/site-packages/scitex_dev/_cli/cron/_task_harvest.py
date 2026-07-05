#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``task-harvest`` cron job — recurring backlog-consumption sweep over
the shared ``~/.scitex/todo/tasks.yaml`` board.

This module is the body the materialised ``scitex-dev cron exec
task-harvest`` line invokes. The PROTOCOL the body implements lives in
``scitex_todo._skills.scitex-todo.40_task-harvest`` (the skill the
operator commissioned in TG msgs 332 + 335 and scitex-todo PR #72):

  Phase 1 — re-check every ``status: blocked`` task. If its blocker
            has cleared (compute resource freed / quota reset / the
            ``depends_on`` chain bottomed-out at ``done``), flip its
            status back. ``task-dependency`` blockers are TRANSITIVE
            so the walk follows the chain to its leaf — the actual
            atomic blocker (``compute`` / ``quota`` / ``user-pending``)
            or a RUNNABLE node — and routes any pressure there, not
            at intermediate relay nodes.

  Phase 2 — every ``RUNNABLE`` task (no live blocker) is a candidate
            for ESCALATION. The lead a2a-dispatches it to the owning
            agent (``agent: proj-<…>``) so consumption-rate stays >
            arrival-rate and the board doesn't drift from the live
            codebase.

This module ships the *cron-side* of that loop: load the YAML, classify
every task, log a structured one-line summary, return a result the
``exec`` dispatcher can inspect. The full Phase-1 walk + Phase-2 a2a
dispatch land in a follow-up — keeping this PR surgical per lead a2a
``cbc8203c`` (2026-06-08). Today's body provides:

  * a reliable cron tick (registered alongside ``ci-watch`` /
    ``worktree-gc`` so the operator can ``scitex-dev cron list`` and
    see the harvest is wired)
  * an audit line on every fire (``[task-harvest YYYY-MM-DD]
    N=… blocked=… runnable=… …``) appended to
    ``~/.scitex/dev/logs/cron-task-harvest.log``
  * a structured ``TaskHarvestResult`` (``scanned`` /
    ``blocked`` / ``runnable`` / ``done`` / ``error``) so the
    follow-up PRs add Phase-1 walk + Phase-2 dispatch without changing
    the dispatcher contract

Robustness contract
-------------------
This runs unattended from cron. It must never crash the cron loop:

  * If ``tasks.yaml`` is missing / malformed, we log the outcome and
    return a result whose ``error`` is set — the ``exec`` dispatcher
    exits non-zero so the log records the failure, but the cron
    schedule keeps ticking.
  * The audit log is best-effort: a write failure must not prevent
    the sweep from having run.

Seams (per PA-306 / STX-NM)
----------------------------
``tasks_path`` (path-or-None — ``None`` triggers the standard
scitex-todo resolution chain) and ``now`` (a ``Callable[[], float]``
returning epoch seconds) are keyword arguments so tests pass real
fakes — no monkeypatching of ``time`` or filesystem.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence


# The store-resolution chain for ``tasks.yaml`` (highest precedence
# first), mirroring scitex_todo._paths so the cron body picks the SAME
# file scitex-todo itself uses. Kept inline (no scitex-todo import) so
# scitex-dev doesn't take a cross-package runtime dependency on
# scitex-todo just to run this cron tick.
STORE_ENV_VAR: str = "SCITEX_TODO_TASKS"
USER_STORE_DEFAULT: str = "~/.scitex/todo/tasks.yaml"


def _state_dir() -> Path:
    """Return the canonical scitex-dev local-state dir (``~/.scitex/dev``).

    Honours ``$SCITEX_DIR`` (the ecosystem-wide relocation lever) so
    the harvest log lives next to the other cron logs without per-host
    configuration.
    """
    base = os.environ.get("SCITEX_DIR") or os.path.join(
        os.path.expanduser("~"), ".scitex"
    )
    return Path(base) / "dev"


def _resolve_tasks_path() -> Path:
    """Find ``tasks.yaml`` via the standard scitex-todo precedence chain.

    Highest precedence first:
      1. ``$SCITEX_TODO_TASKS`` env var
      2. ``~/.scitex/todo/tasks.yaml`` (the canonical user store)

    The project-tier (`<git-root>/.scitex/todo/tasks.yaml`) tier
    scitex-todo also supports is intentionally NOT walked from a cron
    job — the cron has no current-project context, so falling back on
    the user store is the right default.
    """
    env_path = os.environ.get(STORE_ENV_VAR)
    if env_path:
        return Path(env_path).expanduser()
    return Path(USER_STORE_DEFAULT).expanduser()


@dataclass(frozen=True)
class TaskHarvestResult:
    """Aggregate outcome of one ``task-harvest`` exec-body invocation.

    Phase-1 walk + Phase-2 dispatch land in follow-up PRs; today's
    fields are the at-a-glance counts that let the operator confirm
    the harvest is wired and ticking.
    """

    tasks_path: str
    scanned: int
    by_status: Mapping[str, int] = field(default_factory=dict)
    blocked_by_kind: Mapping[str, int] = field(default_factory=dict)
    error: str | None = None

    @property
    def blocked(self) -> int:
        return self.by_status.get("blocked", 0)

    @property
    def runnable(self) -> int:
        """A task is runnable when it isn't blocked / done / deferred / failed.

        ``goal`` rows are umbrella nodes (per the scitex-todo schema)
        and the harvest doesn't escalate them, so they're excluded too.
        """
        nonrun = {"blocked", "done", "deferred", "failed", "goal"}
        return sum(n for s, n in self.by_status.items() if s not in nonrun)

    @property
    def done(self) -> int:
        return self.by_status.get("done", 0)


def _load_yaml(path: Path) -> object:
    """Load a YAML document. Local import so a missing ``ruamel.yaml`` /
    ``pyyaml`` only surfaces when the cron body actually runs (the
    registry + dispatch wiring tests don't import this module's body).
    """
    try:
        from ruamel.yaml import YAML

        return YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except ImportError:  # pragma: no cover — ruamel is a scitex-todo dep
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8"))


def _classify(tasks: Sequence[Mapping[str, object]]) -> tuple[dict, dict]:
    """Return (by_status, blocked_by_kind) — the two summary maps."""
    by_status: dict[str, int] = {}
    blocked_by_kind: dict[str, int] = {}
    for t in tasks:
        status = str(t.get("status") or "pending")
        by_status[status] = by_status.get(status, 0) + 1
        if status == "blocked":
            blocker = str(t.get("blocker") or "(unspecified)")
            blocked_by_kind[blocker] = blocked_by_kind.get(blocker, 0) + 1
    return by_status, blocked_by_kind


def run_once(
    *,
    tasks_path: Path | None = None,
    now: Callable[[], float] = time.time,
) -> TaskHarvestResult:
    """Execute one task-harvest pass — load + classify + log.

    Phase-1 walk + Phase-2 dispatch are deferred to follow-up PRs (see
    the module docstring). Today's body is the classification half:
    counts that prove the harvest is wired, ready for the walk +
    dispatch logic to fold in.
    """
    resolved = (tasks_path or _resolve_tasks_path()).expanduser()
    timestamp = datetime.fromtimestamp(now(), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%MZ"
    )

    if not resolved.exists():
        msg = f"tasks.yaml not found at {resolved}"
        print(
            f"[task-harvest {timestamp}] ERROR: {msg}",
            file=sys.stderr,
            flush=True,
        )
        return TaskHarvestResult(
            tasks_path=str(resolved), scanned=0, error=msg
        )

    try:
        doc = _load_yaml(resolved)
    except Exception as exc:  # noqa: BLE001 — best-effort logging
        msg = f"failed to load {resolved}: {exc.__class__.__name__}: {exc}"
        print(
            f"[task-harvest {timestamp}] ERROR: {msg}",
            file=sys.stderr,
            flush=True,
        )
        return TaskHarvestResult(
            tasks_path=str(resolved), scanned=0, error=msg
        )

    tasks = list(
        ((doc or {}).get("tasks", []) if isinstance(doc, Mapping) else [])
    )
    by_status, blocked_by_kind = _classify(tasks)
    runnable = sum(
        n
        for s, n in by_status.items()
        if s not in {"blocked", "done", "deferred", "failed", "goal"}
    )

    # Audit line — append-only, greppable by date prefix. Phase-1 walk
    # + Phase-2 dispatch fold into THIS log line so a single grep
    # against `~/.scitex/dev/logs/cron-task-harvest.log` answers "how
    # are we trending?" across the whole history of the board.
    print(
        f"[task-harvest {timestamp}] "
        f"path={resolved} N={len(tasks)} "
        f"blocked={by_status.get('blocked', 0)} "
        f"runnable={runnable} done={by_status.get('done', 0)} "
        f"by_kind={dict(sorted(blocked_by_kind.items()))}",
        flush=True,
    )

    return TaskHarvestResult(
        tasks_path=str(resolved),
        scanned=len(tasks),
        by_status=by_status,
        blocked_by_kind=blocked_by_kind,
    )


# EOF
