#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``spartan-conn-monitor`` cron job — watch the ywatanabe user's footprint on
the Spartan login nodes so a regression of the 2026-06-17 admin incident (440+
SSH connections / ssh-agents, login-node ``du``) is caught EARLY — before the
HPC admin notices.

Per cycle it ssh's (light, multiplexed) to each Spartan login node and records,
for the ``ywatanabe`` user: ssh-agents, ``who`` login sessions, total procs,
``srun`` clients. It appends a timestamped TSV row per node to
``~/.scitex/dev/runtime/spartan-conn-monitor.tsv`` and, if any node crosses a
threshold, fires a LOUD notification AND a phone call (operator directive: "call
me when threshold reached").

Why these metrics (countable as a non-root user)
------------------------------------------------
  * ``ssh_agents``  — the headline 440-incident metric; should be ~0 (PRIMARY).
  * ``total_procs`` — secondary safety; alerts only at an extreme level so normal
                      other-agent srun research load (~90) does not false-alarm.
``who`` under-counts (our agent ssh is non-interactive → no utmp entry) and
netstat connection counts are root-only, so ``total_procs`` is the best load
proxy available without root.

Robustness contract
-------------------
This runs unattended from cron and must never crash the cron loop: an
unreachable login node is logged as ``NA`` and skipped; a notification failure is
swallowed. A threshold breach exits non-zero (so the cron log marks the tick) but
the per-node loop always completes first.

Seams (per PA-306 / STX-NM*)
----------------------------
``ssh_runner`` (node → ``(rc, stdout)``), ``notifier`` / ``caller`` (message →
None), ``now`` (→ ISO timestamp str) and ``tsv_path`` are injectable so tests
pass real fakes — no monkeypatching of ``subprocess``.
"""

from __future__ import annotations

import datetime as _dt
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

LOGIN_NODES = (
    "spartan-login1.hpc.unimelb.edu.au",
    "spartan-login2.hpc.unimelb.edu.au",
    "spartan-login3.hpc.unimelb.edu.au",
)

# Alert thresholds. ssh-agents was 440 in the incident; ~0 is healthy. The proc
# ceiling is deliberately high so legitimate other-agent srun load never pages.
AGENT_MAX = 15
PROC_MAX = 250
# Per-login-node ``srun`` client ceiling. The HPC admin's guidance is ~20
# connections per login node; each persistent CI runner used to leave one
# ``srun`` CLIENT there (the SSH-vector that prompted the 'ci runner up' rewrite
# to launch on the compute node instead). Page at 50 — comfortably above normal
# transient other-agent srun research load, yet well BELOW a breach so we act
# before the admin notices. The launch fix should keep this near 0 going forward;
# a climb back toward 50 means a regression (a runner launched the old way, or
# orphaned srun clients piling up).
SRUN_MAX = 50

# SSH connection MULTIPLEXING — one reused master per host, 30s persist, a
# dedicated control path (kept apart from interactive sockets). Mirrors
# scitex_dev.ci.runner.config.SSH_MUX_OPTS — the runner-side lesson from the same
# incident: never open a fresh login-node connection per call.
_SSH_OPTS = [
    "-o",
    "ConnectTimeout=10",
    "-o",
    "BatchMode=yes",
    "-o",
    "ControlMaster=auto",
    "-o",
    "ControlPersist=30",
    "-o",
    "ControlPath=~/.ssh/.cm-scitex-mon-%C",
]

# Remote counter — user hardcoded to ywatanabe (shared account), so no nested
# quotes to mangle; sequential vars then one echo. `pgrep -c` already prints 0
# on no-match (do NOT add `|| echo 0` — it duplicates + shifts the fields).
_REMOTE = (
    "a=$(pgrep -u ywatanabe -c ssh-agent 2>/dev/null); "
    "w=$(who 2>/dev/null | grep -c ywatanabe); "
    "p=$(ps -u ywatanabe --no-headers 2>/dev/null | wc -l); "
    "s=$(pgrep -u ywatanabe -xc srun 2>/dev/null); "
    'echo "${a:-0} ${w:-0} ${p:-0} ${s:-0}"'
)


def _state_dir() -> Path:
    """Canonical scitex-dev local-state dir (honours ``$SCITEX_DIR``)."""
    base = os.environ.get("SCITEX_DIR") or os.path.join(
        os.path.expanduser("~"), ".scitex"
    )
    return Path(base) / "dev"


def tsv_path() -> Path:
    """Path of the append-only metrics log (runtime/ per the local-state rule)."""
    return _state_dir() / "runtime" / "spartan-conn-monitor.tsv"


@dataclass
class NodeReading:
    """One login node's counts for one cycle (NA fields = unreachable)."""

    node: str
    ssh_agents: int | None
    who_sessions: int | None
    total_procs: int | None
    srun: int | None
    reachable: bool


@dataclass
class MonitorResult:
    """Outcome of one ``spartan-conn-monitor`` cycle."""

    readings: list[NodeReading] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)


