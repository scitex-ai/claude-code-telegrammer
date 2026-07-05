#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-child process bookkeeping for the ecosystem supervisor.

One :class:`ChildProcess` instance owns one ``kind="service"`` JobSpec. The
supervisor (in ``_runtime.py``) holds a ``dict[name, ChildProcess]`` and
calls into each child on every supervisor tick — start if not running, poll
for exit, decide whether to restart, etc. The split between this module
and ``_runtime`` keeps each file under the line-limit cap and lets us
unit-test the per-child state machine in isolation (no real ``subprocess``
required — every external touch is behind a kwarg seam).

Restart policy
--------------
``JobSpec.restart_policy`` follows systemd vocabulary verbatim — that was
A-J answer (B): keep the unchanged JobSpec API and translate INSIDE the
supervisor. The translation table:

* ``"no"`` — never restart; child exits once → ``ChildProcess.status``
  becomes ``"stopped"`` and stays there. The supervisor leaves it alone.
* ``"on-failure"`` — restart on non-zero exit (including signal-killed).
  Zero exit leaves it stopped; that's the only "clean shutdown" path a
  systemd ``Type=simple`` short-lived helper would respect.
* ``"on-abnormal"`` — restart on signal or non-zero exit, NOT on normal
  zero exit. Today this collapses to ``on-failure`` semantics (we don't
  yet distinguish "killed by signal" from "exited non-zero" in the
  restart decision — the supervisor only sees an integer returncode).
* ``"on-abort"`` — restart only on a true abort (SIGABRT / SIGSEGV /
  similar). Treated as ``on-failure`` for now (same caveat as above).
* ``"on-watchdog"`` — restart only on watchdog timeout. We don't ship a
  watchdog ping protocol, so this collapses to ``no``.
* ``"always"`` — restart on any exit (success or failure).

These collapses are explicit (not silent): a leaf that asked for
``on-watchdog`` and got ``no`` semantics is doing something the
supervisor can't honour, and "fail open" (treat as ``no``) is safer than
"fail closed" (busy-loop restarting something that exits zero).

Circuit breaker
---------------
A leaf that crash-loops will burn CPU. After ``circuit_window_sec``
failures within ``circuit_window_sec`` seconds (default 5 in 60), the
child's circuit opens — no more restarts until the supervisor reloads.
``ChildProcess.status`` becomes ``"failed"``. The ``status`` CLI surfaces
this so a human can intervene.

