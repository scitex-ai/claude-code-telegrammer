#!/usr/bin/env python3
# File: src/scitex_container/apptainer/_sandbox_versioning.py
"""Sandbox version management: list, switch, rollback, cleanup.

Manages versioned sandbox directories (sandbox-YYYYMMDD_HHMMSS/) with
a ``current-sandbox`` symlink pointing to the active version.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from scitex_container._compat import supports_return_as

logger = logging.getLogger(__name__)

_SANDBOX_RE = re.compile(r"^sandbox-(\d{8}_\d{6})$")


def _parse_sandbox_version(path: Path) -> str | None:
    """Extract timestamp from a sandbox-YYYYMMDD_HHMMSS directory name."""
    m = _SANDBOX_RE.match(path.name)
    return m.group(1) if m else None


def _versioned_sandboxes(containers_dir: Path) -> list[Path]:
    """Return sandbox-* directories sorted by modification time (newest first)."""
    sandboxes = [
        p for p in containers_dir.iterdir() if p.is_dir() and _SANDBOX_RE.match(p.name)
    ]
    sandboxes.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return sandboxes


@supports_return_as
def list_sandboxes(containers_dir: Path) -> list[dict]:
    """List all versioned sandbox directories with metadata.

    Parameters
    ----------
    containers_dir : Path
        Directory containing sandbox directories.

    Returns
    -------
    list[dict]
        Each dict has keys: version, path, date, active.
        Sorted by modification time (newest first).
    """
    containers_dir = Path(containers_dir)
    active = get_active_sandbox(containers_dir)
    results = []

    for sb in _versioned_sandboxes(containers_dir):
        version = _parse_sandbox_version(sb)
        if version is None:
            continue
        stat = sb.stat()
        results.append(
            {
                "version": version,
                "path": str(sb),
                "date": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                "active": version == active,
            }
        )

    return results


@supports_return_as
def get_active_sandbox(containers_dir: Path) -> str | None:
    """Read current-sandbox symlink to determine active sandbox version.

    Parameters
    ----------
    containers_dir : Path
        Directory containing the current-sandbox symlink.

    Returns
    -------
    str or None
        Timestamp string of the active sandbox, or None if no symlink.
    """
    containers_dir = Path(containers_dir)
    link = containers_dir / "current-sandbox"

    if not link.is_symlink():
        return None

    target = Path(link.readlink())
    return _parse_sandbox_version(target)


@supports_return_as
def switch_sandbox(
    version: str,
    containers_dir: Path,
    use_sudo: bool = False,
) -> None:
    """Atomically switch current-sandbox symlink to sandbox-{version}/.

    Uses ``ln -sfn`` to create a temporary symlink, then ``mv -Tf`` for
    an atomic rename on the same filesystem.

    Parameters
    ----------
    version : str
        Target timestamp string (e.g. "20260225_173700").
    containers_dir : Path
        Directory containing sandbox directories.
    use_sudo : bool
        If True, run ln/mv via sudo.

    Raises
    ------
    FileNotFoundError
        If the target sandbox does not exist.
    RuntimeError
        If the symlink switch fails.
    """
    containers_dir = Path(containers_dir)
    target_name = f"sandbox-{version}"
    target_path = containers_dir / target_name
    link_path = containers_dir / "current-sandbox"

    if not target_path.is_dir():
        raise FileNotFoundError(f"Sandbox {version} not found: {target_path}")

    tmp_link = containers_dir / f".current-sandbox.tmp.{id(version)}"
    prefix = ["sudo"] if use_sudo else []

    try:
        subprocess.run(
            [*prefix, "ln", "-sfn", target_name, str(tmp_link)],
            check=True,
        )
        subprocess.run(
            [*prefix, "mv", "-Tf", str(tmp_link), str(link_path)],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        tmp_link.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to switch to sandbox {version}: {exc}") from exc

    logger.info("Switched to sandbox %s", version)


@supports_return_as
def rollback_sandbox(
    containers_dir: Path,
    use_sudo: bool = False,
) -> str:
    """Switch to the sandbox before the current one (by modification time).

    Parameters
    ----------
    containers_dir : Path
        Directory containing sandbox directories.
    use_sudo : bool
        If True, run symlink commands via sudo.

    Returns
    -------
    str
        Timestamp string of the now-active sandbox.

    Raises
    ------
    RuntimeError
        If there is no current sandbox or no previous one to roll back to.
    """
    containers_dir = Path(containers_dir)
    active = get_active_sandbox(containers_dir)

    if active is None:
        raise RuntimeError("No active sandbox found; cannot rollback")

    sandboxes = _versioned_sandboxes(containers_dir)
    versions = [_parse_sandbox_version(s) for s in sandboxes]

    try:
        idx = versions.index(active)
    except ValueError:
        raise RuntimeError(f"Active sandbox {active} not found in directory")

    if idx + 1 >= len(versions):
        raise RuntimeError(f"No older sandbox to roll back to (current: {active})")

    previous = versions[idx + 1]
    logger.info("Rolling back sandbox from %s to %s", active, previous)
    switch_sandbox(previous, containers_dir, use_sudo=use_sudo)
    return previous


@supports_return_as
def cleanup_sandboxes(
    containers_dir: Path,
    keep: int = 5,
) -> list[Path]:
    """Remove old sandbox directories, keeping the N most recent.

    Never removes the active sandbox (current-sandbox symlink target).

    Parameters
    ----------
    containers_dir : Path
        Directory containing sandbox directories.
    keep : int
        Number of most-recent sandboxes to keep (default: 5).

    Returns
    -------
    list[Path]
        Paths of removed sandbox directories.
    """
    containers_dir = Path(containers_dir)
    active = get_active_sandbox(containers_dir)
    sandboxes = _versioned_sandboxes(containers_dir)
    removed: list[Path] = []

    kept = 0
    for sb in sandboxes:
        version = _parse_sandbox_version(sb)
        if version is None:
            continue

        if version == active:
            continue

        if kept < keep:
            kept += 1
            continue

        logger.info("Removing old sandbox: %s", sb.name)
        shutil.rmtree(sb)
        removed.append(sb)

    return removed


@supports_return_as
def cleanup_sifs(
    containers_dir: Path,
    keep: int = 0,
) -> list[Path]:
    """Remove SIF files and related artifacts.

    Removes ``*.sif``, ``*.sif.old``, ``*.sif.backup.*`` files and
    the ``current.sif`` symlink.

    Parameters
    ----------
    containers_dir : Path
        Directory containing SIF files.
    keep : int
        Number of most-recent versioned SIFs to keep (default: 0).

    Returns
    -------
    list[Path]
        Paths of removed files.
    """
    from ._versioning import _VERSION_RE, _versioned_sifs

    containers_dir = Path(containers_dir)
    removed: list[Path] = []

    for pattern in ("*.sif.old", "*.sif.backup.*"):
        for f in containers_dir.glob(pattern):
            if f.is_file():
                logger.info("Removing SIF artifact: %s", f.name)
                f.unlink()
                removed.append(f)

    sifs = _versioned_sifs(containers_dir)
    for i, sif in enumerate(sifs):
        if i < keep:
            continue
        logger.info("Removing SIF: %s", sif.name)
        sif.unlink()
        removed.append(sif)

    for f in containers_dir.glob("*.sif"):
        if f.is_file() and not _VERSION_RE.match(f.name):
            logger.info("Removing non-versioned SIF: %s", f.name)
            f.unlink()
            removed.append(f)

    link = containers_dir / "current.sif"
    if link.is_symlink():
        logger.info("Removing current.sif symlink")
        link.unlink()
        removed.append(link)

    return removed


# EOF
