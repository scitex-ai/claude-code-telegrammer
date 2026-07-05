#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``ensure_service`` — guarantee a ``kind="service"`` daemon stays alive.

Consumed via ``scitex-dev service ensure <name>``. A leaf declares a
long-running daemon as a ``kind="service"`` JobSpec (via the
``scitex_dev.jobs`` entry-point federation); scitex-dev owns keeping it
running so leaves never hand-roll their own supervisor.

Two backends, selected at runtime by whether a systemd ``--user``
manager is reachable:

1. **systemd --user** — write the ``.service`` unit (via the existing
   :func:`scitex_dev.jobs._systemd.build_service_unit` builder) into
   ``~/.config/systemd/user/``, then ``daemon-reload`` +
   ``enable --now``. Idempotent — re-running rewrites the unit and
   re-enables (a no-op if already active).

2. **respawn-loop fallback** — for hosts with no user-systemd. Write the
   keep-alive script (:mod:`scitex_dev.jobs._respawn`) under
   ``~/.scitex/<pkg>/runtime/``, drop the alive flag, and launch the
   loop detached. Idempotent via the pidfile — if a live supervisor is
   already running we leave it alone.

The ``systemctl`` calls and the detached launch are the ONLY impure
parts; both are injected as callables (``run_fn`` / ``spawn_fn``) and
the availability probe (``systemd_available_fn``) is injected too, so
tests exercise backend selection + the install sequence WITHOUT a real
``systemctl`` or a real detached process.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import JobSpec, jobs_of_kind
from . import _respawn, _systemd

#: Injected-callable types.
RunFn = Callable[[list[str]], "subprocess.CompletedProcess"]
SpawnFn = Callable[[Path, Path], int]
AvailFn = Callable[[], bool]


@dataclass(frozen=True)
class EnsureResult:
    """Outcome of :func:`ensure_service` — what backend ran + artefacts."""

    name: str
    backend: str  # "systemd" | "respawn"
    unit_path: Path | None = None
    script_path: Path | None = None
    already_running: bool = False
    messages: tuple[str, ...] = ()


def find_service_job(
    name: str, **discover_kwargs
) -> JobSpec:
    """Resolve the named ``kind="service"`` JobSpec from the federation.

    Uses the exact same discovery path (:func:`jobs_of_kind`) the
    cron/ecosystem code uses, so the daemon a leaf declares is found the
    same way everywhere. Raises ``KeyError`` when no service job matches.
    """
    for job in jobs_of_kind("service", **discover_kwargs):
        if job.name == name:
            return job
    raise KeyError(
        f"no kind='service' JobSpec named {name!r} in the "
        f"scitex_dev.jobs federation"
    )


def systemd_user_available(
    *, run_fn: RunFn | None = None
) -> bool:
    """Return True if a systemd ``--user`` manager is reachable.

    Probe = ``systemctl --user is-system-running`` returns *anything*
    (even ``degraded``/exit!=0 still means the manager answered). A
    missing binary or a "Failed to connect to bus" is treated as
    unavailable → respawn fallback. ``run_fn`` is a test seam.
    """
    if run_fn is None:
        if shutil.which("systemctl") is None:
            return False
        run_fn = _default_run

    try:
        proc = run_fn(["systemctl", "--user", "is-system-running"])
    except (FileNotFoundError, OSError):
        return False
    # A live user manager prints a state word (running/degraded/…) even
    # when exit code is non-zero. "Failed to connect to bus" goes to
    # stderr with empty stdout → treat as unavailable.
    out = (getattr(proc, "stdout", "") or "").strip()
    return bool(out)


def _default_run(argv: list[str]) -> "subprocess.CompletedProcess":
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=30, check=False
    )


