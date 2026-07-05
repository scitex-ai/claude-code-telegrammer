#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discover scitex ecosystem packages that expose docs via entry points.

Each package registers itself in pyproject.toml:
    [project.entry-points."scitex_dev.docs"]
    scitex-writer = "scitex_writer"

This module lazily discovers all registered packages and caches the result.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "scitex_dev.docs"

# Cache: populated on first call, cleared by invalidate_cache()
_cache: Optional[dict[str, str]] = None


def discover_packages(
    *,
    entry_points_fn=None,
    ecosystem: Optional[dict] = None,
    use_cache: bool = True,
) -> dict[str, str]:
    """Discover all ecosystem packages, merging entry points with ECOSYSTEM.

    Uses entry points as primary source, then fills in missing packages
    from ECOSYSTEM dict with a warning for each missing entry point.

    ``entry_points_fn`` / ``ecosystem`` are test-injection seams (default
    behavior is unchanged when both are ``None``). When either is supplied,
    or ``use_cache`` is False, the result bypasses the module cache.

    Returns:
        Dict mapping package name → Python module name.
        e.g. {"scitex-writer": "scitex_writer", "figrecipe": "figrecipe"}
    """
    global _cache
    injected = entry_points_fn is not None or ecosystem is not None
    if use_cache and not injected and _cache is not None:
        return _cache

    packages = {}

    # 1. Entry points (primary — these packages registered correctly)
    try:
        if entry_points_fn is None:
            from importlib.metadata import entry_points

            eps = entry_points(group=_ENTRY_POINT_GROUP)
        else:
            eps = entry_points_fn(group=_ENTRY_POINT_GROUP)
        for ep in eps:
            packages[ep.name] = ep.value
    except Exception:
        logger.debug("Failed to discover entry points for %s", _ENTRY_POINT_GROUP)

    # 2. Fill in from ECOSYSTEM (source of truth for all packages)
    try:
        if ecosystem is None:
            from .._ecosystem import ECOSYSTEM
        else:
            ECOSYSTEM = ecosystem

        from importlib.metadata import PackageNotFoundError, distribution

        for pip_name, info in ECOSYSTEM.items():
            if pip_name not in packages:
                import_name = info.get("import_name", pip_name.replace("-", "_"))
                # Check if installed via metadata (no module import needed)
                dist_name = import_name.replace("_", "-")
                installed = False
                for name in [dist_name, import_name, pip_name]:
                    try:
                        distribution(name)
                        installed = True
                        break
                    except PackageNotFoundError:
                        continue
                if not installed:
                    continue
                packages[pip_name] = import_name
                # Demoted from WARNING to DEBUG: this is a packaging hint for
                # maintainers, not an error users should see on every CLI invocation.
                # Was producing 30+ noise lines on `scitex skills list`.
                logger.debug(
                    "Package '%s' missing scitex_dev.docs entry point — "
                    'add [project.entry-points."scitex_dev.docs"] to its pyproject.toml',
                    pip_name,
                )
    except ImportError:
        logger.debug("ECOSYSTEM not available for fallback discovery")

    if use_cache and not injected:
        _cache = packages
    return packages


def invalidate_cache() -> None:
    """Clear the discovery cache. Useful after installing new packages."""
    global _cache
    _cache = None


def get_package_root(module_name: str) -> Optional[Path]:
    """Get the installed root directory of a Python package.

    Uses importlib.metadata to resolve the path WITHOUT importing the module.
    This avoids triggering heavy module initialization (numpy, torch, etc.)
    which can take seconds per package.

    Falls back to importlib.import_module only if metadata resolution fails.

    Args:
        module_name: Python import name (e.g. "scitex_writer")

    Returns:
        Path to the package directory, or None if not found.
    """
    root = _get_package_root_fast(module_name)
    if root is not None:
        return root

    # Slow fallback: actually import the module
    try:
        mod = importlib.import_module(module_name)
        if hasattr(mod, "__path__"):
            return Path(mod.__path__[0])
        elif hasattr(mod, "__file__") and mod.__file__:
            return Path(mod.__file__).parent
    except ImportError:
        pass
    return None


def _get_package_root_fast(module_name: str) -> Optional[Path]:
    """Resolve package root via importlib.metadata — no module import needed.

    Handles both regular installs (site-packages) and editable installs
    (pip install -e, using direct_url.json).
    """
    import json as _json

    from importlib.metadata import PackageNotFoundError, distribution

    dist_name = module_name.replace("_", "-")
    dist = None
    for name in [dist_name, module_name]:
        try:
            dist = distribution(name)
            break
        except PackageNotFoundError:
            continue
    if dist is None:
        return None

    # Method 1: Editable install — read direct_url.json for source path (check FIRST)
    try:
        du_text = dist.read_text("direct_url.json")
        if du_text:
            du = _json.loads(du_text)
            url = du.get("url", "")
            if url.startswith("file:///"):
                project_root = Path(url[7:])
                # Standard layout: src/<module_name>/
                src_dir = project_root / "src" / module_name
                if src_dir.is_dir():
                    return src_dir
                # Flat layout: <module_name>/ at project root
                flat_dir = project_root / module_name
                if flat_dir.is_dir():
                    return flat_dir
    except Exception:
        pass

    # Method 2: Regular install — dist._path.parent / module_name
    if hasattr(dist, "_path") and dist._path:
        pkg_dir = dist._path.parent / module_name
        if pkg_dir.is_dir():
            return pkg_dir

    return None


_CORE_PACKAGES = {"scitex", "scitex-hub"}


def get_package_metadata(pip_name: str) -> Optional[dict]:
    """Get display metadata for a package from importlib.metadata.

    Returns:
        Dict with keys: pip_name, module_name, description, version,
        github_url, github_repo, is_core. None if package not found.
    """
    discovered = discover_packages()
    module_name = discovered.get(pip_name)

    try:
        from importlib.metadata import metadata as get_metadata

        meta = get_metadata(pip_name)
    except Exception:
        if module_name is None:
            return None
        # Package registered but metadata not available
        return {
            "pip_name": pip_name,
            "module_name": module_name,
            "description": "",
            "version": "",
            "github_url": "",
            "github_repo": pip_name,
            "is_core": pip_name in _CORE_PACKAGES,
        }

    # Extract Repository URL from Project-URL fields
    github_url = ""
    github_repo = pip_name
    urls = meta.get_all("Project-URL") or []
    for url_entry in urls:
        label, _, url = url_entry.partition(",")
        url = url.strip()
        if label.strip().lower() in ("repository", "homepage"):
            github_url = url
            # Extract repo name from github URL
            parts = url.rstrip("/").rstrip(".git").rsplit("/", 1)
            if len(parts) == 2:
                github_repo = parts[1]
            break

    return {
        "pip_name": pip_name,
        "module_name": module_name or pip_name.replace("-", "_"),
        "description": meta.get("Summary", ""),
        "version": meta.get("Version", ""),
        "github_url": github_url,
        "github_repo": github_repo,
        "is_core": pip_name in _CORE_PACKAGES,
    }


def get_sphinx_source(module_name: str) -> Optional[Path]:
    """Find the Sphinx source directory for a package (dev environment only).

    Looks for docs/sphinx/conf.py relative to the package's repo root.
    """
    pkg_root = get_package_root(module_name)
    if pkg_root is None:
        return None

    # Walk up to find repo root (has pyproject.toml or .git)
    candidate = pkg_root
    for _ in range(5):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            sphinx_dir = candidate / "docs" / "sphinx"
            if (sphinx_dir / "conf.py").exists():
                return sphinx_dir
            break
    return None
