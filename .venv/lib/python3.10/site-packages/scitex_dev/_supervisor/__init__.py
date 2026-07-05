#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SciTeX ecosystem supervisor — the ONE process behind ``scitex-dev-ecosystem.service``.

Operator design (msg 0f009103 / 0502252a, 2026-06-14): the SciTeX fleet runs
~70 packages. A separate systemd ``--user`` unit per leaf is unmanageable, so
*scitex-dev* is the SOLE management surface. ``systemctl --user list-units``
shows exactly ONE entry — ``scitex-dev-ecosystem.service`` — and that unit's
``ExecStart`` is :func:`scitex_dev._supervisor._runtime.run_supervisor`, the
collective wrapper this package implements.

Public surface
--------------
* :class:`Supervisor` — the long-running process supervisor itself.
* :func:`run_supervisor` — convenience entry point that constructs a
  default-configured :class:`Supervisor` and calls
  :meth:`Supervisor.run_forever`.
* :class:`ChildProcess` — per-leaf bookkeeping (PID, restart counter,
  circuit-breaker state, last exit code, log path).
* :class:`SupervisorState` — frozen snapshot serialised to the state file
  for ``scitex-dev ecosystem status`` to read.

The actual lowering policy lives in :mod:`scitex_dev.jobs` (the JobSpec
contract) plus the per-kind lowerings (``_systemd``, ``_cron_block``,
and this supervisor for the daemon-as-child path). All three lowerings
share a single discovery mechanism (``discover_jobs``) so adding /
removing a leaf is one entry-point registration.
"""

from __future__ import annotations

from ._child import ChildProcess
from ._runtime import Supervisor, run_supervisor
from ._state import (
    DEFAULT_LOG_DIR,
    DEFAULT_STATE_DIR,
    SupervisorState,
    default_log_dir,
    default_state_dir,
    default_state_path,
)

__all__ = [
    "ChildProcess",
    "DEFAULT_LOG_DIR",
    "DEFAULT_STATE_DIR",
    "Supervisor",
    "SupervisorState",
    "default_log_dir",
    "default_state_dir",
    "default_state_path",
    "run_supervisor",
]


# EOF
