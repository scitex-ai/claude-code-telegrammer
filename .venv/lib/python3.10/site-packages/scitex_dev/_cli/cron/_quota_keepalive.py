#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``quota-keepalive`` cron job — pre-start the rolling 5-hour quota window.

Claude's usage quota is a *rolling 5-hour window*: the window opens on the
first turn and closes 5 hours later. If real work begins cold, you burn a
fresh 5-hour window starting from the first real turn. By firing a trivial
"hello" turn every 2.5 hours, the window is always *partway elapsed* when
real work starts — so a single calendar day overlaps roughly two usable
5-hour windows instead of one.

Self-gating design (why not a single cron interval)
----------------------------------------------------
2.5 hours is **not** expressible as one 5-field cron schedule (cron has no
"every 150 minutes" — ``*/150`` in the minute field is invalid, and the
minute field caps at 59). Rather than split into multiple crontab lines
(e.g. ``30 0,5,10,15,20 * * *`` plus offsets, which drifts and is hard to
reason about), we install **one** clean line at ``*/30 * * * *`` and gate
the body here: fire the keepalive only when at least
``KEEPALIVE_INTERVAL_MIN`` (150) minutes have elapsed since the last fire.

The last-fire time is tracked in a timestamp file under the canonical
scitex-dev local-state dir (``~/.scitex/dev/quota-keepalive.last``). On
each 30-minute tick we read it, compare against ``now``, and either fire
(and rewrite the file) or skip. This yields exact 2.5-hour spacing with a
single, legible schedule.

Robustness contract
--------------------
This runs unattended from cron. It must never crash the cron loop:

  * If ``claude`` is missing or returns non-zero, we log the outcome and
    return a result whose ``error`` is set — the ``exec`` dispatcher exits
    0 anyway (a keepalive miss is recoverable; the next tick retries).
  * The timestamp file is best-effort: a write failure is logged but does
    not prevent the keepalive from having fired.

Seams (per PA-306 / STX-NM*)
----------------------------
``now`` (a ``Callable[[], float]`` returning epoch seconds) and
``claude_runner`` (a ``Callable[[str], CompletedProcess]``) are keyword
arguments on every function so tests pass real fakes — no monkeypatching
of ``time`` or ``subprocess``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# The keepalive cadence. 150 minutes == 2.5 hours. The crontab line ticks
# every 30 minutes (see _jobs.py); the body fires on the first tick at or
# past this many minutes since the last fire.
KEEPALIVE_INTERVAL_MIN: int = 150

# The cheapest model — the turn content is irrelevant; we only need a turn
# to open / refresh the rolling quota window.
KEEPALIVE_MODEL: str = "claude-haiku-4-5"

# The trivial prompt body.
KEEPALIVE_PROMPT: str = "hello"


def _state_dir() -> Path:
    """Return the canonical scitex-dev local-state dir (``~/.scitex/dev``).

    Honours ``$SCITEX_DIR`` (the ecosystem-wide relocation lever) so the
    keepalive timestamp moves with the rest of user state when set.
    """
    base = os.environ.get("SCITEX_DIR") or os.path.join(
        os.path.expanduser("~"), ".scitex"
    )
    return Path(base) / "dev"


def timestamp_path() -> Path:
    """Path of the last-fire timestamp file."""
    return _state_dir() / "quota-keepalive.last"


