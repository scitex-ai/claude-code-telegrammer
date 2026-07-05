#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/apptainer/_sandbox.py
"""Sandbox management for Apptainer containers."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from scitex_container._compat import supports_return_as

from ._utils import detect_container_cmd

logger = logging.getLogger(__name__)


@supports_return_as
def is_sandbox(path: str | Path) -> bool:
    """Check if path is a sandbox directory (not a SIF image).

    A path ending in ``.sif`` is treated as a SIF image; anything else
    (including bare directory names or paths ending in ``-sandbox``) is
    treated as a sandbox directory.

    Parameters
    ----------
    path : str or Path
        Path to check.

    Returns
    -------
    bool
        True if path is a sandbox directory, False if it is a SIF image.
    """
    return not str(path).rstrip("/").endswith(".sif")


@supports_return_as
def create(
    source: str | Path,
    containers_dir: str | Path | None = None,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    """Build a sandbox directory from a SIF image or .def file.

    Creates a timestamped sandbox (``sandbox-YYYYMMDD_HHMMSS/``) and
    updates the ``current-sandbox`` symlink to point to it.

    Parameters
    ----------
    source : str or Path
        Path to the source ``.sif`` file or ``.def`` file.
    containers_dir : str or Path, optional
        Parent directory for sandbox output and symlink.
        Defaults to source file's parent directory.
    output_dir : str or Path, optional
        Explicit output path (overrides timestamped naming).

    Returns
    -------
    Path
        Path to the created sandbox directory.

    Raises
    ------
    FileNotFoundError
        If the source file does not exist.
    RuntimeError
        If the build fails.
    """
    from datetime import datetime

    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"Source not found: {source}")

    parent = Path(containers_dir) if containers_dir else source.parent

    if output_dir:
        sandbox_dir = Path(output_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sandbox_dir = parent / f"sandbox-{timestamp}"

    cmd = detect_container_cmd()
    logger.info("Creating sandbox %s from %s", sandbox_dir.name, source.name)

    result = subprocess.run(
        [cmd, "build", "--sandbox", "--fakeroot", str(sandbox_dir), str(source)],
        capture_output=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Sandbox creation failed with exit code {result.returncode}"
        )

    _update_sandbox_symlink(parent, sandbox_dir)
    configure_ps1(sandbox_dir)
    logger.info("Sandbox created: %s", sandbox_dir)
    return sandbox_dir


def _update_sandbox_symlink(containers_dir: Path, sandbox_dir: Path) -> None:
    """Create or update the current-sandbox symlink atomically."""
    link_path = containers_dir / "current-sandbox"
    target_name = sandbox_dir.name

    tmp_link = containers_dir / f".current-sandbox.tmp.{id(sandbox_dir)}"
    try:
        subprocess.run(
            ["ln", "-sfn", target_name, str(tmp_link)],
            check=True,
        )
        subprocess.run(
            ["mv", "-Tf", str(tmp_link), str(link_path)],
            check=True,
        )
    except subprocess.CalledProcessError:
        tmp_link.unlink(missing_ok=True)
        raise

    logger.info("Symlink updated: current-sandbox -> %s", target_name)


@supports_return_as
def configure_ps1(sandbox_dir: str | Path, default_ps1: str = r"\W $ ") -> None:
    r"""Set PS1 prompt in a sandbox's environment script.

    Writes a shell snippet that reads ``SCITEX_CLOUD_APPTAINER_PS1`` at runtime,
    falling back to *default_ps1*.  Users override by passing
    ``--env SCITEX_CLOUD_APPTAINER_PS1='(mylab) \\W $ '`` to apptainer.

    Apptainer's ``99-base.sh`` defaults to ``PS1="Apptainer> "``
    only when PS1 is unset.  Setting PS1 in ``90-environment.sh``
    (the ``%environment`` section) runs first and prevents that.

    Parameters
    ----------
    sandbox_dir : str or Path
        Path to the sandbox directory.
    default_ps1 : str
        Default PS1 when ``SCITEX_CLOUD_APPTAINER_PS1`` is not set.
    """
    import re

    sandbox_dir = Path(sandbox_dir)
    env_script = sandbox_dir / ".singularity.d" / "env" / "90-environment.sh"

    if not env_script.exists():
        logger.warning("Environment script not found: %s", env_script)
        return

    content = env_script.read_text()
    # Use shell-level variable expansion so users can override at runtime
    ps1_line = '\nexport PS1="${SCITEX_CLOUD_APPTAINER_PS1:-\\\\W \\$ }"\n'

    if "export PS1=" in content:
        content = re.sub(r"\n\s*export PS1=.*\n", ps1_line, content)
    else:
        content += ps1_line

    env_script.write_text(content)
    logger.info(
        "PS1 configured (default: %s, override: SCITEX_CLOUD_APPTAINER_PS1)",
        default_ps1,
    )


@supports_return_as
def maintain(sandbox_dir: str | Path, command: list[str]) -> int:
    """Run a command inside a sandbox with --writable --fakeroot flags.

    Intended for admin maintenance tasks (installing packages, etc.).
    For user sessions, use --writable-tmpfs instead.

    Parameters
    ----------
    sandbox_dir : str or Path
        Path to the sandbox directory.
    command : list[str]
        Command to execute inside the sandbox.

    Returns
    -------
    int
        Return code of the executed command.

    Raises
    ------
    FileNotFoundError
        If the sandbox directory does not exist or apptainer is not found.
    """
    sandbox_dir = Path(sandbox_dir)

    if not sandbox_dir.exists():
        raise FileNotFoundError(f"Sandbox directory not found: {sandbox_dir}")

    cmd = detect_container_cmd()
    logger.info("Running maintenance command in sandbox %s", sandbox_dir.name)

    result = subprocess.run(
        [cmd, "exec", "--writable", "--fakeroot", str(sandbox_dir), *command],
        capture_output=False,
    )

    if result.returncode != 0:
        logger.warning("Maintenance command exited with code %d", result.returncode)

    return result.returncode


# Package name -> directory name mapping (when they differ)
_PKG_DIR_MAP = {
    "scitex": "scitex-python",
}

_PKG_DIR_FALLBACK = {
    "scitex": "scitex-code",
}

# Default ecosystem packages to update
_DEFAULT_PACKAGES = (
    "scitex",
    "figrecipe",
    "scitex-writer",
    "scitex-dataset",
    "crossref-local",
    "openalex-local",
    "socialia",
    "scitex-linter",
    "scitex-container",
)


def _resolve_pkg_dir(pkg: str, proj_root: Path) -> Path | None:
    """Resolve a package name to its local directory path."""
    primary = _PKG_DIR_MAP.get(pkg, pkg)
    candidate = proj_root / primary
    if candidate.is_dir():
        return candidate

    fallback = _PKG_DIR_FALLBACK.get(pkg)
    if fallback:
        candidate = proj_root / fallback
        if candidate.is_dir():
            return candidate

    return None


@supports_return_as
def update(
    sandbox_dir: str | Path,
    *,
    proj_root: str | Path | None = None,
    packages: tuple[str, ...] | None = None,
    install_deps: bool = False,
) -> dict[str, str]:
    """Incrementally update ecosystem packages inside an existing sandbox.

    Runs ``pip install`` for each package from local repos, avoiding a
    full sandbox rebuild.  Ideal for active development.

    Parameters
    ----------
    sandbox_dir : str or Path
        Path to the sandbox directory (or ``current-sandbox`` symlink).
    proj_root : str or Path, optional
        Directory containing all ecosystem repos.
        Defaults to ``~/proj``.
    packages : tuple[str, ...], optional
        Package names to install. Defaults to all ecosystem packages.
    install_deps : bool
        If True, install dependencies too. If False (default), uses
        ``--no-deps`` for faster installs.

    Returns
    -------
    dict[str, str]
        Mapping of package name to result: "ok", "failed", or "skipped".
    """
    sandbox_dir = Path(sandbox_dir)
    if not sandbox_dir.exists():
        raise FileNotFoundError(f"Sandbox directory not found: {sandbox_dir}")

    if proj_root is None:
        proj_root = Path.home() / "proj"
    else:
        proj_root = Path(proj_root)

    if packages is None:
        packages = _DEFAULT_PACKAGES

    cmd = detect_container_cmd()
    pip_flags = [] if install_deps else ["--no-deps"]
    results: dict[str, str] = {}

    # Ensure bind mount destination exists inside sandbox
    # (--writable mode can't auto-create mount points)
    sandbox_real = sandbox_dir.resolve()
    mount_dest = sandbox_real / str(proj_root).lstrip("/")
    mount_dest.mkdir(parents=True, exist_ok=True)

    for pkg in packages:
        pkg_path = _resolve_pkg_dir(pkg, proj_root)
        if pkg_path is None:
            logger.warning("Package %s not found in %s, skipping", pkg, proj_root)
            results[pkg] = "skipped"
            continue

        logger.info("Installing %s from %s", pkg, pkg_path)
        result = subprocess.run(
            [
                cmd,
                "exec",
                "--writable",
                "--fakeroot",
                "--bind",
                f"{proj_root}:{proj_root}",
                str(sandbox_dir),
                "pip",
                "install",
                *pip_flags,
                str(pkg_path),
            ],
            capture_output=True,
        )

        if result.returncode == 0:
            results[pkg] = "ok"
            logger.info("Installed %s successfully", pkg)
        else:
            results[pkg] = "failed"
            stderr = result.stderr.decode(errors="replace").strip()
            logger.error(
                "Failed to install %s: %s",
                pkg,
                stderr[-200:] if stderr else "unknown error",
            )

    return results


@supports_return_as
def to_sif(sandbox_dir: str | Path, output_sif: str | Path) -> Path:
    """Convert a sandbox directory back to a SIF image.

    Parameters
    ----------
    sandbox_dir : str or Path
        Path to the source sandbox directory.
    output_sif : str or Path
        Path for the output .sif file.

    Returns
    -------
    Path
        Path to the created .sif file.

    Raises
    ------
    FileNotFoundError
        If the sandbox directory does not exist or apptainer is not found.
    RuntimeError
        If the conversion fails.
    """
    sandbox_dir = Path(sandbox_dir)
    output_sif = Path(output_sif)

    if not sandbox_dir.exists():
        raise FileNotFoundError(f"Sandbox directory not found: {sandbox_dir}")

    cmd = detect_container_cmd()
    logger.info("Converting sandbox %s to SIF %s", sandbox_dir.name, output_sif.name)

    result = subprocess.run(
        ["sudo", cmd, "build", "--force", str(output_sif), str(sandbox_dir)],
        capture_output=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Sandbox to SIF conversion failed with exit code {result.returncode}"
        )

    logger.info("SIF created: %s", output_sif)
    return output_sif


# EOF
