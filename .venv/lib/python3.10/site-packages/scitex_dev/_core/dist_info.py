#!/usr/bin/env python3
# Timestamp: 2026-03-27
# File: scitex_dev/_dist_info.py

"""Clean stale dist-info directories to prevent importlib.metadata confusion.

When pip install -e is run multiple times with different versions,
old dist-info directories accumulate. importlib.metadata may pick up
the oldest one, causing skills export to read stale content.
"""

from __future__ import annotations

import logging
import shutil
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


def clean_stale_dist_info() -> list[str]:
    """Remove stale dist-info directories, keeping only the newest per package.

    Returns
    -------
    list[str]
        Names of removed dist-info directories.
    """
    import site

    site_dirs = site.getsitepackages() if hasattr(site, "getsitepackages") else []
    removed: list[str] = []

    for site_dir in site_dirs:
        sp = Path(site_dir)
        if not sp.is_dir():
            continue

        by_package: dict[str, list[Path]] = defaultdict(list)
        for d in sp.glob("*.dist-info"):
            parts = d.name.rsplit("-", 1)
            if len(parts) == 2:
                by_package[parts[0]].append(d)

        for _pkg_name, dirs in by_package.items():
            if len(dirs) <= 1:
                continue
            dirs.sort(key=lambda d: d.stat().st_mtime)
            for stale in dirs[:-1]:
                logger.info("Removing stale dist-info: %s", stale.name)
                shutil.rmtree(stale)
                removed.append(stale.name)

    return removed


# EOF
