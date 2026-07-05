#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/host/_packages.py
"""Host package installation and verification."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from scitex_container._compat import supports_return_as

# ---------------------------------------------------------------------------
# Package root resolution
# ---------------------------------------------------------------------------

_PKG_ROOT = Path(__file__).resolve().parents[4]  # scitex-container root
_INSTALL_SCRIPT = _PKG_ROOT / "scripts" / "install-host-packages.sh"

# ---------------------------------------------------------------------------
# Binary → package group mapping
# ---------------------------------------------------------------------------

_TEXLIVE_BINARIES = [
    "pdflatex",
    "bibtex",
    "latexmk",
    "latexdiff",
    "kpsewhich",
    "makeindex",
    "biber",
]
_TEXLIVE_EXTRA_BINARIES = ["gs", "pdfinfo"]  # ghostscript, poppler-utils

_IMAGEMAGICK_BINARIES = ["convert", "identify", "mogrify"]


def _find_version(cmd: str) -> str:
    """Return first line of --version output, or empty string on failure."""
    try:
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (result.stdout or result.stderr or "").strip()
        return output.splitlines()[0] if output else ""
    except Exception:
        return ""


@supports_return_as
def check_packages() -> dict:
    """Check which host packages are installed.

    Returns
    -------
    dict
        Structured status per package group::

            {
                "texlive": {
                    "installed": True,
                    "version": "pdfTeX 3.141592653...",
                    "binaries": ["pdflatex", "bibtex", ...],
                },
                "imagemagick": {
                    "installed": True,
                    "version": "Version: ImageMagick 6.9...",
                    "binaries": ["convert", "identify"],
                },
            }
    """
    result: dict = {}

    # TeXLive
    all_tex_bins = _TEXLIVE_BINARIES + _TEXLIVE_EXTRA_BINARIES
    found_tex = [b for b in all_tex_bins if shutil.which(b)]
    tex_version = _find_version("pdflatex") if shutil.which("pdflatex") else ""
    result["texlive"] = {
        "installed": bool(found_tex),
        "version": tex_version,
        "binaries": found_tex,
    }

    # ImageMagick
    found_im = [b for b in _IMAGEMAGICK_BINARIES if shutil.which(b)]
    im_version = _find_version("convert") if shutil.which("convert") else ""
    result["imagemagick"] = {
        "installed": bool(found_im),
        "version": im_version,
        "binaries": found_im,
    }

    return result


@supports_return_as
def install_packages(
    texlive: bool = False,
    imagemagick: bool = False,
    all: bool = False,  # noqa: A002
    check_only: bool = False,
) -> dict:
    """Install host packages by calling the shell script.

    Parameters
    ----------
    texlive : bool
        Install TeXLive packages.
    imagemagick : bool
        Install ImageMagick.
    all : bool
        Install all packages (overrides texlive/imagemagick flags).
    check_only : bool
        Run the script in --check mode without installing anything.

    Returns
    -------
    dict
        Status per package group::

            {
                "texlive": {"status": "installed", "returncode": 0},
                "imagemagick": {"status": "skipped", "returncode": None},
                "script": "/abs/path/to/install-host-packages.sh",
            }

    Raises
    ------
    FileNotFoundError
        If the install script cannot be found.
    """
    if not _INSTALL_SCRIPT.exists():
        raise FileNotFoundError(
            f"Install script not found: {_INSTALL_SCRIPT}\n"
            "Expected at: scitex-container/scripts/install-host-packages.sh"
        )

    result: dict = {"script": str(_INSTALL_SCRIPT)}

    if check_only:
        proc = subprocess.run(
            ["bash", str(_INSTALL_SCRIPT), "--check"],
            capture_output=False,
            text=True,
        )
        result["check"] = {"returncode": proc.returncode}
        return result

    # Build flags
    flags: list[str] = []
    if all:
        flags = ["--all"]
    else:
        if texlive:
            flags.append("--texlive")
        if imagemagick:
            flags.append("--imagemagick")

    # Default: install everything when no flag given
    if not flags:
        flags = ["--all"]

    cmd = ["sudo", "bash", str(_INSTALL_SCRIPT)] + flags
    proc = subprocess.run(cmd, capture_output=False, text=True)

    if "--texlive" in flags or "--all" in flags:
        result["texlive"] = {
            "status": "installed" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
        }
    else:
        result["texlive"] = {"status": "skipped", "returncode": None}

    if "--imagemagick" in flags or "--all" in flags:
        result["imagemagick"] = {
            "status": "installed" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
        }
    else:
        result["imagemagick"] = {"status": "skipped", "returncode": None}

    return result


# EOF