def _read_last_fire(path: Path) -> float | None:
    """Return the epoch-seconds float in ``path``, or None if absent/garbage.

    Absent file or unparseable content both mean "never fired" → fire now.
    A read error must never crash the cron loop, so any exception degrades
    to None (treat as stale).
    """
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _write_last_fire(path: Path, when: float) -> bool:
    """Record ``when`` (epoch seconds) as the last-fire time. Best-effort.

    Returns True on success, False on any OS error. The keepalive may have
    fired even when this returns False — the worst case is an early re-fire
    on the next tick, which is harmless.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{when:.6f}\n", encoding="utf-8")
        return True
    except OSError:
        return False


def is_due(
    last_fire: float | None,
    now: float,
    *,
    interval_min: int = KEEPALIVE_INTERVAL_MIN,
) -> bool:
    """True iff a keepalive is due.

    Due when there is no recorded last fire, or at least ``interval_min``
    minutes have elapsed since it. Pure function — no I/O, no clock read —
    so the self-gate logic is trivially testable.
    """
    if last_fire is None:
        return True
    return (now - last_fire) >= interval_min * 60


@dataclass(frozen=True)
class KeepaliveResult:
    """Outcome of one ``quota-keepalive`` exec-body invocation."""

    fired: bool
    skipped_reason: str | None = None
    error: str | None = None
    output: str = ""


def _default_claude_runner(prompt: str) -> subprocess.CompletedProcess:
    """Real ``claude -p`` invocation. Tests pass their own fake.

    Reads the host's ``~/.claude/.credentials.json`` automatically (the
    default claude auth path) — we deliberately do NOT pass an API key so
    no secret is hardcoded or logged.

    Raises ``FileNotFoundError`` if ``claude`` is not on PATH; the caller
    catches it and degrades to a logged error (no crash).
    """
    return subprocess.run(
        ["claude", "-p", prompt, "--model", KEEPALIVE_MODEL],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def run_once(
    *,
    now: Callable[[], float] | None = None,
    claude_runner: Callable[[str], subprocess.CompletedProcess] | None = None,
    ts_path: Path | None = None,
    out=None,
) -> KeepaliveResult:
    """Run one quota-keepalive pass: gate, fire if due, record the fire.

    Returns a :class:`KeepaliveResult` so callers (and tests) can inspect
    what happened. Prints a one-line progress message to ``out`` (default
    ``sys.stdout``) so the cron log records each tick's decision.

    The clock (``now``) and the claude invocation (``claude_runner``) are
    injectable seams; everything else is real I/O against ``ts_path``.
    """
    if out is None:
        out = sys.stdout
    clock = now or time.time
    runner = claude_runner or _default_claude_runner
    path = ts_path if ts_path is not None else timestamp_path()

    current = clock()
    last = _read_last_fire(path)

    if not is_due(last, current):
        elapsed_min = (current - (last or current)) / 60.0
        reason = (
            f"not due ({elapsed_min:.0f} min since last fire; "
            f"need {KEEPALIVE_INTERVAL_MIN})"
        )
        print(f"quota-keepalive: skip — {reason}", file=out)
        return KeepaliveResult(fired=False, skipped_reason=reason)

    # Due. Fire the trivial turn. Any failure here is logged and returned
    # as an error, but the exec dispatcher still exits 0 (a miss is
    # recoverable — the next tick retries).
    try:
        r = runner(KEEPALIVE_PROMPT)
    except FileNotFoundError:
        msg = "`claude` not found on PATH"
        print(f"quota-keepalive: error — {msg}", file=out)
        return KeepaliveResult(fired=False, error=msg)
    except Exception as exc:  # stx-allow: fallback (reason: never crash cron)
        msg = f"claude invocation raised: {exc}"
        print(f"quota-keepalive: error — {msg}", file=out)
        return KeepaliveResult(fired=False, error=msg)

    output = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        msg = f"claude exited rc={r.returncode}: {output.strip()[:200]}"
        print(f"quota-keepalive: error — {msg}", file=out)
        return KeepaliveResult(fired=False, error=msg, output=output)

    # Success: record the fire time so the next 30-min ticks gate until
    # the interval re-elapses.
    wrote = _write_last_fire(path, current)
    if not wrote:
        print(
            f"quota-keepalive: warn — fired but failed to write {path}",
            file=out,
        )
    print(
        f"quota-keepalive: fired keepalive turn (model={KEEPALIVE_MODEL})",
        file=out,
    )
    return KeepaliveResult(fired=True, output=output)


# EOF
