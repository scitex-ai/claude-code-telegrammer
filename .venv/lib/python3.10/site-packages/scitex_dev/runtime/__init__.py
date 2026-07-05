#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex_dev.runtime — shared async runtime primitives for SciTeX daemons.

Currently exports the supervised periodic-task shape that every SciTeX daemon
loop collapses onto:

* :class:`PeriodicTask` — one interval-fired, off-loop-dispatching, env-gated,
  cleanly-cancellable, fail-loud loop.
* :class:`PeriodicTaskGroup` — start/stop a set of them as a unit.

Stable import path for consumers::

    from scitex_dev.runtime import PeriodicTask, PeriodicTaskGroup

Importing this package has no side effects.
"""

from __future__ import annotations

from ._periodic import PeriodicTask, PeriodicTaskGroup

__all__ = ["PeriodicTask", "PeriodicTaskGroup"]


# EOF
