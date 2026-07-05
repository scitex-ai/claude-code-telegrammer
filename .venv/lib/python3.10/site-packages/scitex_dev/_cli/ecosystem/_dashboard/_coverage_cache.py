"""Per-package coverage cache for the ecosystem dashboard.

Mirrors the audit cache layout (``audit/_cache.py``) so coverage cells
in `scitex-dev ecosystem dashboard list` fill in instantly on the
dashboard's hot path:

1. Cheap path (preferred): the package has a fresh
   ``<repo>/coverage.xml`` (Cobertura, written by `pytest --cov-report=xml`
   in CI or locally). Parse it, cache the resulting ratio keyed by the
   package's git HEAD SHA, and return.

2. Cache hit: HEAD SHA matches the cached ``target_fp`` -> return the
   cached value. Dashboard refreshes don't re-run pytest.

3. Cache miss + no coverage.xml: leave ``state.coverage`` at -1 so the
   renderer prints "N/C". The heavy `--with-tests run` path will
   eventually write coverage.xml + populate the cache.

Dirty trees opt out of caching (same rule as the audit cache).

Layout:
    $SCITEX_DIR/dev/runtime/coverage-cache/<pkg>.json
    {
        "target_fp": "<git HEAD SHA>",
        "coverage":  0.6837,            # float in [0, 1]
        "source":    "coverage.xml"     # or "tests-run" or "codecov"
        "run_at":    "<iso>",
    }
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _scitex_dir() -> Path:
    return Path(os.environ.get("SCITEX_DIR", os.path.expanduser("~/.scitex")))


def cache_root() -> Path:
    return _scitex_dir() / "dev" / "runtime" / "coverage-cache"


def cache_path(pkg: str) -> Path:
    return cache_root() / f"{pkg}.json"


def target_fingerprint(repo: Path) -> str | None:
    """Return git HEAD SHA, or None if the working tree is dirty.

    Dirty trees opt out of caching — we don't memoise a coverage number
    tied to transient un-pushed state.
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
    return head


def load(pkg: str, *, target_fp: str | None) -> float | None:
    """Return cached coverage ratio (0..1) or None.

    ``target_fp`` is the caller's pre-computed git HEAD; pass None for
    dirty trees to force a cache miss.
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
    if blob.get("target_fp") != target_fp:
        return None
    cov = blob.get("coverage")
    if isinstance(cov, (int, float)):
        return float(cov)
    return None


def save(
    pkg: str,
    *,
    target_fp: str,
    coverage: float,
    source: str = "coverage.xml",
) -> None:
    """Upsert a cache entry. Dirty trees should never reach this path."""
    p = cache_path(pkg)
    p.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "target_fp": str(target_fp),
        "coverage": float(coverage),
        "source": str(source),
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=2))
    os.replace(tmp, p)


def clear(pkg: str | None = None) -> int:
    """Drop cache entries. With `pkg`, only that pkg's file. With None,
    the entire cache root. Returns count of files removed."""
    root = cache_root()
    if not root.is_dir():
        return 0
    targets = [cache_path(pkg)] if pkg else list(root.glob("*.json"))
    n = 0
    for t in targets:
        try:
            t.unlink()
            n += 1
        except FileNotFoundError:
            continue
    return n
