#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manifest schema for pre-built docs.

Each package can ship a _sphinx_html/manifest.json describing its documentation:
    {
        "package": "scitex-writer",
        "version": "0.3.0",
        "pages": [
            {"name": "index", "title": "Home", "path": "index.html"},
            {"name": "api",   "title": "API Reference", "path": "api.html"},
            ...
        ],
        "formats": ["html", "json"],
        "built_at": "2026-03-13T04:00:00Z"
    }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def read_manifest(docs_dir: Path) -> Optional[dict[str, Any]]:
    """Read manifest.json from a _sphinx_html/ directory.

    Args:
        docs_dir: Path to the _sphinx_html/ directory.

    Returns:
        Parsed manifest dict, or None if not found/invalid.
    """
    manifest_path = docs_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read manifest at %s: %s", manifest_path, e)
        return None


def write_manifest(docs_dir: Path, manifest: dict[str, Any]) -> Path:
    """Write manifest.json to a docs directory.

    Args:
        docs_dir: Target directory.
        manifest: Manifest data to write.

    Returns:
        Path to the written manifest file.
    """
    docs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = docs_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return manifest_path


def generate_manifest(
    package: str,
    docs_dir: Path,
    version: Optional[str] = None,
) -> dict[str, Any]:
    """Generate a manifest by scanning a built docs directory.

    Discovers HTML and JSON pages by walking the directory.

    Args:
        package: Package name (e.g. "scitex-writer").
        docs_dir: Path to the built docs directory.
        version: Optional package version string.

    Returns:
        Manifest dict ready to write.
    """
    from datetime import datetime, timezone

    pages = []
    formats = set()

    if docs_dir.exists():
        for html_file in sorted(docs_dir.rglob("*.html")):
            rel = html_file.relative_to(docs_dir)
            name = rel.stem if rel.parent == Path(".") else str(rel.with_suffix(""))
            pages.append(
                {
                    "name": name,
                    "title": _title_from_name(name),
                    "path": str(rel),
                }
            )
            formats.add("html")

        if (docs_dir / "objects.inv").exists():
            formats.add("json")  # Sphinx JSON builder likely available

    return {
        "package": package,
        "version": version,
        "pages": pages,
        "formats": sorted(formats),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


def _title_from_name(name: str) -> str:
    """Convert a page name to a human-readable title."""
    return name.replace("_", " ").replace("-", " ").title()
