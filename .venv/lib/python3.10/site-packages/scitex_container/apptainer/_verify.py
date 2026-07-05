#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/apptainer/_verify.py
"""Verify container integrity: SIF hash, .def origin, and lock file consistency."""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

from scitex_container._compat import supports_return_as

from ._utils import detect_container_cmd

logger = logging.getLogger(__name__)


def _hash_file(path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA256 of a file in chunks (handles large SIFs)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


@supports_return_as
def verify(
    sif_path: str | Path,
    def_path: str | Path | None = None,
    lock_dir: str | Path | None = None,
) -> dict:
    """Verify container integrity.

    Checks:

    1. SIF exists and computes its SHA256
    2. If def_path given, compares .def hash against stored .def-hash
    3. If lock files exist, runs pip freeze / dpkg-query inside the SIF
       and compares against stored lock files

    Parameters
    ----------
    sif_path : str or Path
        Path to the .sif file to verify.
    def_path : str or Path, optional
        Path to the .def file that should have produced this SIF.
    lock_dir : str or Path, optional
        Directory containing lock files (requirements-lock.txt, dpkg-lock.txt).
        Defaults to same directory as the SIF.

    Returns
    -------
    dict
        Verification results::

            {
                "sif": {"path": "...", "sha256": "...", "exists": True},
                "def_origin": {"status": "pass|fail|skip", "detail": "..."},
                "pip_lock": {"status": "pass|fail|skip", "detail": "...", "diff_count": 0},
                "dpkg_lock": {"status": "pass|fail|skip", "detail": "...", "diff_count": 0},
                "overall": "pass|fail"
            }
    """
    sif_path = Path(sif_path)
    result = {
        "sif": {"path": str(sif_path), "sha256": None, "exists": False},
        "def_origin": {"status": "skip", "detail": "No .def provided"},
        "pip_lock": {"status": "skip", "detail": "No lock file found"},
        "dpkg_lock": {"status": "skip", "detail": "No lock file found"},
        "overall": "pass",
    }

    # --- Check 1: SIF exists + SHA256 ---
    if not sif_path.exists():
        result["sif"]["exists"] = False
        result["overall"] = "fail"
        return result

    result["sif"]["exists"] = True
    logger.info("Computing SHA256 of %s (this may take a moment)...", sif_path.name)
    result["sif"]["sha256"] = _hash_file(sif_path)

    # --- Check 2: .def origin ---
    if def_path is not None:
        def_path = Path(def_path)
        hash_file = sif_path.parent / ".def-hash"

        if not def_path.exists():
            result["def_origin"] = {
                "status": "fail",
                "detail": f".def not found: {def_path}",
            }
            result["overall"] = "fail"
        elif not hash_file.exists():
            result["def_origin"] = {
                "status": "fail",
                "detail": "No stored .def-hash found",
            }
            result["overall"] = "fail"
        else:
            current_def_hash = _hash_file(def_path)
            stored_hash = hash_file.read_text().strip()
            if current_def_hash == stored_hash:
                result["def_origin"] = {
                    "status": "pass",
                    "detail": f"def hash matches: {current_def_hash[:16]}...",
                }
            else:
                result["def_origin"] = {
                    "status": "fail",
                    "detail": (
                        f"def hash mismatch: "
                        f"current={current_def_hash[:16]}... "
                        f"stored={stored_hash[:16]}..."
                    ),
                }
                result["overall"] = "fail"

    # --- Check 3: Lock file verification ---
    lock_path = Path(lock_dir) if lock_dir else sif_path.parent
    cmd = None
    try:
        cmd = detect_container_cmd()
    except FileNotFoundError:
        result["pip_lock"]["detail"] = "No container command found"
        result["dpkg_lock"]["detail"] = "No container command found"

    if cmd:
        # pip lock
        pip_lock_file = lock_path / "requirements-lock.txt"
        if pip_lock_file.exists():
            result["pip_lock"] = _verify_pip_lock(cmd, sif_path, pip_lock_file)
            if result["pip_lock"]["status"] == "fail":
                result["overall"] = "fail"

        # dpkg lock
        dpkg_lock_file = lock_path / "dpkg-lock.txt"
        if dpkg_lock_file.exists():
            result["dpkg_lock"] = _verify_dpkg_lock(cmd, sif_path, dpkg_lock_file)
            if result["dpkg_lock"]["status"] == "fail":
                result["overall"] = "fail"

    return result


def _verify_pip_lock(cmd: str, sif_path: Path, lock_file: Path) -> dict:
    """Compare pip freeze output against stored lock file."""
    try:
        proc = subprocess.run(
            [cmd, "exec", str(sif_path), "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return {
                "status": "fail",
                "detail": f"pip freeze failed: {proc.stderr[:200]}",
                "diff_count": -1,
            }

        current = set(proc.stdout.strip().splitlines())
        stored = set(lock_file.read_text().strip().splitlines())

        added = current - stored
        removed = stored - current
        diff_count = len(added) + len(removed)

        if diff_count == 0:
            return {
                "status": "pass",
                "detail": f"All {len(current)} packages match",
                "diff_count": 0,
            }
        else:
            detail_parts = []
            if added:
                detail_parts.append(f"+{len(added)} new")
            if removed:
                detail_parts.append(f"-{len(removed)} missing")
            return {
                "status": "fail",
                "detail": f"Package mismatch: {', '.join(detail_parts)}",
                "diff_count": diff_count,
                "added": sorted(added)[:10],
                "removed": sorted(removed)[:10],
            }
    except subprocess.TimeoutExpired:
        return {"status": "fail", "detail": "pip freeze timed out", "diff_count": -1}
    except Exception as exc:
        return {"status": "fail", "detail": str(exc), "diff_count": -1}


def _verify_dpkg_lock(cmd: str, sif_path: Path, lock_file: Path) -> dict:
    """Compare dpkg packages against stored lock file."""
    try:
        proc = subprocess.run(
            [
                cmd,
                "exec",
                str(sif_path),
                "dpkg-query",
                "-W",
                "-f=${Package}=${Version}\n",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return {
                "status": "fail",
                "detail": f"dpkg-query failed: {proc.stderr[:200]}",
                "diff_count": -1,
            }

        current = set(proc.stdout.strip().splitlines())
        stored = set(lock_file.read_text().strip().splitlines())

        added = current - stored
        removed = stored - current
        diff_count = len(added) + len(removed)

        if diff_count == 0:
            return {
                "status": "pass",
                "detail": f"All {len(current)} packages match",
                "diff_count": 0,
            }
        else:
            detail_parts = []
            if added:
                detail_parts.append(f"+{len(added)} changed/new")
            if removed:
                detail_parts.append(f"-{len(removed)} missing/changed")
            return {
                "status": "fail",
                "detail": f"Package mismatch: {', '.join(detail_parts)}",
                "diff_count": diff_count,
            }
    except subprocess.TimeoutExpired:
        return {"status": "fail", "detail": "dpkg-query timed out", "diff_count": -1}
    except Exception as exc:
        return {"status": "fail", "detail": str(exc), "diff_count": -1}


# EOF
