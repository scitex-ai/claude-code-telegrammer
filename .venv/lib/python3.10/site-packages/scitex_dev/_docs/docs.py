#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Public API for docs aggregation and retrieval across the SciTeX ecosystem.

Usage:
    from scitex_dev import get_docs, build_docs

    # All installed packages (manifest overview)
    get_docs()

    # Single package — returns unwrapped result
    get_docs(package="scitex-writer", format="json")

    # Multiple packages — dict keyed by package name
    get_docs(packages=["scitex-writer", "scitex-stats"], format="json")

    # Specific page
    get_docs(package="scitex-writer", format="html", page="api")

    # Build docs from Sphinx source
    build_docs(package="scitex-writer")
    build_docs()  # all discovered packages

    # Search across all packages
    search_docs(query="save figure")
    search_docs(query="statistics", packages=["scitex-stats"])
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .._core.discovery import discover_packages, get_package_root, get_sphinx_source

logger = logging.getLogger(__name__)


def get_docs(
    package: Optional[str] = None,
    packages: Optional[list[str]] = None,
    format: Optional[str] = None,
    page: Optional[str] = None,
    *,
    _discover_fn=None,
    _root_fn=None,
    _sphinx_fn=None,
) -> Any:
    """Get documentation for one, several, or all installed SciTeX packages.

    Resolution chain per package:
        1. Pre-built _sphinx_html/ in installed package → fastest (production)
        2. Sphinx _build/ available → use existing build
        3. Neither → introspect from docstrings + signatures (always works)

    Args:
        package: Single package name (returns unwrapped result).
        packages: List of package names (returns dict keyed by name).
        format: Output format — None for manifest, "json" for structured,
                "html" for path to HTML directory.
        page: Specific page name (only with format="html" or "json").

    Returns:
        - If package=: the doc result directly (unwrapped).
        - If packages=: dict mapping package name → doc result.
        - If neither: dict of all discovered packages → doc result.

    Raises:
        ValueError: If both package= and packages= are given.
        LookupError: If a requested package is not found.
    """
    if package is not None and packages is not None:
        raise ValueError(
            "Use either package= (singular) or packages= (plural), not both"
        )

    discover = _discover_fn if _discover_fn is not None else discover_packages

    # Single package — unwrap
    if package is not None:
        return _get_one(
            package,
            format=format,
            page=page,
            _discover_fn=discover,
            _root_fn=_root_fn,
            _sphinx_fn=_sphinx_fn,
        )

    # Multiple or all packages
    if packages is None:
        discovered = discover()
        packages = list(discovered.keys())

    results = {}
    for pkg in packages:
        try:
            results[pkg] = _get_one(
                pkg,
                format=format,
                page=page,
                _discover_fn=discover,
                _root_fn=_root_fn,
                _sphinx_fn=_sphinx_fn,
            )
        except LookupError:
            logger.warning("Package %s not found, skipping", pkg)

    return results


def build_docs(
    package: Optional[str] = None,
    output_dir: Optional[Path] = None,
    formats: Optional[list[str]] = None,
    *,
    _discover_fn=None,
    _sphinx_fn=None,
) -> dict[str, Any]:
    """Build docs from Sphinx source for one or all packages.

    Args:
        package: Single package name. None = build all discovered.
        output_dir: Override output directory. Default: in-place (_build/).
        formats: List of builders ("html", "json"). Default: ["html"].

    Returns:
        Dict mapping package name → build result (path or error).

    Raises:
        LookupError: If package not found.
        RuntimeError: If Sphinx is not installed.
    """
    from .._core.builder import build_sphinx

    if formats is None:
        formats = ["html"]

    discover = _discover_fn if _discover_fn is not None else discover_packages
    sphinx = _sphinx_fn if _sphinx_fn is not None else get_sphinx_source

    discovered = discover()

    if package is not None:
        targets = {package: discovered.get(package)}
        if targets[package] is None:
            raise LookupError(
                f"Package '{package}' not found in scitex_dev.docs entry points. "
                f"Available: {list(discovered.keys())}"
            )
    else:
        targets = discovered

    results = {}
    for pkg_name, module_name in targets.items():
        if module_name is None:
            continue
        sphinx_src = sphinx(module_name)
        if sphinx_src is None:
            results[pkg_name] = {"error": "No Sphinx source found"}
            continue

        pkg_results = {}
        for fmt in formats:
            try:
                out = build_sphinx(
                    sphinx_src,
                    output_dir=(output_dir / fmt) if output_dir else None,
                    builder=fmt,
                )
                pkg_results[fmt] = str(out) if out else None
            except (RuntimeError, FileNotFoundError) as e:
                pkg_results[fmt] = {"error": str(e)}

        results[pkg_name] = pkg_results

    return results