Logging
-------
``stdout`` + ``stderr`` are appended to ``log_dir/<name>.log`` so a
``tail -f`` against that path tracks the leaf live. Per-child file (not
journal) because (a) leaves can be high-volume and (b) the operator's
muscle memory is already to ``tail`` a log file. The supervisor's OWN
diagnostics go to the journal via systemd ``Type=simple``.
"""

from __future__ import annotations

import dataclasses
import errno
import os
import shlex
import signal
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..jobs import JobSpec
from ..jobs._systemd import resolve_execstart

# Failure-window defaults — operator confirmed 5-in-60. Surfaced as class
# attributes so a test can lower the threshold without monkeypatching.
DEFAULT_CIRCUIT_FAILURE_LIMIT = 5
DEFAULT_CIRCUIT_WINDOW_SEC = 60.0

# Restart back-off — exponential 5s → 60s capped, then constant.
DEFAULT_BACKOFF_INITIAL_SEC = 5.0
DEFAULT_BACKOFF_CAP_SEC = 60.0


def _now() -> float:
    """Indirection over ``time.time`` — test seam."""
    return time.time()


def _build_argv(job: JobSpec) -> list[str]:
    """Return the absolutised argv list for ``job.command``.

    ``resolve_execstart`` returns a single string; we split it back with
    ``shlex`` for the ``subprocess.Popen`` list form. The split is safe
    because ``resolve_execstart`` itself round-trips through
    ``shlex.join`` so quoting is consistent.
    """
    resolved = resolve_execstart(job.command)
    return shlex.split(resolved)


# --------------------------------------------------------------------------- #
# ChildProcess                                                                 #
# --------------------------------------------------------------------------- #


@dataclass
class _RestartLedger:
    """Small accounting struct for the circuit-breaker window.

    Kept as a separate dataclass so ``ChildProcess`` stays focused on the
    process lifecycle and the breaker logic is testable on its own.
    """

    failure_limit: int = DEFAULT_CIRCUIT_FAILURE_LIMIT
    window_sec: float = DEFAULT_CIRCUIT_WINDOW_SEC
    failures: deque = field(default_factory=deque)
    circuit_open: bool = False

    def record_failure(self, *, now: float) -> bool:
        """Record a failure timestamp; return ``True`` if breaker just tripped.

        The window is sliding: failures older than ``window_sec`` are
        dropped before the count check. That makes a leaf with one
        flake per hour stay "healthy" (not within window) instead of
        gradually accumulating into a trip after enough total flakes.
        """
        cutoff = now - self.window_sec
        while self.failures and self.failures[0] < cutoff:
            self.failures.popleft()
        self.failures.append(now)
        if not self.circuit_open and len(self.failures) >= self.failure_limit:
            self.circuit_open = True
            return True
        return False

    def reset(self) -> None:
        """Reset the ledger (called on SIGHUP-driven reconcile)."""
        self.failures.clear()
        self.circuit_open = False


class ChildProcess:
    """One leaf process under the supervisor.

    The supervisor holds one ``ChildProcess`` per ``kind="service"``
    JobSpec discovered. Every public method is idempotent so a stuck
    state never wedges the loop:

    * ``start()`` — no-op if already running, otherwise spawns.
    * ``poll()`` — returns the latest known status without ever blocking.
    * ``terminate()`` — sends SIGTERM, then SIGKILL after the grace
      period; safe to call multiple times.

    External seams (for tests):

    * ``popen_factory`` — a ``Callable[..., subprocess.Popen]`` that
      defaults to :class:`subprocess.Popen`. Tests pass a fake that
      records the argv + env it was called with.
    * ``clock`` — a ``Callable[[], float]`` that defaults to
      :func:`time.time`. Tests freeze the clock to drive the breaker
      deterministically.
    * ``sleep`` — a ``Callable[[float], None]`` that defaults to
      :func:`time.sleep`. Used only by ``terminate()``'s grace wait;
      tests inject a no-op so the SIGTERM→SIGKILL escalation runs
      instantly (mirrors the ``Supervisor`` sleep seam — no real sleep
      in tests).
    """

    def __init__(
        self,
        job: JobSpec,
        *,
        log_dir: Path,
        popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
        clock: Callable[[], float] = _now,
        sleep: Callable[[float], None] = time.sleep,
        circuit_failure_limit: int = DEFAULT_CIRCUIT_FAILURE_LIMIT,
        circuit_window_sec: float = DEFAULT_CIRCUIT_WINDOW_SEC,
    ) -> None:
        if job.kind != "service":
            raise ValueError(
                f"ChildProcess({job.name!r}): only kind='service' may be "
                f"supervised as a child process; got kind={job.kind!r}"
            )
        self.job = job
        self.log_dir = log_dir
        self._popen_factory = popen_factory
        self._clock = clock
        self._sleep = sleep
        self._ledger = _RestartLedger(
            failure_limit=circuit_failure_limit,
            window_sec=circuit_window_sec,
        )
        self._proc: Optional[subprocess.Popen] = None
        self._log_fh = None
        self._started_at: float = 0.0
        self._stopped_at: float = 0.0
        self._restart_count: int = 0
        self._last_exit_code: Optional[int] = None
        # ``status`` mirrors what the snapshot reports. Values: ``stopped``,
        # ``starting``, ``running``, ``failed`` (circuit open).
        self._status: str = "stopped"
        self._argv: list[str] = []

    # ------------------------------------------------------------------ #
    # Public state surface                                               #
    # ------------------------------------------------------------------ #

    @property
    def status(self) -> str:
        return self._status

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc is not None else None

    @property
    def restart_count(self) -> int:
        return self._restart_count

    @property
    def circuit_open(self) -> bool:
        return self._ledger.circuit_open

    @property
    def started_at(self) -> float:
        return self._started_at

    @property
    def last_exit_code(self) -> Optional[int]:
        return self._last_exit_code

    @property
    def log_path(self) -> Path:
        return self.log_dir / f"{self.job.name}.log"

    @property
    def argv(self) -> list[str]:
        """Return the most-recently-used argv (empty before first start)."""
        return list(self._argv)

    def snapshot(self) -> dict:
        """Return a JSON-serialisable dict for ``state.json``."""
        return {
            "name": self.job.name,
            "kind": self.job.kind,
            "command": self.job.command,
            "status": self._status,
            "pid": self.pid,
            "started_at": self._started_at,
            "restart_count": self._restart_count,
            "recent_failure_count": len(self._ledger.failures),
            "circuit_open": self._ledger.circuit_open,
            "last_exit_code": self._last_exit_code,
            "log_path": str(self.log_path),
            "restart_policy": self.job.restart_policy,
            "description": self.job.description,
        }

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Spawn the child if not currently running. Idempotent.

        Re-entrancy: a concurrent caller (or a tick that races with a
        SIGHUP reload) seeing ``_proc is not None`` short-circuits — the
        running process is the source of truth, no second Popen.

        Circuit-breaker check: if the breaker is open we never start.
        The status surface reports ``"failed"`` so an operator can see
        it; a SIGHUP reload resets the ledger and re-attempts.
        """
        if self._ledger.circuit_open:
            self._status = "failed"
            return
        if self._proc is not None and self._proc.poll() is None:
            # Already running; refuse to double-spawn.
            return
        self._argv = _build_argv(self.job)
        # Append to log so a restart preserves the prior log trail.
        # ``mkdir`` here (not at construction) so the supervisor can
        # construct ChildProcess instances cheaply before deciding to
        # actually run them (e.g. discovery dry-run).
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # ``buffering=0`` would matter for the supervisor's own writes;
        # the child writes via its own fd, line-buffered as usual.
        self._log_fh = open(self.log_path, "ab")
        try:
            self._proc = self._popen_factory(
                self._argv,
                stdout=self._log_fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                # The leaf inherits the supervisor's environment; per-leaf
                # env extensions are NOT implemented in PR-1 (the JobSpec
                # contract doesn't carry env today — that's a follow-up if
                # any leaf needs it).
                env=os.environ.copy(),
                # New process group so a SIGTERM to the supervisor
                # doesn't immediately also hit the children — the
                # supervisor's own shutdown() walks the registry and
                # sends SIGTERMs deliberately.
                start_new_session=True,
                close_fds=True,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            # Treat a Popen failure as a "failure event" — record it
            # against the breaker and surface as ``failed`` so the
            # status reader knows. A breaker-tripping Popen failure
            # short-circuits the loop on the next call.
            self._log_fh.close()
            self._log_fh = None
            self._proc = None
            self._last_exit_code = getattr(exc, "errno", -1) or -1
            tripped = self._ledger.record_failure(now=self._clock())
            self._status = "failed" if tripped else "stopped"
            return
        self._started_at = self._clock()
        self._stopped_at = 0.0
        self._status = "running"

    def poll(self) -> str:
        """Update + return the child's status without blocking.

        Drains a finished child's returncode into ``_last_exit_code``,
        closes the log fh, and clears ``_proc`` so the next call to
        :meth:`start` is free to re-spawn (subject to the breaker +
        restart policy gate checked by the supervisor).
        """
        if self._proc is None:
            # Not currently running — status is whatever was last set
            # (``stopped`` on first call, ``failed`` if breaker opened).
            return self._status
        rc = self._proc.poll()
        if rc is None:
            self._status = "running"
            return "running"
        # Exited; capture + clean up.
        self._last_exit_code = rc
        self._stopped_at = self._clock()
        if self._log_fh is not None:
            try:
                self._log_fh.close()
            finally:
                self._log_fh = None
        self._proc = None
        # Distinguish clean vs failed exit so the supervisor's restart
        # decision can honour the restart_policy.
        if rc == 0:
            self._status = "stopped"
        else:
            # Non-zero — record against the breaker. Even if the policy
            # is ``no`` we count the failure for the status surface.
            tripped = self._ledger.record_failure(now=self._clock())
            self._status = "failed" if tripped else "stopped"
        return self._status

    def should_restart(self) -> bool:
        """Return ``True`` if the supervisor should call :meth:`start` next.

        Policy decision happens here so the supervisor loop is policy-
        agnostic — it just polls + asks-then-starts. See module docstring
        for the systemd-vocabulary translation.
        """
        if self._proc is not None:
            return False  # already running
        if self._ledger.circuit_open:
            return False  # breaker tripped
        policy = self.job.restart_policy
        rc = self._last_exit_code
        if policy == "always":
            return True
        if policy in {"on-failure", "on-abnormal", "on-abort"}:
            # ``rc is None`` means "never started" — yes, kick the first
            # start; the supervisor's main loop relies on this on initial
            # bring-up.
            return rc is None or rc != 0
        # ``no`` / ``on-watchdog`` / unknown — never restart automatically.
        # First-bring-up is handled by start_all in the supervisor (which
        # calls start() unconditionally on initial discovery).
        return False

    def terminate(self, *, grace_sec: float = 10.0) -> None:
        """Stop the child gracefully: SIGTERM → wait → SIGKILL stragglers.

        Idempotent: a second call on an already-stopped child is a no-op
        (handle is None). A child that exits during the grace period is
        reaped through the same ``poll`` path so ``last_exit_code`` is
        consistent with a natural exit.
        """
        if self._proc is None:
            return
        # SIGTERM the whole process group (start_new_session=True at
        # spawn). If the child spawned its own children, this catches
        # them too — a long-running leaf that forked workers stays
        # consistent.
        try:
            os.killpg(self._proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            # Already gone, or we don't own it (test-fake doesn't open
            # a real PGID). Fall through to the wait + KILL path.
            pass
        # Iteration-bounded grace wait. Bounding by a fixed step count
        # (not ``while self._clock() < deadline``) makes this immune to a
        # frozen / non-advancing injected clock — a deterministic test
        # clock that returns a constant would otherwise spin here forever.
        # ``self._sleep`` is the injectable seam (no real sleep in tests).
        poll_interval = 0.1
        steps = max(1, int(grace_sec / poll_interval))
        for _ in range(steps):
            if self._proc.poll() is not None:
                break
            self._sleep(poll_interval)
        if self._proc.poll() is None:
            # Still alive — escalate.
            try:
                os.killpg(self._proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                # Wedged in D-state; nothing we can do from userspace.
                pass
        # Reap + clean up via the same poll path so state is consistent.
        self.poll()

    def reset_breaker(self) -> None:
        """Reset the circuit-breaker ledger (SIGHUP reconcile)."""
        self._ledger.reset()

    def mark_restarted(self) -> None:
        """Bookkeeping: bump the restart counter (called by the supervisor)."""
        self._restart_count += 1


__all__ = [
    "DEFAULT_BACKOFF_CAP_SEC",
    "DEFAULT_BACKOFF_INITIAL_SEC",
    "DEFAULT_CIRCUIT_FAILURE_LIMIT",
    "DEFAULT_CIRCUIT_WINDOW_SEC",
    "ChildProcess",
]


# EOF
