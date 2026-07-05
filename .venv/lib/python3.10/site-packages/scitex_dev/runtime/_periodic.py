#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Supervised periodic asyncio task — the ONE shape behind every SciTeX daemon loop.

sac's listen daemon (and other SciTeX daemons) hand-roll ~6 periodic
background loops that ALL share one shape: an async ``while`` loop that fires
on an interval, dispatches blocking IO off the event loop, is gated by an env
var, cancels cleanly on shutdown, and fails loud on error. This module is that
shape, factored into ONE primitive so daemon-owning packages *consume* it
instead of re-implementing it (sac's liveness-tick, zombie-reconciler,
bind-watchdog, github-CI-poll, tui-heartbeat and periodic-drive loops all
collapse onto :class:`PeriodicTask`).

Public surface
--------------
* :class:`PeriodicTask` — one supervised interval loop. Construct with a
  callable + interval, ``await task.run()`` to drive it until cancelled.
* :class:`PeriodicTaskGroup` — start N :class:`PeriodicTask` s together and
  cancel them all cleanly on shutdown. This is how a daemon owns its loop set.

Design seams (all injectable, so tests never wait real seconds)
---------------------------------------------------------------
* ``clock`` / ``sleep`` — the wall clock is behind a kwarg. A fake clock lets a
  test assert "fired N times over M intervals" without a real sleep.
* ``logger`` — the fail-loud sink is injectable so a test can capture the
  ``logger.exception`` call rather than reading the journal.
* ``to_thread`` — the off-loop dispatch hook (defaults to
  :func:`asyncio.to_thread`) is injectable for the same reason.

Importing this module has NO side effects.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Awaitable, Callable, Iterable, Optional, Sequence

__all__ = ["PeriodicTask", "PeriodicTaskGroup"]

# ``on_error`` policy tokens.
ON_ERROR_LOG_CONTINUE = "log-continue"
ON_ERROR_LOG_RAISE = "log-raise"
_ON_ERROR_CHOICES = frozenset({ON_ERROR_LOG_CONTINUE, ON_ERROR_LOG_RAISE})

# Env-gate falsiness rule (documented + tested). A gate env var counts as
# "off" — the tick is SKIPPED — when it is unset OR its value, lower-cased and
# stripped, is one of these tokens. Anything else (e.g. "1", "true", "yes",
# "on", "anything") is truthy and the tick RUNS.
_FALSY_ENV_TOKENS = frozenset({"", "0", "false", "no", "off"})


def _env_gate_open(gate_env: Optional[str], environ) -> bool:
    """Return True if the gate is open (tick should run).

    A ``None`` gate is always open. Otherwise the env var's value is checked
    against :data:`_FALSY_ENV_TOKENS` (case-insensitive, whitespace-stripped);
    unset or falsy → closed (skip), anything else → open (run).
    """
    if gate_env is None:
        return True
    raw = environ.get(gate_env)
    if raw is None:
        return False
    return raw.strip().lower() not in _FALSY_ENV_TOKENS