def ensure_service(
    name: str,
    *,
    home: Path | None = None,
    systemd_available_fn: AvailFn | None = None,
    run_fn: RunFn | None = None,
    spawn_fn: SpawnFn | None = None,
    discover_kwargs: dict | None = None,
) -> EnsureResult:
    """Ensure the ``kind="service"`` daemon ``name`` is installed + running.

    Backend selection: if ``systemd_available_fn()`` (default: the real
    :func:`systemd_user_available` probe) reports a user manager, install
    the systemd unit; otherwise fall back to the respawn loop. All three
    seams (``systemd_available_fn`` / ``run_fn`` / ``spawn_fn``) default
    to their real implementations and exist so tests never touch a real
    ``systemctl`` or spawn a real background process.
    """
    job = find_service_job(name, **(discover_kwargs or {}))

    avail = systemd_available_fn
    if avail is None:
        avail = lambda: systemd_user_available(run_fn=run_fn)  # noqa: E731

    if avail():
        return _ensure_via_systemd(job, home=home, run_fn=run_fn)
    return _ensure_via_respawn(job, home=home, spawn_fn=spawn_fn)


def _ensure_via_systemd(
    job: JobSpec, *, home: Path | None, run_fn: RunFn | None
) -> EnsureResult:
    """systemd --user backend: write unit, daemon-reload, enable --now."""
    run = run_fn or _default_run
    base = home if home is not None else Path.home()
    unit_dir = base / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_name = _systemd.systemd_unit_name(job)  # <name>.service
    unit_path = unit_dir / unit_name
    unit_path.write_text(_systemd.build_service_unit(job), encoding="utf-8")

    msgs = [f"wrote {unit_path}"]
    for argv in (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", unit_name],
    ):
        proc = run(argv)
        rc = getattr(proc, "returncode", 0)
        msgs.append(f"{' '.join(argv)} -> rc={rc}")

    return EnsureResult(
        name=job.name,
        backend="systemd",
        unit_path=unit_path,
        messages=tuple(msgs),
    )


def _ensure_via_respawn(
    job: JobSpec, *, home: Path | None, spawn_fn: SpawnFn | None
) -> EnsureResult:
    """Respawn-loop backend: write script + flag, launch detached.

    Idempotent: if the pidfile names a live process we assume the
    supervisor is already up and do NOT start a second one.
    """
    rt = _respawn.runtime_dir(job, home=home)
    (rt / "logs").mkdir(parents=True, exist_ok=True)

    pidf = _respawn.pidfile_path(job, home=home)
    if _pidfile_alive(pidf):
        return EnsureResult(
            name=job.name,
            backend="respawn",
            script_path=_respawn.script_path(job, home=home),
            already_running=True,
            messages=(f"supervisor already running (pidfile {pidf})",),
        )

    script = _respawn.script_path(job, home=home)
    script.write_text(
        _respawn.build_respawn_script(job, home=home), encoding="utf-8"
    )
    script.chmod(0o755)

    flag = _respawn.flag_path(job, home=home)
    flag.write_text("alive\n", encoding="utf-8")

    logf = _respawn.log_path(job, home=home)
    spawn = spawn_fn or _default_spawn
    pid = spawn(script, logf)

    return EnsureResult(
        name=job.name,
        backend="respawn",
        script_path=script,
        messages=(
            f"wrote {script}",
            f"wrote alive flag {flag}",
            f"launched respawn supervisor pid={pid}",
        ),
    )


def _pidfile_alive(pidf: Path) -> bool:
    """Return True if ``pidf`` names a currently-live process."""
    try:
        pid = int(pidf.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # The pid exists but is owned by another user — still alive.
        return True
    except OSError:
        return False
    return True


def _default_spawn(script: Path, logf: Path) -> int:
    """Launch ``script`` detached (setsid) and return its PID.

    ``setsid`` + redirected stdio fully detaches the loop from this
    process so it survives ``ensure`` returning — same shape as the
    Spartan launcher's ``setsid nohup``.
    """
    logf.parent.mkdir(parents=True, exist_ok=True)
    with open(logf, "a", encoding="utf-8") as log_fh:
        proc = subprocess.Popen(
            ["/bin/bash", str(script)],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # setsid: detach from our session
        )
    return proc.pid


__all__ = [
    "EnsureResult",
    "ensure_service",
    "find_service_job",
    "systemd_user_available",
]


# EOF
