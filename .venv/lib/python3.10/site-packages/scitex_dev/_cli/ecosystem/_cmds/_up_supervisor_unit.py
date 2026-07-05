#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Supervisor systemd unit — the ONE artefact ``ecosystem up`` registers.

Extracted from ``_up.py`` to stay under the per-file line limit and to
keep the unit-text generator unit-testable without booting the rest of
the orchestrator. See module docstring on ``_up.py`` for the operator
policy this implements (post-2026-06-14 redesign: ONE collective
``scitex-dev-ecosystem.service`` instead of per-leaf units).

Public surface
--------------
* :data:`SUPERVISOR_UNIT_NAME` — the canonical filename.
* :func:`build_supervisor_unit_text` — generate the unit body with the
  absolute ``ExecStart=`` path resolved at call time (so test seams +
  PATH probes both work).
* :func:`write_supervisor_unit` — write the unit text to a directory.
  Idempotent; mkdir-parents.
"""

from __future__ import annotations

from pathlib import Path

# The systemd unit filename. ``scitex-dev-ecosystem`` chosen for symmetry
# with the old (now-deprecated) ``scitex-dev-ecosystem-reconcile.service``
# the operator was familiar with; the ``.service`` suffix matches the
# Type=simple long-running shape.
SUPERVISOR_UNIT_NAME = "scitex-dev-ecosystem.service"


def build_supervisor_unit_text() -> str:
    """Return the supervisor unit text with ``ExecStart=`` absolutised.

    Built dynamically (not a module-level constant) so the
    ``ExecStart=`` line carries the absolute path to ``scitex-dev`` as
    resolved from the operator's ambient PATH at call time. systemd
    ``--user`` runs under a deliberately minimal PATH that excludes
    most Python venvs; emitting a bare ``scitex-dev`` would 127 on
    every boot — same root-cause that fixed the legacy reconcile unit
    in PR #163 / scitex-dev v0.17.x.

    Unit shape:

    * ``Type=simple`` — the supervisor IS the foreground process. No
      fork, no PID file. Avoids the legacy oneshot's "stayed inactive
      after exit" trap.
    * ``Restart=always`` — if the supervisor itself ever crashes,
      systemd brings it back. Children are restarted by the
      supervisor; the supervisor is restarted by systemd.
    * ``ExecReload=/bin/kill -HUP $MAINPID`` — surfaces the systemd-
      idiomatic ``systemctl --user reload scitex-dev-ecosystem.service``
      for "re-read your config". The supervisor's SIGHUP handler
      re-runs ``reconcile()``.
    * ``KillSignal=SIGTERM`` + ``TimeoutStopSec=30s`` — graceful child
      shutdown: the supervisor's SIGTERM handler walks the registry,
      SIGTERMs each child, waits the grace, then SIGKILLs stragglers.
    """
    # Import lazily so ``_up_supervisor_unit`` itself stays cheap to
    # import (no jobs/_systemd at module-load time for callers that
    # only need ``SUPERVISOR_UNIT_NAME``).
    from ....jobs._systemd import resolve_execstart

    execstart = resolve_execstart("scitex-dev ecosystem run")
    return (
        "[Unit]\n"
        "Description=SciTeX ecosystem supervisor — manages every "
        "kind=service JobSpec as a child process; the SOLE per-host "
        "systemd entry for the SciTeX fleet\n"
        "Documentation=https://github.com/ywatanabe1989/scitex-dev\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={execstart}\n"
        "ExecReload=/bin/kill -HUP $MAINPID\n"
        "Restart=always\n"
        "RestartSec=5s\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n"
        "KillSignal=SIGTERM\n"
        "TimeoutStopSec=30s\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def write_supervisor_unit(unit_dir: Path) -> Path:
    """Write the supervisor service unit. Idempotent.

    Returns the path written. Always writes the canonical text — if
    the operator hand-edited the file, a fresh ``ecosystem up`` resets
    it. Hand edits belong in the JobSpec the leaf declares, not in
    scitex-dev's managed unit.
    """
    unit_dir.mkdir(parents=True, exist_ok=True)
    path = unit_dir / SUPERVISOR_UNIT_NAME
    path.write_text(build_supervisor_unit_text(), encoding="utf-8")
    return path


__all__ = [
    "SUPERVISOR_UNIT_NAME",
    "build_supervisor_unit_text",
    "write_supervisor_unit",
]


# EOF
