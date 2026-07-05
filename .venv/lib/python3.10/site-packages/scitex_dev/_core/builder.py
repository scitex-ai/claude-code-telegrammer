#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sphinx build wrapper (requires optional 'sphinx' dependency).

Builds HTML and/or JSON docs from a package's Sphinx source directory.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def build_sphinx(
    source_dir: Path,
    output_dir: Optional[Path] = None,
    builder: str = "html",
    timeout: int = 120,
) -> Optional[Path]:
    """Run sphinx-build on a source directory.

    Args:
        source_dir: Path to the Sphinx source directory (contains conf.py).
        output_dir: Where to write output. Defaults to source_dir/_build/<builder>.
        builder: Sphinx builder name ("html", "json", etc.).
        timeout: Build timeout in seconds.

    Returns:
        Path to the build output directory, or None on failure.

    Raises:
        FileNotFoundError: If source_dir or conf.py doesn't exist.
        RuntimeError: If sphinx-build fails.
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"Sphinx source directory not found: {source_dir}")
    if not (source_dir / "conf.py").exists():
        raise FileNotFoundError(f"No conf.py in {source_dir}")

    if output_dir is None:
        output_dir = source_dir / "_build" / builder

    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "sphinx",
        "-b",
        builder,
        "-q",  # quiet
        str(source_dir),
        str(output_dir),
    ]

    logger.info("Building %s docs: %s → %s", builder, source_dir, output_dir)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(source_dir.parent),
        )
    except FileNotFoundError:
        raise RuntimeError(
            "sphinx-build not found. Install with: pip install scitex-dev[sphinx]"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Sphinx build timed out after {timeout}s")

    if result.returncode != 0:
        raise RuntimeError(
            f"Sphinx build failed (exit {result.returncode}):\n{result.stderr}"
        )

    return output_dir


def build_all_formats(
    source_dir: Path,
    output_base: Optional[Path] = None,
    timeout: int = 120,
) -> dict[str, Path]:
    """Build both HTML and JSON from the same Sphinx source.

    Args:
        source_dir: Path to Sphinx source (contains conf.py).
        output_base: Base output directory. Defaults to source_dir/_build.
        timeout: Build timeout per format.

    Returns:
        Dict mapping format name → output directory path.
    """
    if output_base is None:
        output_base = source_dir / "_build"

    results = {}
    for builder in ("html", "json"):
        try:
            out = build_sphinx(
                source_dir,
                output_dir=output_base / builder,
                builder=builder,
                timeout=timeout,
            )
            if out is not None:
                results[builder] = out
        except RuntimeError as e:
            logger.warning("Failed to build %s: %s", builder, e)

    return results
