#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/host/_mounts.py
"""Mount configuration for host packages bound into containers."""

from __future__ import annotations

import shutil
from pathlib import Path

from scitex_container._compat import supports_return_as

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEXLIVE_BINARIES: list[str] = [
    "pdflatex",
    "bibtex",
    "latexmk",
    "latexdiff",
    "kpsewhich",
    "makeindex",
    "biber",
]

TEXLIVE_DIRS: list[str] = [
    "share/texlive",
    "share/texmf-dist",
]

_IMAGEMAGICK_DIRS: list[str] = [
    "etc/ImageMagick-6",
]

_IMAGEMAGICK_BINARIES: list[str] = [
    "convert",
    "identify",
    "mogrify",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _bin_dir_for_prefix(prefix: str) -> str:
    """Return the bin directory for a given prefix (e.g. /usr → /usr/bin)."""
    return str(Path(prefix) / "bin")


def _resolve_binary(name: str, prefix: str) -> str | None:
    """Return absolute path to a binary under prefix/bin, or via PATH lookup."""
    candidate = Path(prefix) / "bin" / name
    if candidate.exists():
        return str(candidate)
    found = shutil.which(name)
    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@supports_return_as
def get_texlive_binds(prefix: str = "/usr") -> list[dict]:
    """Generate bind mount entries for TeXLive.

    Parameters
    ----------
    prefix : str
        Installation prefix (typically ``/usr`` for system-wide apt installs).

    Returns
    -------
    list[dict]
        Each entry has keys ``host``, ``container``, and ``mode``::

            [
                {"host": "/usr/share/texlive", "container": "/usr/share/texlive", "mode": "ro"},
                {"host": "/usr/bin/pdflatex",  "container": "/usr/bin/pdflatex",  "mode": "ro"},
                ...
            ]
    """
    mounts: list[dict] = []

    # Directory mounts (share/texlive, share/texmf-dist, ...)
    for rel_dir in TEXLIVE_DIRS:
        host_path = Path(prefix) / rel_dir
        if host_path.exists():
            container_path = Path("/") / rel_dir  # mirror path in container
            mounts.append(
                {
                    "host": str(host_path),
                    "container": str(container_path),
                    "mode": "ro",
                }
            )

    # Binary mounts
    bin_dir = Path(prefix) / "bin"
    container_bin = Path("/usr/bin")
    for binary in TEXLIVE_BINARIES:
        host_bin = bin_dir / binary
        if host_bin.exists():
            mounts.append(
                {
                    "host": str(host_bin),
                    "container": str(container_bin / binary),
                    "mode": "ro",
                }
            )

    return mounts


@supports_return_as
def get_mount_config(
    texlive_prefix: str = "",
    host_mounts_raw: str = "",
) -> dict:
    """Parse mount configuration and return structured bind mount info.

    Parameters
    ----------
    texlive_prefix : str
        Installation prefix for TeXLive (e.g. ``/usr``).  When empty,
        defaults to ``/usr`` if TeXLive binaries are found there, otherwise
        skips TeXLive mounts.
    host_mounts_raw : str
        Colon-separated raw bind specs in ``host:container`` or
        ``host:container:mode`` format, separated by commas or newlines.
        Example: ``"/data:/data:ro,/scratch:/scratch"``

    Returns
    -------
    dict
        Structured mount information::

            {
                "bind_args": ["--bind", "/usr/share/texlive:/usr/share/texlive:ro", ...],
                "path_additions": ["/usr/bin"],
                "mounts": [{"host": "...", "container": "...", "mode": "ro"}, ...],
            }
    """
    mounts: list[dict] = []
    path_additions: list[str] = []

    # --- TeXLive mounts ---
    prefix = texlive_prefix or "/usr"
    texlive_mounts = get_texlive_binds(prefix=prefix)
    if texlive_mounts:
        mounts.extend(texlive_mounts)
        bin_dir = str(Path(prefix) / "bin")
        if bin_dir not in path_additions:
            path_additions.append(bin_dir)

    # --- Raw extra mounts ---
    if host_mounts_raw:
        # Accept comma or newline as separator
        raw_entries = [
            e.strip()
            for e in host_mounts_raw.replace("\n", ",").split(",")
            if e.strip()
        ]
        for entry in raw_entries:
            parts = entry.split(":")
            if len(parts) == 2:  # noqa: PLR2004
                host_path, container_path = parts
                mode = "rw"
            elif len(parts) == 3:  # noqa: PLR2004
                host_path, container_path, mode = parts
            else:
                # Malformed — skip
                continue
            mounts.append(
                {
                    "host": host_path,
                    "container": container_path,
                    "mode": mode,
                }
            )

    # --- Build --bind args ---
    bind_args: list[str] = []
    for mount in mounts:
        spec = f"{mount['host']}:{mount['container']}:{mount['mode']}"
        bind_args.extend(["--bind", spec])

    return {
        "bind_args": bind_args,
        "path_additions": path_additions,
        "mounts": mounts,
    }


# EOF
