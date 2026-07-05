#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/system_deps.py
"""Federated SYSTEM (apt) dependency declaration for the SciTeX ecosystem.

Every scitex leaf declares the system packages it needs (apt names) by
registering a callable under the ``scitex_dev.system_deps`` entry-point group;
``discover_system_deps()`` aggregates them, deduplicated by apt package name.
This replaces hardcoding apt lists in container definitions -- the same
entry-point federation used by ``scitex_dev.jobs`` / ``discover_jobs``.

apt requires root, so INSTALLATION happens at IMAGE-BUILD time (in a container
``%post`` / Dockerfile), NEVER at agent boot (agents are rootless ``--userns``
and cannot apt-install). Declarations live in the leaves; install is build-time.

Example provider (in a leaf package)::

    # scitex_writer/_system_deps.py
    from scitex_dev.system_deps import SystemDepSpec

    def provide() -> list[SystemDepSpec]:
        return [
            SystemDepSpec("texlive-latex-extra", "LaTeX compile", "scitex-writer"),
            SystemDepSpec("biber", "bibliography backend", "scitex-writer"),
        ]

    # pyproject.toml
    # [project.entry-points."scitex_dev.system_deps"]
    # scitex-writer = "scitex_writer._system_deps:provide"
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Callable

_logger = logging.getLogger(__name__)

#: Entry-point group every leaf registers its system-dep provider under.
ENTRY_POINT_GROUP = "scitex_dev.system_deps"


@dataclass(frozen=True)
class SystemDepSpec:
    """One system (apt) package a scitex package needs at image-build time.

    Fields
    ------
    package
        The apt package name (e.g. ``"ffmpeg"``, ``"texlive-science"``).
    purpose
        Short human-readable reason -- shown in listings and docs.
    provider
        The declaring package (e.g. ``"scitex-writer"``).
    apt_repo
        Optional extra apt source needed before install -- an
        ``add-apt-repository`` argument such as ``"ppa:apptainer/ppa"``.
        ``None`` when the package is in the default repos.
    """

    package: str
    purpose: str
    provider: str
    apt_repo: str | None = None

    def __post_init__(self) -> None:
        # Fail EARLY at construction so a malformed declaration never reaches
        # the aggregator or a container build.
        if not isinstance(self.package, str) or not self.package.strip():
            raise ValueError(
                f"SystemDepSpec.package must be a non-empty apt name; "
                f"got {self.package!r}"
            )
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError(
                f"SystemDepSpec({self.package!r}).provider must name the "
                f"declaring package; got {self.provider!r}"
            )


def _iter_entry_points(group: str):
    """Yield entry points for ``group``, compatible with Python 3.9+."""
    from importlib.metadata import entry_points

    if sys.version_info >= (3, 10):
        return entry_points(group=group)
    eps = entry_points()
    return eps.get(group, [])


def _make_ep_provider(ep) -> Callable[[], list[SystemDepSpec]]:
    """Wrap an entry point into a provider callable returning SystemDepSpecs."""

    def _provider() -> list[SystemDepSpec]:
        get_deps = ep.load()
        return list(get_deps())

    _provider.__name__ = f"entry_point:{getattr(ep, 'name', '?')}"
    return _provider


def discover_system_deps(
    *,
    extra_providers: list[Callable[[], list[SystemDepSpec]]] | None = None,
    include_entry_points: bool = True,
) -> list[SystemDepSpec]:
    """Aggregate every ``SystemDepSpec`` declared across the ecosystem.

    Walks the ``scitex_dev.system_deps`` entry-point group (every leaf that
    registers a provider) plus any ``extra_providers`` -- a test-injection seam
    that mirrors ``discover_jobs``'s, so a fake provider can be supplied without
    installing an entry point. A provider that raises (or whose entry point
    fails to load) is skipped with a logged warning, so one broken package never
    wedges the aggregation.

    De-duplication is keyed by apt ``package`` name; on collision the FIRST
    provider wins (entry-point discovery order, then ``extra_providers``) and
    the duplicate is dropped with a logged warning -- matching ``discover_jobs``
    (provider-wins / first-wins). Returns specs sorted by package name.

    DETERMINISM GUARANTEE (contract): the result is deduped-by-package and
    sorted-by-package, so the set of apt names -- i.e. ``--list`` output -- is
    STABLE regardless of entry-point iteration order. Only the *metadata*
    (purpose / provider / apt_repo) of a duplicated package depends on discovery
    order (first-wins). Leaves can therefore rely on a reproducible install set.
    """
    providers: list[Callable[[], list[SystemDepSpec]]] = []
    if include_entry_points:
        # include_entry_points=False is the unit-test isolation seam: it
        # aggregates ONLY extra_providers, so exact-list assertions stay
        # valid regardless of which real providers are installed in the
        # running env (scitex-dev itself now registers one: rsync).
        for ep in _iter_entry_points(ENTRY_POINT_GROUP):
            providers.append(_make_ep_provider(ep))
    if extra_providers:
        providers.extend(extra_providers)

    by_package: dict[str, SystemDepSpec] = {}
    for provider in providers:
        try:
            deps = provider()
        except Exception:
            _logger.warning(
                "Failed to load system deps from provider %r",
                provider,
                exc_info=True,
            )
            continue
        for dep in deps:
            if not isinstance(dep, SystemDepSpec):
                _logger.warning(
                    "Provider %r yielded a non-SystemDepSpec %r; skipping",
                    provider,
                    dep,
                )
                continue
            if dep.package in by_package:
                _logger.warning(
                    "Duplicate system dep %r ignored (first provider wins)",
                    dep.package,
                )
                continue
            by_package[dep.package] = dep

    return [by_package[pkg] for pkg in sorted(by_package)]


__all__ = ["SystemDepSpec", "ENTRY_POINT_GROUP", "discover_system_deps"]

# EOF
