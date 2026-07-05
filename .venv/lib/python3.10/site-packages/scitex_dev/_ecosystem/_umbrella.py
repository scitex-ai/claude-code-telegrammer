#!/usr/bin/env python3
# Timestamp: 2026-06-07
# File: scitex_dev/_ecosystem/_umbrella.py

"""SSoT resolver: derive umbrella surfaces from the ECOSYSTEM registry.

The umbrella (``scitex`` package, repo ``scitex-python``) has four
hand-maintained surfaces that *should* be derivable from the
ECOSYSTEM registry the scitex-dev owns:

1. ``[project.optional-dependencies]`` — per-module extras like
   ``scitex[io]``, ``scitex[audit]``.
2. ``[all]`` — the aggregator extra that pulls every per-module extra
   except optional-peers (``scitex-hub`` / cloud / module / project).
3. ``EXTERNAL_REEXPORTS`` (``scitex.re_export``) — the lazy-loader
   bridge mapping each ``scitex.<short>`` to a peer top-level
   (``scitex_<short>`` or a branded peer like ``figrecipe``).
4. Lazy-module declarations in ``scitex/__init__.py``
   (``<short> = _LazyModule("<short>", external="<peer>")``).

This module owns the *resolver* layer that produces the expected
shape of each surface from ECOSYSTEM. Drift between expected and
actual is detected by the ``scitex-dev ecosystem regen-umbrella
--check`` CLI (read-only) and, in a follow-up, repaired by
``regen-umbrella --write``.

Design choices:

- Defaults are derived from ``import_name`` (so most entries don't
  need to populate the umbrella_* fields).
- Multi-mount packages (one peer powering several ``scitex.<short>``
  aliases, e.g. ``scitex-logging`` → ``logging`` + ``errors``;
  ``scitex-hub`` → ``cloud`` + ``module`` + ``project``) are listed
  in :data:`AUX_MOUNTS` so the primary mount stays in the
  per-entry schema and the auxiliary mounts stay in one auditable
  table here.
- :func:`expected_all_extras` deliberately excludes
  ``category="dataset"`` / ``"template"`` / ``"umbrella"`` and any
  entry whose owner sets ``umbrella_skip=True``. It also excludes
  ``scitex-hub`` and AUX_MOUNTS pointing at scitex-hub: the operator's
  exclude-policy says the optional-peer surface stays OUT of ``[all]``.

This module is read-only against the live umbrella tree; it does not
import scitex or modify any file. The reader/diff side is in
``scitex_dev._cli.ecosystem._cmds._regen_umbrella``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ._registry import ECOSYSTEM, PackageInfo

__all__ = [
    "AUX_MOUNTS",
    "AuxMount",
    "HAND_CURATED_EXTRAS",
    "IN_TREE_SHIM_LAZY_ATTRS",
    "Mount",
    "default_lazy_short",
    "default_external",
    "expected_all_extras",
    "expected_external_reexports",
    "expected_lazy_attrs",
    "iter_primary_mounts",
    "mount_of",
    "umbrella_core_deps",
]


# --------------------------------------------------------------------- #
# Mount records                                                          #
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class Mount:
    """One resolved ``scitex.<short>`` mount derived from an ECOSYSTEM entry.

    Attributes
    ----------
    pkg
        The ECOSYSTEM key (e.g. ``scitex-io``).
    lazy_short
        The umbrella alias (``scitex.<lazy_short>``).
    extra
        The umbrella ``[project.optional-dependencies]`` group name
        (``scitex[<extra>]``).
    external
        Peer import target for ``EXTERNAL_REEXPORTS`` (e.g.
        ``scitex_io`` or ``scitex_etc.media``).
    in_all
        Whether this mount's extra is aggregated into ``[all]``.
    """

    pkg: str
    lazy_short: str
    extra: str
    external: str
    in_all: bool = True


@dataclass(frozen=True)
class AuxMount:
    """Auxiliary mount: a *secondary* alias owned by another peer.

    Examples: ``errors = _LazyModule(..., external="scitex_logging")``
    (scitex-logging owns both ``logging`` and ``errors``); ``cloud``
    pointing at ``scitex_hub`` (scitex-hub powers ``cloud`` / ``module``
    / ``project``). Aux mounts ship the same lazy_attr machinery but
    do NOT get their own ``[<extra>]`` group — the primary mount of
    the owning peer carries the dependency.
    """

    pkg: str  # the owning ECOSYSTEM key (e.g. scitex-logging)
    lazy_short: str  # the secondary alias (e.g. errors)
    external: str  # peer import (e.g. scitex_logging)
    in_all: bool = True  # mirrors the primary's policy


# Auxiliary mounts curated by hand — every entry is justified inline.
# Update this table when adding a new alias to scitex/__init__.py.
AUX_MOUNTS: tuple[AuxMount, ...] = (
    # scitex-logging owns both `logging` (primary) and `errors`
    # (historical alias that pre-dated the standalone split).
    AuxMount(pkg="scitex-logging", lazy_short="errors", external="scitex_logging"),
    # scitex-linalg's `torch` umbrella alias carries the numerics
    # surface that lived under `scitex.torch` before linalg split.
    AuxMount(pkg="scitex-linalg", lazy_short="torch", external="scitex_linalg"),
    # scitex-ssh owns both `ssh` (primary) and `tunnel` (the SSH-tunnel
    # surface that lived in scitex-tunnel before the merge).
    AuxMount(pkg="scitex-ssh", lazy_short="tunnel", external="scitex_ssh"),
    # scitex-etc ships the media display helpers under `scitex_etc.media`;
    # `scitex.media` proxies into that submodule.
    AuxMount(pkg="scitex-etc", lazy_short="media", external="scitex_etc.media"),
    # scitex-notification's `notify` alias is a back-compat duplicate of
    # the `notification` primary; both point at the same peer.
    AuxMount(
        pkg="scitex-notification", lazy_short="notify", external="scitex_notification"
    ),
    # figrecipe powers `diagram` via `figrecipe.diagram`; `plt`/`fig`
    # primaries are handled by the primary-mount machinery.
    AuxMount(pkg="figrecipe", lazy_short="diagram", external="figrecipe.diagram"),
    # OPTIONAL-peer triple: scitex-hub powers `cloud` / `module` /
    # `project`. in_all=False is the operator's exclude policy — these
    # three aliases stay OUT of [all] so CI's matrix runs without
    # scitex-hub.
    AuxMount(pkg="scitex-hub", lazy_short="cloud", external="scitex_hub", in_all=False),
    AuxMount(
        pkg="scitex-hub", lazy_short="module", external="scitex_hub.module", in_all=False
    ),
    AuxMount(
        pkg="scitex-hub",
        lazy_short="project",
        external="scitex_hub.project",
        in_all=False,
    ),
)


# Per-package primary-mount overrides for branded peers. These live in
# the registry's umbrella_lazy_short / umbrella_extra / umbrella_skip
# fields too; this table is the resolver-side fallback so an entry can
# stay schema-light while the primary alias still gets resolved
# correctly. Add an entry here when a branded peer would otherwise
# produce the wrong default (e.g. socialia → "socialia").
_BRANDED_OVERRIDES: dict[str, tuple[str, str]] = {
    # pkg → (lazy_short, extra)
    "socialia": ("social", "social"),
    "figrecipe": ("fig", "plt"),
}


# Categories that NEVER contribute a primary mount.
#
# - ``umbrella`` is the scitex package itself.
# - ``dataset`` (openalex-local, crossref-local) is data-only, no
#   ``scitex.<short>`` alias.
#
# NOTE: ``template`` (the audit-skip category for scaffold repos) is
# DIFFERENT from "the scitex-template peer that powers `scitex.template`".
# The latter SHOULD mount (it is the package mounted at
# ``scitex.template``). Category=template is a hint to the auditor, not
# an umbrella exclusion, so we don't filter on it here.
_NON_MOUNTING_CATEGORIES = frozenset({"umbrella", "dataset"})

# Hard-coded exclude-from-[all] policy (operator 2026-06-07): optional
# peers stay out so CI's `pip install scitex[all]` works without them.
_EXCLUDE_FROM_ALL = frozenset({"scitex-hub"})


# Hand-curated extras the umbrella keeps OUTSIDE the SSoT regen flow.
# Lead 2026-06-07: "Keep core dependencies (version pins, release-wave
# driven) + heavy/dev/docs (3rd-party curation) as the only hand-written
# umbrella elements." These extras ship 3rd-party tool curation, alias
# groups, or deprecated names — they are NOT derivable from ECOSYSTEM
# and should not surface as drift.
HAND_CURATED_EXTRAS: frozenset[str] = frozenset(
    {
        # 3rd-party tool curation
        "heavy",
        "dev",
        "devtools",
        "docs",
        "cli",
        "scholar-gui",
        # Deprecated module aliases (kept for backward compat)
        "reproduce",
        "rng",
        "verify",
        "dt",
        # In-tree shim modules without a peer standalone
        "schema",
        # Aux-mount aliases — one peer powers multiple `scitex.<short>`
        # aliases (lead 2026-06-07 PR-A2 approval: these are LEGIT
        # umbrella aliases backed by AUX_MOUNTS, NOT cruft). The owning
        # peer's primary [extra] already covers the dependency.
        "diagram",  # figrecipe.diagram (owned by figrecipe primary [plt])
        "media",  # scitex_etc.media (owned by scitex-etc primary [etc])
        "torch",  # scitex_linalg (owned by scitex-linalg primary [linalg])
        "tunnel",  # scitex_ssh (owned by scitex-ssh primary [ssh])
    }
)


# In-tree shim lazy_attrs the umbrella ships *without* a peer external —
# the dir lives in ``src/scitex/<short>/`` and the alias is just a Python
# module name with no ``external="…"`` argument. Drift detector treats
# these as legitimately ``external=None`` and suppresses the
# external-mismatch finding (lead 2026-06-07 PR-A2 approval option (a)).
#
# Distinct from HAND_CURATED_EXTRAS (which is about pyproject [extras]):
# this set is about ``__init__.py`` lazy_attr declarations.
IN_TREE_SHIM_LAZY_ATTRS: frozenset[str] = frozenset(
    {
        # Real peer that ships an in-tree shim instead of external import.
        # Operator may later choose to externalize these or keep the shim;
        # either way, drift on ``external`` field stays silent.
        "dev",  # scitex.dev shim → eventually `external="scitex_dev"`
        "fig",  # scitex.fig shim → eventually `external="figrecipe"`
        "plt",  # scitex.plt shim → eventually `external="scitex_plt"`
        "session",  # scitex.session shim → eventually `external="scitex_session"`
        "social",  # scitex.social shim → eventually `external="socialia"`
        # In-tree modules with no peer at all — drift never resolves.
        "canvas",
        "cli",
        "fts",
        "schema",
        "usage",
    }
)


# --------------------------------------------------------------------- #
# Default derivers                                                       #
# --------------------------------------------------------------------- #


def default_lazy_short(pkg: str) -> str:
    """Derive the default ``scitex.<short>`` alias for ``pkg``.

    Strips the ``scitex_`` prefix from ``import_name`` so
    ``scitex_io`` → ``io``. Branded peers in ``_BRANDED_OVERRIDES``
    return their curated short. Unknown packages return the literal
    import_name (caller can decide).
    """
    if pkg in _BRANDED_OVERRIDES:
        return _BRANDED_OVERRIDES[pkg][0]
    info = ECOSYSTEM.get(pkg) or {}
    explicit = info.get("umbrella_lazy_short")
    if explicit:
        return explicit
    import_name = info.get("import_name") or ""
    if import_name.startswith("scitex_"):
        return import_name[len("scitex_") :]
    return import_name


def default_extra(pkg: str) -> str:
    """Derive the default ``[<extra>]`` name for ``pkg``.

    PyPA convention is *hyphenated* extra names (so
    ``scitex[agent-container]``, not ``scitex[agent_container]``). The
    lazy_attr name keeps Python's underscore (it is a Python identifier),
    so the two diverge here: ``default_lazy_short`` returns
    ``agent_container``; ``default_extra`` returns ``agent-container``.
    """
    info = ECOSYSTEM.get(pkg) or {}
    explicit = info.get("umbrella_extra")
    if explicit:
        return explicit
    if pkg in _BRANDED_OVERRIDES:
        return _BRANDED_OVERRIDES[pkg][1]
    return default_lazy_short(pkg).replace("_", "-")


def default_external(pkg: str) -> str:
    """Derive the default peer-import target for ``pkg``."""
    info = ECOSYSTEM.get(pkg) or {}
    explicit = info.get("umbrella_external")
    if explicit:
        return explicit
    return info.get("import_name") or ""


def _is_mounted(info: PackageInfo) -> bool:
    """Return True iff this entry produces a primary mount.

    Skips archived, non-mounting categories, and explicit
    ``umbrella_skip=True`` entries.
    """
    if info.get("archived"):
        return False
    if info.get("umbrella_skip"):
        return False
    if info.get("category") in _NON_MOUNTING_CATEGORIES:
        return False
    return True


# --------------------------------------------------------------------- #
# Mount iteration / lookup                                               #
# --------------------------------------------------------------------- #


def iter_primary_mounts() -> Iterable[Mount]:
    """Yield every primary mount derived from the registry.

    A *primary mount* is the one driven by the ECOSYSTEM entry's
    ``umbrella_*`` fields (with defaults). Aux mounts (one peer
    powering multiple aliases) come from :data:`AUX_MOUNTS` and are
    NOT yielded here — call :func:`expected_lazy_attrs` for the
    full alias list.
    """
    for pkg, info in ECOSYSTEM.items():
        if not _is_mounted(info):
            continue
        lazy_short = default_lazy_short(pkg)
        if not lazy_short:
            continue
        yield Mount(
            pkg=pkg,
            lazy_short=lazy_short,
            extra=default_extra(pkg),
            external=default_external(pkg),
            in_all=(pkg not in _EXCLUDE_FROM_ALL),
        )


def mount_of(pkg: str) -> Mount | None:
    """Resolve the primary mount for ``pkg``, or None if not mounted."""
    info = ECOSYSTEM.get(pkg)
    if info is None or not _is_mounted(info):
        return None
    return Mount(
        pkg=pkg,
        lazy_short=default_lazy_short(pkg),
        extra=default_extra(pkg),
        external=default_external(pkg),
        in_all=(pkg not in _EXCLUDE_FROM_ALL),
    )


# --------------------------------------------------------------------- #
# Expected umbrella surfaces                                             #
# --------------------------------------------------------------------- #


def expected_all_extras() -> list[str]:
    """Compute the expected ``[all]`` aggregator membership.

    Returns a sorted list of ``"scitex[<extra>]"`` strings — one per
    primary mount where ``in_all=True``. The operator's exclude
    policy filters out ``scitex-hub`` and any other entry tagged
    ``umbrella_skip``.

    Note: this returns ONLY the registry-derived members. The
    umbrella's hand-curated extras (``heavy``, ``dev``, ``docs``,
    ``bridge``, ``rng``, etc.) are NOT in scope here — they stay
    hand-maintained in pyproject.toml because they curate third-party
    tools, not first-party peers.
    """
    out: set[str] = set()
    for mount in iter_primary_mounts():
        if not mount.in_all:
            continue
        if mount.extra in HAND_CURATED_EXTRAS:
            # ``scitex-dev`` derives ``extra="dev"`` but the umbrella's
            # ``[dev]`` extra is a curated 3rd-party tools list; the
            # peer goes into core ``dependencies`` instead, not into a
            # registry-derived ``[dev]``.
            continue
        out.add(f"scitex[{mount.extra}]")
    return sorted(out)


def expected_external_reexports() -> dict[str, str]:
    """Compute the expected ``EXTERNAL_REEXPORTS`` map.

    Combines every primary mount + every aux mount whose ``external``
    is a top-level module (not a submodule). Submodule externals
    (``scitex_etc.media``) are *not* eligible for the eager
    ``register_external_lazy_modules`` registry: those use the
    in-tree ``_LazyModule(external="…")`` direct proxy, which
    handles dotted externals at attribute-access time.
    """
    out: dict[str, str] = {}
    for mount in iter_primary_mounts():
        if "." in mount.external:
            continue
        out[mount.lazy_short] = mount.external
    for aux in AUX_MOUNTS:
        if "." in aux.external:
            continue
        out.setdefault(aux.lazy_short, aux.external)
    return out


def expected_lazy_attrs() -> list[tuple[str, str | None]]:
    """Return the expected ``(short, external)`` pairs for ``__init__.py``.

    External is ``None`` for in-tree shims (modules with no peer
    standalone). Sorted by ``short`` for deterministic output.
    """
    pairs: dict[str, str | None] = {}
    for mount in iter_primary_mounts():
        pairs[mount.lazy_short] = mount.external or None
    for aux in AUX_MOUNTS:
        pairs.setdefault(aux.lazy_short, aux.external or None)
    return sorted(pairs.items())


def umbrella_core_deps() -> list[str]:
    """Return the registry-derived umbrella core ``dependencies``.

    Entries flagged ``umbrella_core_dep=True`` in ECOSYSTEM. Sorted
    by pypi_name. Returns only the names; version-pin reconciliation
    is the release-wave job (separate ``ecosystem version-reconcile``
    command) and is intentionally NOT in scope here.
    """
    out: list[str] = []
    for pkg, info in ECOSYSTEM.items():
        if info.get("umbrella_core_dep"):
            out.append(info.get("pypi_name") or pkg)
    return sorted(out)


# EOF
