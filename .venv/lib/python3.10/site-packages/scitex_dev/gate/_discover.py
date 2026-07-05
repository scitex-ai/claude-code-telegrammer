#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/gate/_discover.py
"""Aggregate every ``GateCheck`` declared across the ecosystem.

Mirrors ``discover_jobs`` / ``discover_system_deps``: leaves register a
provider (``() -> list[GateCheck]``) under the ``scitex_dev.gate.checks``
entry-point group; this module merges them with scitex-dev's own internal
built-in provider, dedups by check id (first-wins), and returns a
deterministic (id-sorted) list. A provider that raises — or an entry
point that fails to load — is skipped with a logged warning so one broken
leaf never wedges the gate.
"""

from __future__ import annotations

import logging
import sys
from typing import Callable

from ._spec import GateCheck

_logger = logging.getLogger(__name__)

#: Entry-point group every leaf registers its gate-check provider under.
ENTRY_POINT_GROUP = "scitex_dev.gate.checks"


def _iter_entry_points(group: str):
    """Yield entry points for ``group``, compatible with Python 3.9+."""
    from importlib.metadata import entry_points

    if sys.version_info >= (3, 10):
        return entry_points(group=group)
    return entry_points().get(group, [])


def _make_ep_provider(ep) -> Callable[[], list[GateCheck]]:
    def _provider() -> list[GateCheck]:
        get_checks = ep.load()
        return list(get_checks())

    _provider.__name__ = f"entry_point:{getattr(ep, 'name', '?')}"
    return _provider


def discover_gate_checks(
    stage: str | None = None,
    *,
    extra_providers: list[Callable[[], list[GateCheck]]] | None = None,
    include_entry_points: bool = True,
    include_builtins: bool = True,
) -> list[GateCheck]:
    """Return every registered ``GateCheck``, optionally filtered by stage.

    ``include_entry_points=False`` skips the entry-point walk (the unit-test
    isolation seam — exact-list assertions stay valid regardless of which
    real leaf providers are installed). ``include_builtins=False`` drops
    scitex-dev's own built-in checks. Dedup is by check id, first-wins in
    provider order (built-ins, then entry points, then ``extra_providers``);
    the returned list is sorted by id for determinism.
    """
    providers: list[Callable[[], list[GateCheck]]] = []
    if include_builtins:
        from ._builtin import provide as _builtin_provide

        providers.append(_builtin_provide)
    if include_entry_points:
        for ep in _iter_entry_points(ENTRY_POINT_GROUP):
            providers.append(_make_ep_provider(ep))
    if extra_providers:
        providers.extend(extra_providers)

    by_id: dict[str, GateCheck] = {}
    for provider in providers:
        try:
            checks = provider()
        except Exception:
            _logger.warning(
                "Failed to load gate checks from provider %r", provider, exc_info=True
            )
            continue
        for check in checks:
            if not isinstance(check, GateCheck):
                _logger.warning(
                    "Provider %r yielded a non-GateCheck %r; skipping",
                    provider,
                    check,
                )
                continue
            if stage is not None and check.stage != stage:
                continue
            if check.id in by_id:
                _logger.warning(
                    "Duplicate gate-check id %r; keeping the first-registered "
                    "and dropping %r",
                    check.id,
                    provider,
                )
                continue
            by_id[check.id] = check

    return [by_id[cid] for cid in sorted(by_id)]


__all__ = ["ENTRY_POINT_GROUP", "discover_gate_checks"]
