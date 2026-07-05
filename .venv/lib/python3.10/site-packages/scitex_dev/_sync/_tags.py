#!/usr/bin/env python3
# Timestamp: 2026-04-27
# File: scitex_dev/sync_tags.py

"""Push local git tags for ecosystem packages to origin.

Extracted from ``sync.py`` to keep that module under the line-limit.
``scitex_dev.sync`` re-exports ``sync_tags`` for backward compat.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .._core.config import DevConfig, load_config


def sync_tags(
    packages: list[str] | None = None,
    confirm: bool = False,
    config: DevConfig | None = None,
) -> dict[str, Any]:
    """Push local tags for all packages to origin.

    Safety: defaults to preview only. Pass confirm=True to execute.

    Parameters
    ----------
    packages : list[str] | None
        Package names. None = all configured packages.
    confirm : bool
        If False (default), preview only.
        If True, execute git push --tags.
    config : DevConfig | None
        Configuration.

    Returns
    -------
    dict
        {package: {status, tag, output|commands}}.
    """
    if config is None:
        config = load_config()

    targets = config.packages
    if packages:
        targets = [p for p in targets if p.name in packages]

    results: dict[str, Any] = {}
    for pkg in targets:
        if not pkg.local_path:
            continue

        path = Path(pkg.local_path).expanduser()
        if not path.exists():
            results[pkg.name] = {"status": "skipped", "error": f"{path} not found"}
            continue

        try:
            tag_result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                cwd=str(path),
                timeout=10,
            )
            tag = tag_result.stdout.strip() if tag_result.returncode == 0 else None
        except Exception:
            tag = None

        if not confirm:
            results[pkg.name] = {
                "status": "dry_run",
                "tag": tag,
                "commands": ["git", "push", "origin", "--tags"],
            }
            continue

        try:
            push_result = subprocess.run(
                ["git", "push", "origin", "--tags"],
                capture_output=True,
                text=True,
                cwd=str(path),
                timeout=30,
            )
            if push_result.returncode == 0:
                results[pkg.name] = {
                    "status": "ok",
                    "tag": tag,
                    "output": push_result.stderr.strip(),
                }
            else:
                results[pkg.name] = {
                    "status": "error",
                    "tag": tag,
                    "error": push_result.stderr.strip(),
                }
        except Exception as e:
            results[pkg.name] = {"status": "error", "error": str(e)}
    return results


# EOF