def _default_ssh_runner(node: str) -> tuple[int, str]:
    """Real ``ssh <opts> <node> <remote-counter>`` invocation (tests fake this)."""
    proc = subprocess.run(
        ["ssh", *_SSH_OPTS, node, _REMOTE],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return proc.returncode, proc.stdout


def _default_notifier(message: str) -> None:
    """Audio notification (error level). Best-effort; never raises."""
    notif = os.path.join(os.path.expanduser("~"), ".venv", "bin", "scitex-notification")
    try:
        subprocess.run(
            [
                notif,
                "send-notification",
                "--backend",
                "audio",
                "--level",
                "error",
                message,
            ],
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _default_caller(message: str) -> None:
    """Phone call (error level). Best-effort; never raises."""
    notif = os.path.join(os.path.expanduser("~"), ".venv", "bin", "scitex-notification")
    try:
        subprocess.run(
            [notif, "call", "--level", "error", message],
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _parse(stdout: str) -> tuple[int, int, int, int] | None:
    """Parse the remote ``echo "a w p s"`` into 4 ints, or None if malformed."""
    parts = stdout.split()
    if len(parts) != 4:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
    except ValueError:
        return None


def _check_thresholds(r: NodeReading) -> list[str]:
    """Alerts raised by one reading (empty if within bounds / unreachable)."""
    out: list[str] = []
    short = r.node.split(".")[0]
    if r.ssh_agents is not None and r.ssh_agents > AGENT_MAX:
        out.append(f"{short}:ssh-agents={r.ssh_agents}(>{AGENT_MAX})")
    if r.srun is not None and r.srun > SRUN_MAX:
        out.append(f"{short}:srun={r.srun}(>{SRUN_MAX})")
    if r.total_procs is not None and r.total_procs > PROC_MAX:
        out.append(f"{short}:procs={r.total_procs}(>{PROC_MAX})")
    return out


def _append_tsv(path: Path, ts: str, r: NodeReading) -> None:
    """Append one row; create the file with a header on first write. Best-effort."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8") as fh:
            if new:
                fh.write(
                    "timestamp\tnode\tssh_agents\twho_sessions\ttotal_procs\tsrun\n"
                )
            short = r.node.split(".")[0]

            def _c(v):
                return "NA" if v is None else str(v)

            fh.write(
                f"{ts}\t{short}\t{_c(r.ssh_agents)}\t{_c(r.who_sessions)}\t"
                f"{_c(r.total_procs)}\t{_c(r.srun)}\n"
            )
    except OSError:
        pass


def run_once(
    *,
    ssh_runner: Callable[[str], tuple[int, str]] | None = None,
    notifier: Callable[[str], None] | None = None,
    caller: Callable[[str], None] | None = None,
    now: Callable[[], str] | None = None,
    path: Path | None = None,
    out=None,
) -> MonitorResult:
    """Run one monitor cycle: poll each login node, log, alert on threshold.

    Returns a :class:`MonitorResult`. On any threshold breach, fires the
    notifier + caller once with a combined message. Never raises (cron-safe);
    the ``exec`` dispatcher decides the exit code from ``result.alerts``.
    """
    if out is None:
        out = sys.stdout
    runner = ssh_runner or _default_ssh_runner
    notify = notifier or _default_notifier
    call = caller or _default_caller
    clock = now or (lambda: _dt.datetime.now().isoformat(timespec="seconds"))
    log_path = path if path is not None else tsv_path()

    ts = clock()
    result = MonitorResult()
    summary_bits: list[str] = []

    for node in LOGIN_NODES:
        short = node.split(".")[0]
        try:
            rc, stdout = runner(node)
        except (OSError, subprocess.SubprocessError):
            rc, stdout = 1, ""
        parsed = _parse(stdout) if rc == 0 else None
        if parsed is None:
            reading = NodeReading(node, None, None, None, None, reachable=False)
            summary_bits.append(f"{short}=unreachable")
        else:
            a, w, p, s = parsed
            reading = NodeReading(node, a, w, p, s, reachable=True)
            summary_bits.append(f"{short}:agents={a},who={w},proc={p},srun={s}")
        result.readings.append(reading)
        _append_tsv(log_path, ts, reading)
        result.alerts.extend(_check_thresholds(reading))

    print(f"spartan-conn-monitor [{ts}] " + " ".join(summary_bits), file=out)

    if result.alerts:
        msg = (
            "Spartan login-node threshold crossed (ywatanabe user): "
            + " ".join(result.alerts)
            + " — ssh hygiene regressing; act before the admin notices"
        )
        notify(msg)
        call(msg)
        print(f"spartan-conn-monitor: ALERT {' '.join(result.alerts)}", file=out)

    return result


# EOF
