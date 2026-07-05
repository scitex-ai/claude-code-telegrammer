#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev service …`` — keep a declared daemon alive, fleet-wide.

A leaf declares a long-running daemon as a ``kind="service"`` JobSpec
(via the ``scitex_dev.jobs`` entry-point federation). scitex-dev owns
keeping it running so no package hand-rolls its own supervisor — the
2026-07-01 sac ``listen`` daemon death (no supervisor, hung fleet) is
exactly what this closes.

Verbs:
  * ``ensure``  — guarantee the named service is installed AND running,
                  picking the systemd ``--user`` backend when available
                  and a respawn keep-alive loop otherwise.
"""

from __future__ import annotations

from ._cmd import register_service_commands

__all__ = ["register_service_commands"]
