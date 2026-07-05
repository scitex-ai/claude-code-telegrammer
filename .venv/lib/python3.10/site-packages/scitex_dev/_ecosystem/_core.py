#!/usr/bin/env python3
# Timestamp: 2026-06-07
# File: scitex_dev/_ecosystem/_core.py

"""SciTeX ecosystem helpers — local-path resolution + audit-skip policy.

The package registry itself (``PackageInfo`` schema + ``ECOSYSTEM``
dict) lives in the sibling ``_registry`` module so the data table and
the helpers can grow independently and stay under the line-limit
hook. Both names are re-exported here so every existing
``from scitex_dev._ecosystem._core import ECOSYSTEM`` import keeps
working unchanged.
"""

from pathlib import Path
from typing import List, Optional

from ._registry import ECOSYSTEM, PackageInfo

__all__ = [
    "ECOSYSTEM",
    "PackageInfo",
    "get_all_packages",
    "get_local_path",
    "should_skip_audit",
]


def get_local_path(package: str) -> Optional[Path]:
    """Get expanded local path for a package."""
    if package not in ECOSYSTEM:
        return None
    return Path(ECOSYSTEM[package]["local_path"]).expanduser()


def get_all_packages() -> List[str]:
    """Get list of all ecosystem package names."""
    return list(ECOSYSTEM.keys())


# --------------------------------------------------------------------- #
# Category-aware audit skip                                              #
# --------------------------------------------------------------------- #

# Per-auditor list of ECOSYSTEM categories that don't apply.
# ``archived`` is short-circuited separately (every auditor skips
# archived).
_CATEGORY_SKIP: dict[str, frozenset[str]] = {
    "audit-cli": frozenset({"template"}),
    "audit-mcp-tools": frozenset({"template", "dataset", "umbrella"}),
    "audit-skills": frozenset(),
    "audit-python-apis": frozenset({"template"}),
    "audit-project": frozenset(),
}


def should_skip_audit(package: str, auditor: str) -> tuple[bool, str]:
    """Return ``(skip, reason)`` for running ``auditor`` on ``package``.

    ``auditor`` is one of the keys in ``_CATEGORY_SKIP``. Unknown
    auditors return ``(False, "")`` — fail open so a typo doesn't
    silently skip.

    Skip semantics:

    - archived packages are skipped for *every* auditor.
    - per-auditor categories listed in ``_CATEGORY_SKIP`` are skipped.
    - unknown package (not in ECOSYSTEM) is NOT skipped — the
      auditor's own not-found path will handle it.
    """
    info = ECOSYSTEM.get(package)
    if info is None:
        return False, ""
    if info.get("archived"):
        return True, "archived"
    cat = info.get("category", "")
    skip_set = _CATEGORY_SKIP.get(auditor, frozenset())
    if cat in skip_set:
        return True, f"category={cat}"
    return False, ""


# EOF
