#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure builders for systemd user ``.service`` / ``.timer`` unit files.

Two shapes, selected by ``JobSpec.kind``:

* ``kind="timer"`` — oneshot ``.service`` + persistent ``.timer``.
  Format mirrors scitex-agent-container's
  ``scripts/systemd/sac-accounts-refresh.{service,timer}`` reference:
  ``Type=oneshot``, journal logging, ``Persistent=true`` timer, a boot
  catch-up via ``OnBootSec``, and a recurring ``OnUnitActiveSec``
  cadence.

* ``kind="service"`` — long-running ``.service`` only (no timer).
  ``Type=simple`` + ``Restart=<policy>``. Used by long-running
  user-space units (the 8051 scitex-todo dashboard, a long-poll
  listener, etc.). ``OnBootSec`` becomes a startup delay implemented
  via ``ExecStartPre=/bin/sleep <N>`` (timers are the only systemd
  mechanism that expose ``OnBootSec`` directly).

The functions here are pure (JobSpec in, string out) so they are
trivial to unit-test; the CLI layer
(``_cli/ecosystem/_cmds/_jobs_systemd``) handles filesystem writes
under ``~/.config/systemd/user/``.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
import warnings
from pathlib import Path

from .. import jobs as _jobs

DEFAULT_ON_BOOT_SEC = "15min"
DEFAULT_ON_UNIT_ACTIVE_SEC = "1h"

# Documentation URL stamped into generated units (operator breadcrumb).
_DOC_URL = "https://github.com/ywatanabe1989/scitex-dev"


def derive_on_unit_active_sec(schedule: str) -> str:
    """Derive an ``OnUnitActiveSec`` from a 5-field cron ``schedule``.

    Best-effort: this is only used when a job declares no explicit
    ``on_unit_active_sec``. We read the minute and hour fields and map a
    handful of common ``*/N`` step forms to a duration; anything we
    don't recognise falls back to ``DEFAULT_ON_UNIT_ACTIVE_SEC``.
    """
    fields = schedule.split()
    if len(fields) != 5:
        return DEFAULT_ON_UNIT_ACTIVE_SEC
    minute, hour = fields[0], fields[1]

    # "*/N * * * *"  -> every N minutes
    if minute.startswith("*/") and hour == "*":
        n = _safe_int(minute[2:])
        if n:
            return f"{n}min"
    # "M */N * * *"  -> every N hours
    if hour.startswith("*/"):
        n = _safe_int(hour[2:])
        if n:
            return f"{n}h"
    # "M H * * *"    -> a fixed daily time
    if minute.isdigit() and hour.isdigit():
        return "1d"
    return DEFAULT_ON_UNIT_ACTIVE_SEC


def _safe_int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


def _on_boot_sec_to_seconds(value: str) -> int:
    """Best-effort parse of a systemd duration string into integer seconds.

    Recognises the small set of suffixes we actually use
    (``s`` / ``min`` / ``h``). Anything we don't recognise returns
    ``0`` so ``ExecStartPre=/bin/sleep 0`` is a harmless no-op rather
    than a unit-write failure.
    """
    text = value.strip().lower()
    if text.endswith("min"):
        n = _safe_int(text[:-3])
        return (n or 0) * 60
    if text.endswith("h"):
        n = _safe_int(text[:-1])
        return (n or 0) * 3600
    if text.endswith("s"):
        n = _safe_int(text[:-1])
        return n or 0
    n = _safe_int(text)
    return n or 0


def _interpreter_bindir() -> Path:
    """Return ``Path(sys.executable).parent`` — the bin/ holding sibling
    console scripts for the interpreter currently running this process.

    Indirection exists so tests can monkeypatch it without having to
    relocate the real interpreter.
    """
    return Path(sys.executable).resolve().parent


