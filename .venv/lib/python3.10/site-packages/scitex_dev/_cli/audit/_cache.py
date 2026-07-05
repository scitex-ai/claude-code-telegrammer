"""Per-package JSON audit cache.

Keys cache entries by (a) the target package's git HEAD SHA and (b)
scitex-dev's own version, so a cache hit is only returned when both
target and auditor are unchanged since the cached run.

Dirty working trees are NEVER cached — a clean cache should reflect
clean, committed state, not transient edits.

Layout:
    ~/.scitex/dev/runtime/audit-cache/<pkg>.json
    {
        "auditor_fp": "0.11.9.dev24+g5a087",
        "<auditor>": {
            "target_fp": "<sha>",
            "errors":     <int>,
            "warnings":   <int>,
            "run_at":     "<iso>",
            "payload":    {...}     # optional full --json output
        },
        ...
    }
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _scitex_dir() -> Path:
    """Honour `$SCITEX_DIR` per local-state-directories §6."""
    return Path(os.environ.get("SCITEX_DIR", os.path.expanduser("~/.scitex")))


def cache_root() -> Path:
    """Project-wide audit cache root (gitignored under §4b runtime/)."""
    return _scitex_dir() / "dev" / "runtime" / "audit-cache"


def cache_path(pkg: str) -> Path:
    return cache_root() / f"{pkg}.json"


def target_fingerprint(repo: Path) -> str | None:
    """Return the git HEAD SHA, or None if the working tree is dirty.

    Dirty trees opt out of caching — we never want to memoise an audit
    result tied to transient un-pushed state. Callers should treat None
    as "always cache miss".
    """
    try:
        head = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return None
    try:
        # Quick clean-tree check. `--quiet` returns 1 if any changes.
        rc = subprocess.call(
            ["git", "-C", str(repo), "diff", "--quiet", "HEAD"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if rc != 0:
        return None
    # Untracked files don't invalidate a clean cache (they aren't read
    # by the auditor by definition — auditors scan tracked sources).
    return head


_AUDITOR_FP_CACHE: list[str | None] = [None]


def auditor_fingerprint() -> str:
    """`scitex-dev`'s own version string. Cached for the process
    lifetime since it never changes mid-run.
    """
    if _AUDITOR_FP_CACHE[0] is not None:
        return _AUDITOR_FP_CACHE[0]
    try:
        from scitex_dev._version import __version__  # type: ignore
    except ImportError:
        try:
            from scitex_dev import __version__  # type: ignore[attr-defined]
        except ImportError:
            __version__ = "unknown"
    _AUDITOR_FP_CACHE[0] = str(__version__)
    return _AUDITOR_FP_CACHE[0]


def load(pkg: str, auditor: str, *, target_fp: str | None) -> dict | None:
    """Return cached entry if both fingerprints match, else None.

    `target_fp` is the caller's pre-computed git HEAD for the pkg; if
    None (dirty tree) we always return None.
    """
    if target_fp is None:
        return None
    p = cache_path(pkg)
    if not p.is_file():
        return None
    try:
        blob = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if blob.get("auditor_fp") != auditor_fingerprint():
        return None
    entry = blob.get(auditor)
    if not isinstance(entry, dict):
        return None
    if entry.get("target_fp") != target_fp:
        return None
    return entry


def save(
    pkg: str,
    auditor: str,
    *,
    target_fp: str,
    errors: int,
    warnings: int,
    payload: dict | None = None,
) -> None:
    """Upsert an entry. Dirty trees should never reach this path."""
    p = cache_path(pkg)
    p.parent.mkdir(parents=True, exist_ok=True)

    blob: dict = {}
    if p.is_file():
        try:
            blob = json.loads(p.read_text()) or {}
        except (OSError, json.JSONDecodeError):
            blob = {}

    # Whole-file auditor_fp guard: if scitex-dev's version moved since
    # last save, every entry in the file is stale — wipe and start over.
    afp = auditor_fingerprint()
    if blob.get("auditor_fp") != afp:
        blob = {"auditor_fp": afp}

    blob[auditor] = {
        "target_fp": target_fp,
        "errors": int(errors),
        "warnings": int(warnings),
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if payload is not None:
        blob[auditor]["payload"] = payload

    # Atomic write: temp file + rename so concurrent readers never see
    # half-written JSON.
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=2))
    os.replace(tmp, p)


def clear(pkg: str | None = None) -> int:
    """Drop cache entries. With `pkg`, only that package's file. With
    None, the entire cache root. Returns the number of files removed.
    """
    root = cache_root()
    if not root.is_dir():
        return 0
    targets: list[Path] = [cache_path(pkg)] if pkg else list(root.glob("*.json"))
    n = 0
    for p in targets:
        if p.is_file():
            p.unlink()
            n += 1
    return n


__all__ = [
    "cache_root",
    "cache_path",
    "target_fingerprint",
    "auditor_fingerprint",
    "load",
    "save",
    "clear",
]
