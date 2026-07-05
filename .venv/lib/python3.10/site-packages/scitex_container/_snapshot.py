#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/_snapshot.py
"""Environment snapshot for Clew reproducibility tracking.

Captures container version, SIF hash, host package versions, dev repo git
commits, and lock file hashes into a single JSON-serializable dict.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scitex_container._compat import supports_return_as


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@supports_return_as
def env_snapshot(
    containers_dir: str | Path | None = None,
    dev_repos: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Capture a lightweight JSON-serializable environment snapshot.

    Gracefully degrades — never raises, just omits fields that cannot
    be determined.

    Parameters
    ----------
    containers_dir : str or Path, optional
        Path to the containers directory.  Auto-detected via
        ``find_containers_dir()`` when *None*.
    dev_repos : list of str or Path, optional
        Paths to git repositories to include in ``dev_repos`` section.

    Returns
    -------
    dict
        JSON-serializable snapshot with keys:
        ``schema_version``, ``timestamp``, ``container``, ``host``,
        ``dev_repos``, ``lock_files``.
    """
    snap: dict[str, Any] = {
        "schema_version": "1.0",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    snap["container"] = _capture_container(containers_dir)
    snap["host"] = _capture_host()
    snap["dev_repos"] = _capture_dev_repos(dev_repos or [])
    snap["lock_files"] = _capture_lock_files(containers_dir)

    return snap


# ---------------------------------------------------------------------------
# Container section
# ---------------------------------------------------------------------------


def _capture_container(containers_dir: str | Path | None) -> dict[str, Any]:
    """Capture container version and SIF hash."""
    result: dict[str, Any] = {}

    try:
        from .apptainer import find_containers_dir, get_active_version

        cdir: Path
        if containers_dir is not None:
            cdir = Path(containers_dir)
        else:
            cdir = find_containers_dir()

        version = get_active_version(cdir)
        result["version"] = version

        # Resolve the current.sif symlink to get the actual SIF path
        link = cdir / "current.sif"
        if link.is_symlink():
            sif_path = link.resolve()
            result["sif_path"] = str(sif_path)

            if sif_path.is_file():
                result["sif_sha256"] = _sha256_file(sif_path)

                # Look for a .def-hash sidecar file
                def_hash_file = sif_path.with_suffix(".def-hash")
                if def_hash_file.is_file():
                    result["def_hash"] = def_hash_file.read_text().strip()
        elif link.is_file():
            # Plain file (not a symlink) — unusual but handle it
            result["sif_path"] = str(link)
            result["sif_sha256"] = _sha256_file(link)

    except Exception:
        # Gracefully degrade — return whatever was gathered
        pass

    return result


# ---------------------------------------------------------------------------
# Host section
# ---------------------------------------------------------------------------


def _capture_host() -> dict[str, Any]:
    """Capture host package installation status."""
    result: dict[str, Any] = {}

    try:
        from .host import check_packages

        packages = check_packages()
        for pkg_name, info in packages.items():
            result[pkg_name] = {
                "installed": info.get("installed", False),
                "version": info.get("version", ""),
            }
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Dev repos section
# ---------------------------------------------------------------------------


def _capture_dev_repos(repo_paths: list[str | Path]) -> list[dict[str, Any]]:
    """Capture git metadata for each dev repo path."""
    repos: list[dict[str, Any]] = []

    for raw_path in repo_paths:
        entry = _capture_one_repo(Path(raw_path))
        repos.append(entry)

    return repos


def _capture_one_repo(repo_path: Path) -> dict[str, Any]:
    """Capture git metadata for a single repository path."""
    entry: dict[str, Any] = {
        "name": repo_path.name,
        "path": str(repo_path.resolve()),
    }

    if not repo_path.exists():
        entry["error"] = "path does not exist"
        return entry

    git = shutil.which("git")
    if git is None:
        entry["error"] = "git not found"
        return entry

    def _run(args: list[str]) -> str:
        """Run a git command and return stripped stdout, or '' on failure."""
        try:
            proc = subprocess.run(
                [git, "-C", str(repo_path)] + args,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.stdout.strip() if proc.returncode == 0 else ""
        except Exception:
            return ""

    commit = _run(["rev-parse", "HEAD"])
    if commit:
        entry["commit"] = commit

    branch = _run(["branch", "--show-current"])
    if branch:
        entry["branch"] = branch

    porcelain = _run(["status", "--porcelain"])
    entry["dirty"] = bool(porcelain)

    return entry


# ---------------------------------------------------------------------------
# Lock files section
# ---------------------------------------------------------------------------


def _capture_lock_files(containers_dir: str | Path | None) -> dict[str, Any]:
    """Capture SHA256 hashes of lock files in the containers directory."""
    result: dict[str, Any] = {}

    try:
        from .apptainer import find_containers_dir

        cdir: Path
        if containers_dir is not None:
            cdir = Path(containers_dir)
        else:
            cdir = find_containers_dir()

        # pip lock (requirements_lock.txt or requirements.lock)
        for candidate in ("requirements_lock.txt", "requirements.lock"):
            lock_path = cdir / candidate
            if lock_path.is_file():
                result["pip"] = _sha256_file(lock_path)
                break

        # dpkg lock
        for candidate in ("dpkg_lock.txt", "dpkg.lock"):
            lock_path = cdir / candidate
            if lock_path.is_file():
                result["dpkg"] = _sha256_file(lock_path)
                break

    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Compute SHA256 hex digest of a file, reading in chunks."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


# EOF