def resolve_execstart(
    command: str,
    *,
    which=shutil.which,
    interpreter_bindir=_interpreter_bindir,
) -> str:
    """Return an ``ExecStart=`` value with the first token absolutised.

    systemd ``--user`` services run under a deliberately minimal PATH
    (``/usr/local/bin:/usr/bin:/bin``) that excludes the operator's
    Python venv and most ecosystem installs. If we emit a relative
    command name like ``scitex-todo board --port 8051`` the unit fails
    to start with ``status=127/EXEC`` (command not found) and any
    leaf service silently flaps.

    Resolution rules (tried in order — first match wins):

    1. **Interpreter sibling-bin** — ``Path(sys.executable).parent / head``.
       The process that *writes* the unit is the same interpreter that
       installed the console scripts. Its sibling ``bin/`` therefore
       reliably holds ``scitex-todo``, ``scitex-dev``, ``sac``, etc.,
       even when ``ecosystem up`` was invoked via the venv's absolute
       interpreter (no ``activate``) and so the ambient PATH lacks
       the venv's ``bin/`` (the live bug observed on ywata-note-win,
       where ``scitex-todo.wake-watcher.service`` was written with
       ``ExecStart=/usr/bin/env scitex-todo`` and crash-looped at
       ``status=127`` for ~12 h because systemd user PATH lacks
       ``~/.env-3.11/bin``).
    2. **PATH lookup** — :func:`shutil.which` against the ambient PATH.
       Catches operator binaries installed outside the interpreter's
       bin (``/usr/local/bin/...``, ``~/.local/bin/...``, etc.).
    3. **/usr/bin/env fallback** — last resort. Emits a *loud*
       :class:`UserWarning` so the bring-up log makes it obvious the
       resolution missed; the unit will still fail to start with
       ``status=127`` under systemd's minimal PATH, but the operator
       has a breadcrumb.

    Pass-throughs:

    * If the first token is already absolute (starts with ``/``), pass
      through unchanged — the leaf has been explicit.
    * Empty ``command`` returns ``command`` verbatim.

    Args/tokens are preserved verbatim via ``shlex``-style splitting
    + re-joining so a quoted arg with spaces survives the round-trip.

    The ``which`` and ``interpreter_bindir`` keywords are test seams
    (fake-callables); the production defaults are :func:`shutil.which`
    and :func:`_interpreter_bindir`.
    """
    tokens = shlex.split(command)
    if not tokens:
        return command
    head, *tail = tokens
    if head.startswith("/"):
        return command

    # 1. Interpreter sibling-bin probe — most reliable for console
    #    scripts installed alongside the running interpreter.
    try:
        candidate = interpreter_bindir() / head
    except Exception:  # pragma: no cover — defensive only
        candidate = None
    if candidate is not None and candidate.is_file() and os.access(candidate, os.X_OK):
        return shlex.join([str(candidate), *tail])

    # 2. PATH lookup.
    resolved = which(head)
    if resolved:
        return shlex.join([resolved, *tail])

    # 3. Fallback — emit a LOUD warning so a bring-up log makes the
    #    miss obvious. systemd will still fail with exec=127, but
    #    the operator has a clear breadcrumb instead of a silent flap.
    warnings.warn(
        f"resolve_execstart: could not resolve {head!r} via "
        f"sys.executable's bin ({Path(sys.executable).parent}) nor PATH; "
        f"falling back to '/usr/bin/env {head}'. The systemd user unit "
        f"will likely fail with status=127 because user PATH is minimal. "
        f"Install the binary in the interpreter's bin/ or on PATH before "
        f"running 'ecosystem up'.",
        UserWarning,
        stacklevel=2,
    )
    return f"/usr/bin/env {command}"


def build_service_unit(job: _jobs.JobSpec) -> str:
    """Return the ``.service`` unit text for ``job``.

    Branches on ``job.kind``:

    * ``"timer"`` → oneshot service triggered by the sibling ``.timer``.
    * ``"service"`` → long-running ``Type=simple`` with ``Restart=``
      from ``job.restart_policy``. ``on_boot_sec`` (if set) becomes an
      ``ExecStartPre=/bin/sleep <N>`` startup delay so the unit comes
      up gracefully N seconds after boot — the systemd Service idiom
      for "wait before starting" (Timers own ``OnBootSec`` directly;
      Services don't).
    """
    if job.kind == "service":
        return _build_long_running_service_unit(job)
    return _build_oneshot_service_unit(job)


def _build_oneshot_service_unit(job: _jobs.JobSpec) -> str:
    """Oneshot ``.service`` for ``kind="timer"`` jobs."""
    lines = [
        "[Unit]",
        f"Description={job.description or job.name}",
        f"Documentation={_DOC_URL}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=oneshot",
        f"ExecStart={resolve_execstart(job.command)}",
        "StandardOutput=journal",
        "StandardError=journal",
        "RemainAfterExit=no",
    ]
    if job.timeout_sec is not None:
        lines.append(f"TimeoutStartSec={job.timeout_sec}s")
    lines.append("")
    return "\n".join(lines)


