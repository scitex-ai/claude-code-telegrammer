"""Auditor freshness check — warn if running scitex-dev < PyPI latest.

Background — 2026-05: a user ran `scitex-dev ecosystem audit-all
scitex-io` against scitex-io's modernised README and got six false-
positive errors (PS-131, PS-141, PS-142, etc.). Cause: the installed
auditor was 0.11.8 while PyPI was on 0.11.11 — three relaxations
shipped in between (Quick-Start as Demo alias, visual-anywhere,
collapse-all-interfaces). The rule corpus had moved; the local
auditor hadn't.

This module adds a pre-audit self-check:

    - Fetch the latest scitex-dev version on PyPI (cheap; cached 6 h).
    - Compare to the installed version.
    - If installed < latest, emit a clear stderr warning telling the
      user how to upgrade. Audit proceeds (warning, not hard fail) so
      that air-gapped boxes still work.

Behaviour can be turned off explicitly with --no-version-check or by
setting SCITEX_DEV_SKIP_VERSION_CHECK=1.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

_CACHE_TTL = timedelta(hours=6)
_PYPI_URL = "https://pypi.org/pypi/scitex-dev/json"


def _scitex_dir() -> Path:
    return Path(os.environ.get("SCITEX_DIR", os.path.expanduser("~/.scitex")))


def _cache_path() -> Path:
    return _scitex_dir() / "dev" / "runtime" / "auditor-version-check.json"


def _installed_version() -> str:
    try:
        from scitex_dev import __version__  # type: ignore[attr-defined]

        return str(__version__)
    except Exception:
        return "0.0.0"


def _normalize(v: str) -> tuple[int, ...]:
    """Tuple-compare-friendly version parse — strips leading 'v' and any
    PEP 440 suffix (`.dev`, `+local`, `a1`, etc.). Returns (0, 0, 0)
    on parse failure so unknown locals never look 'newer'.
    """
    v = v.lstrip("vV").split("+", 1)[0]
    head: list[int] = []
    for part in v.split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        head.append(int(digits))
    return tuple(head)


def _read_cache() -> tuple[str, datetime] | None:
    p = _cache_path()
    if not p.is_file():
        return None
    try:
        blob = json.loads(p.read_text())
        v = str(blob["latest"])
        ts = datetime.fromisoformat(blob["fetched_at"])
        return v, ts
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _write_cache(latest: str) -> None:
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "latest": latest,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=2))
    os.replace(tmp, p)


def _fetch_latest_from_pypi(timeout: float = 3.0) -> str | None:
    try:
        with urllib.request.urlopen(_PYPI_URL, timeout=timeout) as resp:
            data = json.load(resp)
        return str(data["info"]["version"])
    except Exception:
        return None


def latest_known() -> str | None:
    """Return the latest scitex-dev version, cached for 6 h. Returns
    None on network failure with no usable cache."""
    cached = _read_cache()
    if cached is not None:
        v, fetched_at = cached
        if datetime.now(timezone.utc) - fetched_at < _CACHE_TTL:
            return v
    latest = _fetch_latest_from_pypi()
    if latest is not None:
        _write_cache(latest)
        return latest
    return cached[0] if cached is not None else None


def warn_if_stale(*, stream=sys.stderr) -> bool:
    """Emit a one-line warning if installed < latest. Returns True if
    a warning was emitted, False otherwise.

    Honors:
      - SCITEX_DEV_SKIP_VERSION_CHECK=1 — skip the check entirely
      - SCITEX_DEV_VERSION_CHECK_SILENT=1 — suppress the print (still
        returns True so a caller can react)
    """
    if os.environ.get("SCITEX_DEV_SKIP_VERSION_CHECK"):
        return False
    installed = _installed_version()
    latest = latest_known()
    if latest is None:
        return False  # offline; can't compare — silent
    if _normalize(installed) >= _normalize(latest):
        return False  # up to date (or running a dev build ahead)
    if not os.environ.get("SCITEX_DEV_VERSION_CHECK_SILENT"):
        msg = (
            "\033[33m"
            f"WARN  scitex-dev {installed} is older than the latest "
            f"{latest} on PyPI. Rule corpus may have moved on — audit "
            f"results below may be stale. Upgrade: pip install -U "
            f"scitex-dev (or `--no-version-check` to silence).\033[0m"
        )
        print(msg, file=stream, flush=True)
    return True