def search_docs(
    query: str,
    package: Optional[str] = None,
    packages: Optional[list[str]] = None,
    max_results: int = 10,
    *,
    _discover_fn=None,
    _get_one_fn=None,
) -> list[dict[str, Any]]:
    """Search documentation across one, several, or all SciTeX packages.

    Simple keyword search over page titles and introspected content.
    Stdlib only — no external search dependencies.

    Args:
        query: Search query string (case-insensitive keyword matching).
        package: Search within a single package.
        packages: Search within specific packages.
        max_results: Maximum number of results to return.

    Returns:
        List of dicts with keys: package, name, title, score, match_type.
        Sorted by relevance score (descending).
    """
    query_lower = query.lower()
    query_terms = query_lower.split()
    results = []

    discover = _discover_fn if _discover_fn is not None else discover_packages
    get_one = _get_one_fn if _get_one_fn is not None else _get_one

    # Determine which packages to search
    if package is not None:
        search_targets = {package: None}
    elif packages is not None:
        search_targets = {p: None for p in packages}
    else:
        search_targets = discover()

    for pkg_name in search_targets:
        try:
            manifest = get_one(pkg_name)
        except LookupError:
            continue

        if not isinstance(manifest, dict):
            continue

        # Search page titles from manifest
        for page_entry in manifest.get("pages", []):
            if isinstance(page_entry, dict):
                name = page_entry.get("name", "")
                title = page_entry.get("title", "")
            else:
                name = str(page_entry)
                title = name

            text = f"{name} {title}".lower()
            score = sum(1 for term in query_terms if term in text)
            if score > 0:
                results.append(
                    {
                        "package": pkg_name,
                        "name": name,
                        "title": title,
                        "score": score,
                        "match_type": "page_title",
                    }
                )

        # Search introspected module/function names
        for member_name, info in manifest.get("modules", {}).items():
            text = f"{member_name} {info.get('description', '')}".lower()
            score = sum(1 for term in query_terms if term in text)
            if score > 0:
                results.append(
                    {
                        "package": pkg_name,
                        "name": member_name,
                        "title": info.get("description", "")[:80],
                        "score": score,
                        "match_type": "api_member",
                    }
                )

        # Search package description
        desc = manifest.get("description", "").lower()
        score = sum(1 for term in query_terms if term in desc)
        if score > 0:
            results.append(
                {
                    "package": pkg_name,
                    "name": pkg_name,
                    "title": manifest.get("description", "")[:80],
                    "score": score,
                    "match_type": "package",
                }
            )

    # Sort by score descending, then by name
    results.sort(key=lambda r: (-r["score"], r["name"]))
    return results[:max_results]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_one(
    package: str,
    format: Optional[str] = None,
    page: Optional[str] = None,
    *,
    _discover_fn=None,
    _root_fn=None,
    _sphinx_fn=None,
) -> Any:
    """Get docs for a single package, following the resolution chain."""
    discover = _discover_fn if _discover_fn is not None else discover_packages
    root_lookup = _root_fn if _root_fn is not None else get_package_root
    sphinx_lookup = _sphinx_fn if _sphinx_fn is not None else get_sphinx_source

    discovered = discover()
    module_name = discovered.get(package)

    if module_name is None:
        raise LookupError(
            f"Package '{package}' not found. Available: {list(discovered.keys())}"
        )

    # 1. Try pre-built _sphinx_html/
    pkg_root = root_lookup(module_name)
    if pkg_root is not None:
        docs_dir = pkg_root / "_sphinx_html"
        result = _resolve_from_built(docs_dir, format=format, page=page)
        if result is not None:
            return _enrich_manifest(result, package)

    # 2. Try Sphinx _build/
    sphinx_src = sphinx_lookup(module_name)
    if sphinx_src is not None:
        build_dir = sphinx_src / "_build"
        result = _resolve_from_built(
            build_dir / "html", format=format, page=page, json_dir=build_dir / "json"
        )
        if result is not None:
            return _enrich_manifest(result, package)

    # 3. Fallback: introspect
    from .._core.introspect import introspect_package

    return introspect_package(module_name)


def _resolve_from_built(
    html_dir: Path,
    format: Optional[str] = None,
    page: Optional[str] = None,
    json_dir: Optional[Path] = None,
) -> Any:
    """Try to resolve docs from a built docs directory.

    Returns None if the directory doesn't exist or doesn't have the requested content.
    """
    if not html_dir.exists():
        return None

    # If page requested but no format, default to html
    if page is not None and format is None:
        format = "html"

    # No format requested → return manifest
    if format is None:
        from .._core.manifest import read_manifest, generate_manifest

        manifest = read_manifest(html_dir)
        if manifest is not None:
            return manifest
        # Auto-generate manifest from directory contents
        return generate_manifest(
            package=html_dir.parent.name,
            docs_dir=html_dir,
        )

    # HTML format → return path
    if format == "html":
        if page is not None:
            page_path = html_dir / f"{page}.html"
            if not page_path.exists():
                page_path = html_dir / page
            if page_path.exists():
                return page_path
            return None
        if (html_dir / "index.html").exists():
            return html_dir
        return None

    # JSON format → try Sphinx JSON builder output or read HTML
    if format == "json":
        target_dir = json_dir if json_dir and json_dir.exists() else html_dir
        if page is not None:
            json_path = target_dir / f"{page}.fjson"
            if json_path.exists():
                with open(json_path, encoding="utf-8") as f:
                    return json.load(f)
            # Try .json extension
            json_path = target_dir / f"{page}.json"
            if json_path.exists():
                with open(json_path, encoding="utf-8") as f:
                    return json.load(f)
            return None
        # Return list of available pages
        pages = []
        for ext in ("*.fjson", "*.json"):
            for p in sorted(target_dir.glob(ext)):
                pages.append(p.stem)
        if pages:
            return {"pages": pages}
        # Fall back to listing HTML pages
        html_pages = [p.stem for p in sorted(html_dir.glob("*.html"))]
        if html_pages:
            return {"pages": html_pages, "note": "JSON not built, listing HTML pages"}
        return None

    raise ValueError(f"Unknown format: {format!r}. Use None, 'html', or 'json'.")


def _enrich_manifest(result: Any, package: str) -> Any:
    """Fill in version/description from importlib.metadata if missing."""
    if not isinstance(result, dict):
        return result
    if result.get("version") is not None and result.get("description") is not None:
        return result
    try:
        from importlib.metadata import metadata

        meta = metadata(package)
        if result.get("version") is None:
            result["version"] = meta.get("Version")
        if result.get("description") is None:
            summary = meta.get("Summary")
            if summary:
                result["description"] = summary
    except Exception:
        pass
    return result
