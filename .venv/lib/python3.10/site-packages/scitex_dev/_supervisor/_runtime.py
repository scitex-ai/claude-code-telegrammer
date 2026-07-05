#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Long-running supervisor for the SciTeX ecosystem.

Backs ``scitex-dev-ecosystem.service``. ExecStart =
``scitex-dev ecosystem run`` → :func:`run_supervisor` (this module). The
supervisor:

1. Discovers every ``kind="service"`` JobSpec via
   :func:`scitex_dev.jobs.discover_jobs`.
2. Spawns each as a child process under itself, NOT as a per-leaf
   systemd unit (operator policy 2026-06-14: only ``scitex-dev`` shows
   in ``systemctl --user list-units``).
3. Loops at 1 Hz: poll children, restart per JobSpec.restart_policy,
   write a state snapshot every ``state_write_interval`` seconds.
4. SIGHUP → re-discover + reconcile delta (hot reload).
5. SIGTERM / SIGINT → graceful shutdown of every child, exit 0.

This module is the ONLY long-running loop in scitex-dev. Every external
touch (``signal.signal``, the discovery callable, the child constructor,
the wall clock, the state-write path) is behind a kwarg seam so the
loop is unit-testable without a real process tree.

Tick budget
-----------
The tick is bounded: each tick polls every child (``waitpid`` non-
blocking) + maybe writes state + maybe runs reconcile. None of those
should block more than tens of milliseconds. A 1 Hz tick gives ~999 ms
of slack between ticks — enough that even an unlucky reconcile cycle
(re-discover entry points across ~70 packages) fits comfortably.

Why not select/SIGCHLD?
-----------------------
A SIGCHLD handler would wake the loop the instant a child dies. But:
(a) Python's signal delivery is best-effort under heavy load (the
handler runs on the main thread at the next interpreter check), so
SIGCHLD is NOT a reliability primitive for correctness — it's a latency
optimisation; (b) the poll loop is already cheap (one
``waitpid(WNOHANG)`` per child per second, dozens of microseconds
total). A 1 s detection latency on crash is well below the operator's
"why isn't the board back yet" threshold and the loop is dramatically
simpler. We can layer SIGCHLD on later if any leaf needs sub-second
restart, but PR-1 keeps it polling.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from typing import Callable, Optional

from ..jobs import JobSpec, discover_jobs
from ._child import ChildProcess
from ._state import (
    SupervisorState,
    default_log_dir,
    default_state_path,
    write_state_atomically,
)

_logger = logging.getLogger(__name__)

DEFAULT_TICK_INTERVAL_SEC = 1.0
DEFAULT_STATE_WRITE_INTERVAL_SEC = 5.0
DEFAULT_CHILD_GRACE_SEC = 10.0


def _scitex_dev_version() -> str:
    """Resolve the installed ``scitex-dev`` version — diagnostic-only."""
    try:
        from importlib.metadata import version

        return version("scitex-dev")
    except Exception:  # pragma: no cover — defensive only
        return "unknown"


def _default_discover(extra_providers=None) -> list[JobSpec]:
    """Production default — delegate straight to :func:`discover_jobs`.

    Wrapped so a test fake can replace this single callable without
    touching the entry-point machinery.
    """
    return discover_jobs(extra_providers=extra_providers)