def _build_long_running_service_unit(job: _jobs.JobSpec) -> str:
    """Long-running ``.service`` for ``kind="service"`` jobs.

    ``Restart=<policy>`` keeps the unit alive per the leaf's declared
    policy. An ``ExecStartPre=/bin/sleep <N>`` step implements
    ``on_boot_sec`` (systemd Services don't natively expose
    ``OnBootSec`` — that's a Timer-only knob — so we materialise the
    delay as a pre-exec sleep).

    Watchdog (opt-in). ``Restart=`` handles a *crash* (the process
    exits) but is blind to a *hang* (the process is alive but wedged).
    ``WatchdogSec`` closes that gap — BUT it does nothing unless the
    daemon calls ``sd_notify(WATCHDOG=1)`` on a cadence faster than the
    interval, under ``Type=notify``. If we emitted ``WatchdogSec`` for a
    plain ``Type=simple`` daemon that never pings, systemd would decide
    the daemon "timed out" every interval and kill+restart it forever —
    a restart-storm footgun strictly worse than no watchdog at all.

    Therefore the watchdog is emitted ONLY when the JobSpec explicitly
    sets ``watchdog_sec`` (the leaf is declaring "I send WATCHDOG=1
    pings"). In that case we switch the unit to ``Type=notify`` and add
    ``WatchdogSec=<N>s``. Otherwise the unit stays ``Type=simple`` and
    relies on ``Restart=`` alone.
    """
    use_watchdog = job.watchdog_sec is not None
    lines = [
        "[Unit]",
        f"Description={job.description or job.name}",
        f"Documentation={_DOC_URL}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        # Type=notify ONLY when a watchdog is requested — a Type=notify
        # unit whose ExecStart never calls sd_notify(READY=1) would sit
        # in "activating" until TimeoutStartSec and fail, so we must NOT
        # flip to notify for daemons that don't opt in.
        "Type=notify" if use_watchdog else "Type=simple",
    ]
    if job.on_boot_sec:
        seconds = _on_boot_sec_to_seconds(job.on_boot_sec)
        if seconds > 0:
            lines.append(f"ExecStartPre=/bin/sleep {seconds}")
    lines.extend(
        [
            f"ExecStart={resolve_execstart(job.command)}",
            "StandardOutput=journal",
            "StandardError=journal",
            f"Restart={job.restart_policy}",
        ]
    )
    if use_watchdog:
        # Guards hangs. The leaf MUST ping sd_notify(WATCHDOG=1) faster
        # than this or systemd will treat the daemon as hung and restart
        # it — see the opt-in caveat in the docstring above.
        lines.append(f"WatchdogSec={job.watchdog_sec}s")
    if job.restart_policy != "no":
        # Sensible default the operator can override at the systemctl
        # level. Keeps a runaway restart loop from melting CPU on a
        # broken leaf.
        lines.append("RestartSec=5s")
    if job.timeout_sec is not None:
        lines.append(f"TimeoutStartSec={job.timeout_sec}s")
    lines.extend(
        [
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    return "\n".join(lines)


def build_timer_unit(job: _jobs.JobSpec) -> str:
    """Return the ``.timer`` unit text for ``job`` (Persistent=true).

    Only meaningful for ``kind="timer"`` jobs. Calling this on a
    ``kind="service"`` job raises ``ValueError`` — services don't have
    timers; checking up-front avoids writing an inert timer file the
    operator would have to clean up later.
    """
    if job.kind != "timer":
        raise ValueError(
            f"build_timer_unit({job.name!r}): only kind='timer' has a timer; "
            f"got kind={job.kind!r}"
        )
    on_boot = job.on_boot_sec or DEFAULT_ON_BOOT_SEC
    on_active = job.on_unit_active_sec or derive_on_unit_active_sec(job.schedule)
    lines = [
        "[Unit]",
        f"Description=Timer for {job.name}",
        f"Documentation={_DOC_URL}",
        "",
        "[Timer]",
        f"OnBootSec={on_boot}",
        f"OnUnitActiveSec={on_active}",
        "Persistent=true",
        f"Unit={job.name}.service",
        "",
        "[Install]",
        "WantedBy=timers.target",
        "",
    ]
    return "\n".join(lines)


def systemd_unit_name(job: _jobs.JobSpec) -> str:
    """Return the systemctl enable target for ``job`` (``<name>.timer``
    for timer jobs, ``<name>.service`` for long-running services).
    """
    return f"{job.name}.timer" if job.kind == "timer" else f"{job.name}.service"


# EOF
