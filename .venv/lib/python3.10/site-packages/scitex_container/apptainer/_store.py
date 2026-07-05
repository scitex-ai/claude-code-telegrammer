#!/usr/bin/env python3
# Timestamp: "2026-05-24"
# File: src/scitex_container/apptainer/_store.py
"""Timestamped (sif, lock) artifact store for reproducible builds.

Artifact layout (per the operator-approved design)::

    <root>/containers/
    ├── <layer>.sif  ->  <layer>/<layer>-<ts>.sif        (latest symlink)
    └── <layer>/
        ├── <layer>-<ts>.sif        # canonical artifact (one per <ts>)
        ├── <layer>-<ts>.lock        # paired lock (full version set)
        ├── <layer>-<ts>.def         # locked def (used to reproduce)
        ├── <layer>-<ts>.verified    # OR .unverified (round-trip result)
        ├── <layer>-<ts>.keep        # optional: prune-protect dotfile
        ├── <layer>-<ts>.build.log
        └── ... older <ts> sets (pruned to retain N)

The ``<ts>`` correspondence between the SIF and its lock is the
invariant: a build's lock reproduces exactly that build's SIF.

This module owns the on-disk shape only (paths, symlink, markers,
retention). The round-trip orchestration lives in ``_reproducible.py``;
lock capture + locked-def generation live in ``_lockgen.py``.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from scitex_container._compat import supports_return_as

logger = logging.getLogger(__name__)

# <layer>-<YYYY-MMDD-HHMMSS>.sif — the timestamp shape mirrors the
# existing build-log timestamp (``_dt.strftime("%Y-%m%d-%H%M%S")``).
_TS_RE = r"\d{4}-\d{4}-\d{6}"


def timestamp() -> str:
    """Return a fresh build timestamp string (``YYYY-MMDD-HHMMSS``)."""
    return _dt.datetime.now().strftime("%Y-%m%d-%H%M%S")


@dataclass(frozen=True)
class ArtifactPaths:
    """Resolved paths for one timestamped build of a layer.

    Every artifact for a single ``(layer, ts)`` build, plus the
    layer-level ``latest`` symlink, derived from the output root.
    """

    root: Path  # containers/ dir
    layer: str
    ts: str

    @property
    def layer_dir(self) -> Path:
        return self.root / self.layer

    @property
    def sif(self) -> Path:
        return self.layer_dir / f"{self.layer}-{self.ts}.sif"

    @property
    def lock(self) -> Path:
        return self.layer_dir / f"{self.layer}-{self.ts}.lock"

    @property
    def locked_def(self) -> Path:
        return self.layer_dir / f"{self.layer}-{self.ts}.def"

    @property
    def verified_marker(self) -> Path:
        return self.layer_dir / f"{self.layer}-{self.ts}.verified"

    @property
    def unverified_marker(self) -> Path:
        return self.layer_dir / f"{self.layer}-{self.ts}.unverified"

    @property
    def keep_marker(self) -> Path:
        return self.layer_dir / f"{self.layer}-{self.ts}.keep"

    @property
    def build_log(self) -> Path:
        return self.layer_dir / f"{self.layer}-{self.ts}.build.log"

    @property
    def latest_symlink(self) -> Path:
        return self.root / f"{self.layer}.sif"


def artifact_paths(
    root: str | Path,
    layer: str,
    ts: str,
) -> ArtifactPaths:
    """Build an ``ArtifactPaths`` for ``(layer, ts)`` under ``root``."""
    return ArtifactPaths(root=Path(root), layer=layer, ts=ts)


@supports_return_as
def list_builds(root: str | Path, layer: str) -> list[dict]:
    """List the timestamped builds of ``layer`` under ``root``.

    Parameters
    ----------
    root : str or Path
        The ``containers/`` directory.
    layer : str
        Layer name (e.g. ``sac-base``).

    Returns
    -------
    list[dict]
        One dict per build with keys ``ts``, ``sif``, ``lock``, ``def``,
        ``verified`` (bool|None — None when no marker yet), ``keep``
        (bool), ``active`` (bool — the current ``latest`` symlink
        target). Sorted newest ``ts`` first.
    """
    root = Path(root)
    layer_dir = root / layer
    if not layer_dir.is_dir():
        return []

    pat = re.compile(rf"^{re.escape(layer)}-({_TS_RE})\.sif$")
    active_ts = _active_ts(root, layer)

    builds: list[dict] = []
    for sif in layer_dir.glob(f"{layer}-*.sif"):
        m = pat.match(sif.name)
        if not m:
            continue
        ts = m.group(1)
        ap = artifact_paths(root, layer, ts)
        verified: bool | None
        if ap.verified_marker.exists():
            verified = True
        elif ap.unverified_marker.exists():
            verified = False
        else:
            verified = None
        builds.append(
            {
                "ts": ts,
                "sif": str(ap.sif),
                "lock": str(ap.lock) if ap.lock.exists() else None,
                "def": str(ap.locked_def) if ap.locked_def.exists() else None,
                "verified": verified,
                "keep": ap.keep_marker.exists(),
                "active": ts == active_ts,
            }
        )

    builds.sort(key=lambda b: b["ts"], reverse=True)
    return builds


def _active_ts(root: Path, layer: str) -> str | None:
    """Return the ``<ts>`` the layer ``latest`` symlink points at, if any."""
    link = root / f"{layer}.sif"
    if not link.is_symlink():
        return None
    target = link.readlink()
    m = re.match(
        rf"^{re.escape(layer)}/{re.escape(layer)}-({_TS_RE})\.sif$", str(target)
    )
    if m:
        return m.group(1)
    # Fall back to matching the resolved name in case the link was
    # written as an absolute or oddly-shaped target.
    m2 = re.match(rf"^{re.escape(layer)}-({_TS_RE})\.sif$", Path(str(target)).name)
    return m2.group(1) if m2 else None


def atomic_symlink(link: str | Path, rel_target: str | Path) -> Path:
    """Atomically point ``link`` at ``rel_target`` (temp symlink + os.replace).

    The single SSOT for the safe-swap primitive: write a temporary symlink
    beside ``link`` (same directory → same filesystem, so the rename is
    atomic), then ``os.replace`` it onto ``link``. Any existing symlink OR
    real file at ``link`` is replaced atomically — a concurrent reader sees
    either the old target or the new one, never a missing/partial link.

    ``rel_target`` is written verbatim as the symlink target; keep it
    relative to ``link``'s parent so the store stays relocatable.

    Returns
    -------
    Path
        The ``link`` path.
    """
    link = Path(link)
    rel_target = Path(rel_target)
    # Unique temp name in the link's own dir: PID-scoped so parallel builds
    # of *different* layers never collide, plus the target name for a same-PID
    # sandbox. The temp is always unlinked+replaced, so staleness is harmless.
    tmp = link.parent / f".{link.name}.tmp.{os.getpid()}.{rel_target.name}"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(rel_target)
    # os.replace on a symlink path performs an atomic rename.
    os.replace(tmp, link)
    return link


@supports_return_as
def point_latest(root: str | Path, layer: str, ts: str) -> Path:
    """Point the layer ``latest`` symlink at the ``(layer, ts)`` build.

    Writes ``<root>/<layer>.sif -> <layer>/<layer>-<ts>.sif`` (a relative
    target so the store stays relocatable). Atomically replaces any
    existing symlink/file.

    Returns
    -------
    Path
        The symlink path.
    """
    root = Path(root)
    ap = artifact_paths(root, layer, ts)
    if not ap.sif.exists():
        raise FileNotFoundError(f"Build artifact not found: {ap.sif}")

    rel_target = Path(layer) / f"{layer}-{ts}.sif"
    link = atomic_symlink(ap.latest_symlink, rel_target)
    logger.info("Pointed %s.sif -> %s", layer, rel_target)
    return link


@supports_return_as
def prune(root: str | Path, layer: str, retain: int) -> list[str]:
    """Prune old builds of ``layer``, keeping the ``retain`` most recent.

    Never removes:
    - the ``retain`` most-recent builds (by ``<ts>``),
    - the active build (current ``latest`` symlink target),
    - any build carrying a ``.keep`` marker.

    Parameters
    ----------
    root : str or Path
        The ``containers/`` directory.
    layer : str
        Layer name.
    retain : int
        Number of most-recent builds to keep.

    Returns
    -------
    list[str]
        The ``<ts>`` values that were pruned.
    """
    root = Path(root)
    builds = list_builds(root, layer)  # newest first
    active_ts = _active_ts(root, layer)

    pruned: list[str] = []
    kept = 0
    for b in builds:
        ts = b["ts"]
        if ts == active_ts:
            continue
        if b["keep"]:
            continue
        if kept < retain:
            kept += 1
            continue
        _remove_build(root, layer, ts)
        pruned.append(ts)

    return pruned


def _remove_build(root: Path, layer: str, ts: str) -> None:
    """Delete every artifact file for one ``(layer, ts)`` build."""
    ap = artifact_paths(root, layer, ts)
    for p in (
        ap.sif,
        ap.lock,
        ap.locked_def,
        ap.verified_marker,
        ap.unverified_marker,
        ap.keep_marker,
        ap.build_log,
    ):
        if p.is_file() or p.is_symlink():
            logger.info("Pruning %s", p.name)
            p.unlink()


@supports_return_as
def mark_verified(root: str | Path, layer: str, ts: str) -> Path:
    """Write the ``.verified`` marker for a build (clears ``.unverified``)."""
    root = Path(root)
    ap = artifact_paths(root, layer, ts)
    if ap.unverified_marker.exists():
        ap.unverified_marker.unlink()
    ap.verified_marker.write_text(
        f"round-trip verified at {_dt.datetime.now().isoformat()}\n"
    )
    return ap.verified_marker


@supports_return_as
def mark_unverified(root: str | Path, layer: str, ts: str, reason: str = "") -> Path:
    """Write the ``.unverified`` marker for a build (clears ``.verified``).

    The marker body carries the drift reason so a later use-time check
    can surface *what* drifted, not just *that* it drifted.
    """
    root = Path(root)
    ap = artifact_paths(root, layer, ts)
    if ap.verified_marker.exists():
        ap.verified_marker.unlink()
    body = f"reproducibility unverified at {_dt.datetime.now().isoformat()}\n"
    if reason:
        body += reason.rstrip("\n") + "\n"
    ap.unverified_marker.write_text(body)
    return ap.unverified_marker


@supports_return_as
def protect(root: str | Path, layer: str, ts: str) -> Path:
    """Write the ``.keep`` prune-protect marker for a build."""
    root = Path(root)
    ap = artifact_paths(root, layer, ts)
    ap.keep_marker.write_text("prune-protected\n")
    return ap.keep_marker


# EOF