class Supervisor:
    """Long-running process supervisor.

    Tests construct one directly with seams (``discover``, ``clock``,
    ``sleep``, ``state_path``, ``child_factory``). Production uses
    :func:`run_supervisor` which wires production defaults.
    """

    def __init__(
        self,
        *,
        discover: Callable[[], list[JobSpec]] = _default_discover,
        log_dir: Optional[Path] = None,
        state_path: Optional[Path] = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        child_factory: Optional[Callable[..., ChildProcess]] = None,
        tick_interval_sec: float = DEFAULT_TICK_INTERVAL_SEC,
        state_write_interval_sec: float = DEFAULT_STATE_WRITE_INTERVAL_SEC,
        child_grace_sec: float = DEFAULT_CHILD_GRACE_SEC,
    ) -> None:
        self._discover = discover
        self._log_dir = log_dir or default_log_dir()
        self._state_path = state_path or default_state_path()
        self._clock = clock
        self._sleep = sleep
        self._child_factory = child_factory or self._make_child_default
        self._tick_interval = tick_interval_sec
        self._state_write_interval = state_write_interval_sec
        self._child_grace = child_grace_sec

        self._children: dict[str, ChildProcess] = {}
        self._started_at: float = 0.0
        self._last_state_write: float = 0.0
        # Signal-driven flags read on the main loop thread.
        self._reload_requested = False
        self._shutdown_requested = False

    # ------------------------------------------------------------------ #
    # Construction helpers                                               #
    # ------------------------------------------------------------------ #

    def _make_child_default(self, job: JobSpec) -> ChildProcess:
        return ChildProcess(job, log_dir=self._log_dir, clock=self._clock)

    # ------------------------------------------------------------------ #
    # Discovery + reconcile                                              #
    # ------------------------------------------------------------------ #

    def discover_service_jobs(self) -> list[JobSpec]:
        """Return only the ``kind="service"`` JobSpecs from discovery.

        Timer-kind and cron-kind JobSpecs lower to user-crontab lines
        via ``_cron_block``; they are NOT children of this supervisor.
        Filtering happens here so the rest of the runtime never sees a
        non-service kind (cleaner invariant — see ChildProcess's
        ``ValueError`` on construction).
        """
        all_jobs = self._discover()
        return [j for j in all_jobs if j.kind == "service"]

    def reconcile(self) -> dict[str, str]:
        """Reconcile children to match the current discovery output.

        Returns ``{name: action}`` where ``action`` is one of
        ``"added"`` / ``"removed"`` / ``"restarted"`` / ``"unchanged"``.
        Called once on initial bring-up (via :meth:`start_all`) and
        again on every SIGHUP-driven reload.

        Semantics:

        * Names in the new set but NOT in the registry → constructed +
          started. Action: ``added``.
        * Names in the registry but NOT in the new set → terminated +
          dropped. Action: ``removed``.
        * Names in BOTH but with a different ``command`` → terminated +
          re-constructed + started (so the new argv takes effect).
          Action: ``restarted``.
        * Names in BOTH with identical ``command`` → no-op. Action:
          ``unchanged``. The breaker ledger is reset on reload — a
          reload is the operator's signal that the leaf is supposed to
          be healthy again.
        """
        actions: dict[str, str] = {}
        new_jobs = self.discover_service_jobs()
        new_by_name = {j.name: j for j in new_jobs}

        # Removals first so a renamed-rest-of-set doesn't collide with
        # a still-running predecessor of the same name.
        for name in list(self._children):
            if name not in new_by_name:
                self._children[name].terminate(grace_sec=self._child_grace)
                self._children.pop(name)
                actions[name] = "removed"

        for name, job in new_by_name.items():
            existing = self._children.get(name)
            if existing is None:
                child = self._child_factory(job)
                self._children[name] = child
                child.start()
                actions[name] = "added"
            elif existing.job.command != job.command:
                existing.terminate(grace_sec=self._child_grace)
                child = self._child_factory(job)
                self._children[name] = child
                child.start()
                actions[name] = "restarted"
            else:
                # Same job — reset the breaker. SIGHUP is an operator
                # signal of "try again", so a previously-failed leaf
                # gets one more chance.
                existing.reset_breaker()
                actions[name] = "unchanged"
        return actions

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def start_all(self) -> None:
        """Initial bring-up: discover + spawn every service-kind child."""
        self._started_at = self._clock()
        self.reconcile()

    def tick(self) -> None:
        """One supervisor cycle.

        Steps:

        1. Poll every child (non-blocking ``waitpid``).
        2. For any child that exited and whose policy says restart,
           call ``start()`` again. ``ChildProcess.should_restart``
           encapsulates the policy decision.
        3. Maybe write the state file (rate-limited to
           ``state_write_interval_sec``).

        The tick is the loop's only side-effect surface — keeping it
        tight + idempotent means a failed write or a flapping child
        never corrupts the registry.
        """
        for child in self._children.values():
            child.poll()
            if child.should_restart():
                child.start()
                if child.status == "running":
                    child.mark_restarted()
        now = self._clock()
        if now - self._last_state_write >= self._state_write_interval:
            self._write_state()
            self._last_state_write = now

    def shutdown(self) -> None:
        """Terminate every child gracefully.

        Idempotent: a second call is a no-op (the registry is already
        empty after the first call's terminates resolve). Called from
        :meth:`run_forever` on SIGTERM / SIGINT.
        """
        for child in list(self._children.values()):
            try:
                child.terminate(grace_sec=self._child_grace)
            except Exception:  # noqa: BLE001 — never crash the shutdown
                _logger.exception(
                    "supervisor: error terminating %r — continuing", child.job.name
                )
        # Final state write so a status reader sees the "stopped" snapshot.
        try:
            self._write_state()
        except Exception:  # noqa: BLE001 — last-ditch state write
            _logger.exception("supervisor: error writing final state")

    # ------------------------------------------------------------------ #
    # Signal-driven flags                                                #
    # ------------------------------------------------------------------ #

    def request_reload(self) -> None:
        """Set the reload flag (called from a SIGHUP handler)."""
        self._reload_requested = True

    def request_shutdown(self) -> None:
        """Set the shutdown flag (called from a SIGTERM/SIGINT handler)."""
        self._shutdown_requested = True

    # ------------------------------------------------------------------ #
    # Main loop                                                          #
    # ------------------------------------------------------------------ #

    def run_forever(
        self,
        *,
        install_signal_handlers: bool = True,
        max_ticks: Optional[int] = None,
    ) -> int:
        """Run the supervisor loop until SIGTERM/SIGINT.

        Returns 0 on a graceful shutdown. ``max_ticks`` is the test
        seam — production uses ``None`` (loop forever); tests pass a
        small integer so the test exits deterministically.
        """
        if install_signal_handlers:
            self._install_signal_handlers()
        self.start_all()
        ticks = 0
        while not self._shutdown_requested:
            self.tick()
            if self._reload_requested:
                self._reload_requested = False
                actions = self.reconcile()
                _logger.info("supervisor: SIGHUP reload, actions=%s", actions)
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            self._sleep(self._tick_interval)
        self.shutdown()
        return 0

    def _install_signal_handlers(self) -> None:
        """Install SIGHUP / SIGTERM / SIGINT handlers on the main thread.

        Wrapped in a separate method so :meth:`run_forever` stays
        testable without globally rewriting signal handlers — the
        test passes ``install_signal_handlers=False`` and drives the
        flags directly.
        """

        def _on_term(_signum, _frame):
            self.request_shutdown()

        def _on_hup(_signum, _frame):
            self.request_reload()

        signal.signal(signal.SIGTERM, _on_term)
        signal.signal(signal.SIGINT, _on_term)
        signal.signal(signal.SIGHUP, _on_hup)

    # ------------------------------------------------------------------ #
    # State snapshot                                                     #
    # ------------------------------------------------------------------ #

    def _write_state(self) -> None:
        """Render + write the current SupervisorState snapshot."""
        snap = SupervisorState(
            schema_version=1,
            pid=os.getpid(),
            started_at=self._started_at,
            written_at=self._clock(),
            scitex_dev_version=_scitex_dev_version(),
            children=[c.snapshot() for c in self._children.values()],
        )
        write_state_atomically(snap, self._state_path)

    # ------------------------------------------------------------------ #
    # Read-only accessors (for tests + ecosystem status)                  #
    # ------------------------------------------------------------------ #

    @property
    def children(self) -> dict[str, ChildProcess]:
        """Live registry; tests inspect contents directly."""
        return self._children

    @property
    def state_path(self) -> Path:
        return self._state_path


def run_supervisor(*, max_ticks: Optional[int] = None) -> int:
    """Convenience entry point used by the CLI command.

    Constructs a production-defaulted :class:`Supervisor` and runs it.
    Returns the loop's exit code so the CLI can ``sys.exit(rc)``.
    """
    sup = Supervisor()
    return sup.run_forever(max_ticks=max_ticks)


__all__ = [
    "DEFAULT_CHILD_GRACE_SEC",
    "DEFAULT_STATE_WRITE_INTERVAL_SEC",
    "DEFAULT_TICK_INTERVAL_SEC",
    "Supervisor",
    "run_supervisor",
]


# EOF