class PeriodicTask:
    """A single supervised periodic loop.

    Parameters
    ----------
    fn:
        The work to run each tick. May be either a coroutine function
        (``async def``) — awaited directly on the event loop — or a plain
        sync/blocking callable — dispatched via :func:`asyncio.to_thread` so it
        NEVER blocks the loop. Detection is automatic
        (:func:`asyncio.iscoroutinefunction`); no flag needed.
    interval:
        Seconds between the *start* of consecutive ticks. Must be > 0.
    name:
        Human name used in every log line — makes a fail-loud traceback point
        at the right loop.
    gate_env:
        Optional env-var name. When given, each tick checks it and SKIPS the
        work (cheap no-op, loop keeps ticking) while the var is unset or falsy
        (``""``/``"0"``/``"false"``/``"no"``/``"off"``, case-insensitive). This
        lets a daemon disable a loop at runtime without a restart.
    on_error:
        ``"log-continue"`` (default) — a raising ``fn`` is logged LOUDLY and the
        loop keeps going. ``"log-raise"`` — log then propagate, killing the loop
        so a supervisor/group sees the failure. Never silently swallowed.
    initial_delay:
        Seconds to wait before the FIRST tick (default 0.0).
    jitter:
        If > 0, each inter-tick sleep is perturbed by a uniform random amount in
        ``[0, jitter)`` seconds. De-synchronises many loops that would otherwise
        thunder together. Default 0.0.
    logger:
        Where fail-loud output goes. Defaults to a module logger.
    clock / sleep:
        Time seams. ``clock`` is unused by the default loop (kept for symmetry
        and future backoff policies); ``sleep`` defaults to
        :func:`asyncio.sleep` and is the ONLY place the loop yields. Inject a
        fake to drive many ticks with zero real wall-clock cost.
    to_thread:
        Off-loop dispatch hook for sync ``fn`` (defaults to
        :func:`asyncio.to_thread`). Injectable so a test can assert the sync
        path was taken.
    rng:
        Random source for jitter (defaults to the module :mod:`random`). Inject
        for deterministic jitter in tests.
    environ:
        Mapping consulted for the env gate (defaults to :data:`os.environ`).
        Injectable so a test need not mutate the real process env.
    """

    def __init__(
        self,
        fn: Callable[[], object] | Callable[[], Awaitable[object]],
        *,
        interval: float,
        name: str,
        gate_env: Optional[str] = None,
        on_error: str = ON_ERROR_LOG_CONTINUE,
        initial_delay: float = 0.0,
        jitter: float = 0.0,
        logger: Optional[logging.Logger] = None,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], Awaitable[None]]] = None,
        to_thread: Optional[Callable[..., Awaitable[object]]] = None,
        rng: Optional[random.Random] = None,
        environ=None,
    ) -> None:
        if interval <= 0:
            raise ValueError(f"interval must be > 0, got {interval!r}")
        if initial_delay < 0:
            raise ValueError(f"initial_delay must be >= 0, got {initial_delay!r}")
        if jitter < 0:
            raise ValueError(f"jitter must be >= 0, got {jitter!r}")
        if on_error not in _ON_ERROR_CHOICES:
            raise ValueError(
                f"on_error must be one of {sorted(_ON_ERROR_CHOICES)}, "
                f"got {on_error!r}"
            )

        self._fn = fn
        self.interval = float(interval)
        self.name = name
        self.gate_env = gate_env
        self.on_error = on_error
        self.initial_delay = float(initial_delay)
        self.jitter = float(jitter)
        self._log = logger or logging.getLogger(f"scitex_dev.runtime.periodic.{name}")
        self._clock = clock or __import__("time").monotonic
        self._sleep = sleep or asyncio.sleep
        self._to_thread = to_thread or asyncio.to_thread
        self._rng = rng or random
        self._environ = environ if environ is not None else os.environ
        self._is_coro = asyncio.iscoroutinefunction(fn)

    # ------------------------------------------------------------------ #
    # The supervised loop                                                #
    # ------------------------------------------------------------------ #
    async def run(self) -> None:
        """Drive the loop until cancelled.

        Await this from a task/group. It sleeps ``initial_delay`` (if any), then
        loops: sleep ``interval`` (+ jitter), run one tick, forever. On
        :class:`asyncio.CancelledError` it stops PROMPTLY and RE-RAISES (never
        swallowed — swallowing breaks structured cancellation). ``fn`` errors are
        handled by a SEPARATE ``except Exception`` that never sees
        ``CancelledError``.
        """
        try:
            if self.initial_delay > 0:
                await self._sleep(self.initial_delay)
            else:
                # Fire the first tick immediately (still cancellable on entry).
                await self._tick()
                await self._sleep_between()
            while True:
                await self._tick()
                await self._sleep_between()
        except asyncio.CancelledError:
            # Structured-cancellation contract: stop promptly, run teardown,
            # and RE-RAISE. Do NOT convert this into a normal return.
            self._log.debug("PeriodicTask %s cancelled — stopping", self.name)
            raise

    async def _sleep_between(self) -> None:
        delay = self.interval
        if self.jitter > 0:
            delay += self._rng.uniform(0.0, self.jitter)
        await self._sleep(delay)

    async def _tick(self) -> None:
        """Run exactly one gated, fail-loud tick.

        CancelledError raised *inside* the tick propagates out untouched (it is
        NOT an ``Exception`` subclass on modern Python and is not caught here).
        """
        if not _env_gate_open(self.gate_env, self._environ):
            # Gate closed → cheap no-op; the loop keeps ticking so re-enabling
            # the env var resumes work with no restart.
            return
        try:
            if self._is_coro:
                await self._fn()
            else:
                await self._to_thread(self._fn)
        except asyncio.CancelledError:
            # Belt-and-suspenders: never let the fail-loud handler below swallow
            # a cancellation that surfaced through fn / to_thread.
            raise
        except Exception:  # noqa: BLE001 — fail LOUD, deliberately broad.
            self._log.exception("PeriodicTask %s tick failed", self.name)
            if self.on_error == ON_ERROR_LOG_RAISE:
                raise
            # ON_ERROR_LOG_CONTINUE: logged above, keep looping.


