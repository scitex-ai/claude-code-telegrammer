#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_system_deps.py
"""scitex-dev's own SYSTEM (apt) dependency declarations.

scitex-dev historically declared no system deps of its own — this module
exists because the ``scholar-library-sync`` managed cron job (see
``_cli.cron._job_commands._scholar_library_sync_command``) shells out to
``rsync`` via ``scitex-ssh sync``. Registered under the same
``scitex_dev.system_deps`` entry-point federation every leaf uses, so the
aggregator (``discover_system_deps``) picks it up like any downstream
provider — the keystone eats its own dog food.
"""

from __future__ import annotations

from scitex_dev.system_deps import SystemDepSpec


def provide() -> list[SystemDepSpec]:
    """System deps scitex-dev itself needs at image-build time."""
    return [
        SystemDepSpec(
            "rsync",
            "scholar-library cross-machine sync (scitex-ssh sync wraps rsync)",
            "scitex-dev",
        ),
    ]