class PeriodicTaskGroup:
    """Start N :class:`PeriodicTask` s together and cancel them all on shutdown.

    This is the daemon-owns-its-loops surface. Typical use::

        group = PeriodicTaskGroup([liveness, reconciler, watchdog])
        await group.start()
        ...                     # daemon runs
        await group.stop()      # cancels every member, waits for teardown

    or as an async context manager::

        async with PeriodicTaskGroup([...]) as group:
            await group.wait()  # until a member with on_error="log-raise" dies

    Cancellation is cooperative and complete: every member's
    :class:`asyncio.CancelledError` is delivered and awaited, so no loop is left
    dangling.
    """

    def __init__(self, tasks: Iterable[PeriodicTask] = ()) -> None:
        self._tasks: list[PeriodicTask] = list(tasks)
        self._running: list[asyncio.Task] = []

    def add(self, task: PeriodicTask) -> None:
        """Register a task before :meth:`start`. Raises if already running."""
        if self._running:
            raise RuntimeError("cannot add tasks to an already-started group")
        self._tasks.append(task)

    @property
    def tasks(self) -> Sequence[PeriodicTask]:
        return tuple(self._tasks)

    async def start(self) -> None:
        """Schedule every member on the running loop. Idempotent-guarded."""
        if self._running:
            raise RuntimeError("group already started")
        loop = asyncio.get_event_loop()
        self._running = [
            loop.create_task(t.run(), name=f"periodic:{t.name}") for t in self._tasks
        ]

    async def stop(self) -> None:
        """Cancel every member and wait for all to finish teardown.

        Idempotent: safe to call when never started or already stopped.
        Gathers with ``return_exceptions=True`` so one member's teardown error
        (or its expected :class:`asyncio.CancelledError`) never masks another's.
        """
        if not self._running:
            return
        for t in self._running:
            t.cancel()
        await asyncio.gather(*self._running, return_exceptions=True)
        self._running = []

    async def wait(self) -> None:
        """Block until the FIRST member finishes (normally only a log-raise death).

        Cancels the remaining members before returning so a single loop crash
        tears the whole group down cleanly. Re-raises the offending member's
        exception (never a bare :class:`asyncio.CancelledError`).
        """
        if not self._running:
            return
        done, _pending = await asyncio.wait(
            self._running, return_when=asyncio.FIRST_COMPLETED
        )
        try:
            for d in done:
                exc = d.exception()
                if exc is not None:
                    raise exc
        finally:
            await self.stop()

    async def __aenter__(self) -> "PeriodicTaskGroup":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()


# EOF
