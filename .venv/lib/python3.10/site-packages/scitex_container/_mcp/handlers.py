#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/_mcp/handlers.py
"""Async MCP handlers wrapping the scitex-container Python API."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Apptainer handlers
# ---------------------------------------------------------------------------


async def build_handler(
    name: str = "scitex-final",
    sandbox: bool = False,
    force: bool = False,
    base: bool = False,
) -> dict:
    """Build a SIF or sandbox from a .def file."""
    from ..apptainer import build

    try:
        output_path = build(def_name=name, force=force, sandbox=sandbox)
        return {"success": True, "path": str(output_path)}
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}


async def list_handler(containers_dir: str | None = None) -> dict:
    """List all versioned SIFs with metadata."""
    from pathlib import Path

    from ..apptainer import find_containers_dir, get_active_version, list_versions

    try:
        cdir = Path(containers_dir) if containers_dir else find_containers_dir()
        versions = list_versions(cdir)
        active = get_active_version(cdir)
        return {
            "success": True,
            "containers_dir": str(cdir),
            "active": active,
            "versions": versions,
        }
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}


async def switch_handler(
    version: str,
    containers_dir: str | None = None,
    use_sudo: bool = False,
) -> dict:
    """Switch active container to the specified version."""
    from pathlib import Path

    from ..apptainer import find_containers_dir, get_active_version, switch_version

    try:
        cdir = Path(containers_dir) if containers_dir else find_containers_dir()
        old_version = get_active_version(cdir)
        switch_version(version, cdir, use_sudo=use_sudo)
        return {
            "success": True,
            "previous_version": old_version,
            "active_version": version,
        }
    except (FileNotFoundError, RuntimeError) as exc:
        return {"success": False, "error": str(exc)}


async def rollback_handler(
    containers_dir: str | None = None,
    use_sudo: bool = False,
) -> dict:
    """Roll back to the previous container version."""
    from pathlib import Path

    from ..apptainer import find_containers_dir, get_active_version
    from ..apptainer import rollback as do_rollback

    try:
        cdir = Path(containers_dir) if containers_dir else find_containers_dir()
        old_version = get_active_version(cdir)
        new_version = do_rollback(cdir, use_sudo=use_sudo)
        return {
            "success": True,
            "previous_version": old_version,
            "active_version": new_version,
        }
    except (FileNotFoundError, RuntimeError) as exc:
        return {"success": False, "error": str(exc)}


async def deploy_handler(
    target_dir: str = "/opt/scitex/singularity",
    containers_dir: str | None = None,
) -> dict:
    """Copy active SIF to production target directory."""
    from pathlib import Path

    from ..apptainer import find_containers_dir, get_active_version
    from ..apptainer import deploy as do_deploy

    try:
        cdir = Path(containers_dir) if containers_dir else find_containers_dir()
        active = get_active_version(cdir)
        do_deploy(source_dir=cdir, target_dir=Path(target_dir))
        return {"success": True, "version": active, "target": target_dir}
    except (FileNotFoundError, RuntimeError) as exc:
        return {"success": False, "error": str(exc)}


async def cleanup_handler(
    keep: int = 3,
    containers_dir: str | None = None,
) -> dict:
    """Remove old container versions, keeping the N most recent."""
    from pathlib import Path

    from ..apptainer import find_containers_dir
    from ..apptainer import cleanup as do_cleanup

    try:
        cdir = Path(containers_dir) if containers_dir else find_containers_dir()
        removed = do_cleanup(cdir, keep=keep)
        return {
            "success": True,
            "removed_count": len(removed),
            "removed": [str(p) for p in removed],
        }
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Status handler
# ---------------------------------------------------------------------------


async def status_handler() -> dict:
    """Combined status of containers, host packages, and Docker."""
    result: dict = {}

    # Apptainer
    try:
        from ..apptainer import find_containers_dir, get_active_version, list_versions

        cdir = find_containers_dir()
        result["apptainer"] = {
            "containers_dir": str(cdir),
            "active": get_active_version(cdir),
            "versions": list_versions(cdir),
        }
    except Exception as exc:
        result["apptainer"] = {"error": str(exc)}

    # Host packages
    try:
        from ..host import check_packages

        result["host"] = check_packages()
    except Exception as exc:
        result["host"] = {"error": str(exc)}

    # Docker (dev + prod)
    docker_status: dict = {}
    for env in ("dev", "prod"):
        try:
            from ..docker import status as docker_status_fn

            docker_status[env] = docker_status_fn(env=env)
        except Exception as exc:
            docker_status[env] = {"error": str(exc)}
    result["docker"] = docker_status

    return result


# ---------------------------------------------------------------------------
# Host handlers
# ---------------------------------------------------------------------------


async def host_install_handler(
    texlive: bool = False,
    imagemagick: bool = False,
    all: bool = True,  # noqa: A002
) -> dict:
    """Install host packages via the install script."""
    from ..host import install_packages

    try:
        result = install_packages(texlive=texlive, imagemagick=imagemagick, all=all)
        return {"success": True, "result": result}
    except (FileNotFoundError, RuntimeError) as exc:
        return {"success": False, "error": str(exc)}


async def host_check_handler() -> dict:
    """Check which host packages are installed."""
    from ..host import check_packages

    try:
        packages = check_packages()
        return {"success": True, "packages": packages}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Sandbox handlers
# ---------------------------------------------------------------------------


async def sandbox_create_handler(
    source_sif: str | None = None,
    output_dir: str | None = None,
    force: bool = False,
) -> dict:
    """Convert a SIF image to a writable sandbox directory."""
    from pathlib import Path

    from ..apptainer import sandbox_create

    if not source_sif:
        return {"success": False, "error": "source_sif is required"}

    sif_path = Path(source_sif)
    out_path = (
        Path(output_dir)
        if output_dir
        else sif_path.parent / (sif_path.stem + "-sandbox")
    )

    if out_path.exists() and not force:
        return {
            "success": False,
            "error": f"Sandbox already exists: {out_path}. Set force=True to overwrite.",
        }

    try:
        result = sandbox_create(source=sif_path, output_dir=out_path)
        return {"success": True, "sandbox_dir": str(result)}
    except (FileNotFoundError, RuntimeError) as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Verify handler
# ---------------------------------------------------------------------------


async def verify_handler(
    sif_path: str = "",
    def_path: str = "",
    lock_dir: str = "",
) -> dict:
    """Verify container integrity: SHA256 hash, .def origin, lock file comparison."""
    from ..apptainer import find_containers_dir, get_active_version
    from ..apptainer import verify as do_verify

    if not sif_path:
        try:
            cdir = find_containers_dir()
            active = get_active_version(cdir)
            if active:
                sif_path = str(cdir / f"scitex-v{active}.sif")
            else:
                return {"success": False, "error": "No active SIF found"}
        except FileNotFoundError as exc:
            return {"success": False, "error": str(exc)}

    try:
        result = do_verify(
            sif_path=sif_path,
            def_path=def_path or None,
            lock_dir=lock_dir or None,
        )
        return {"success": True, "verification": result}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Docker handlers
# ---------------------------------------------------------------------------


async def docker_rebuild_handler(env: str = "dev") -> dict:
    """Rebuild Docker containers for the given environment."""
    from ..docker import rebuild

    try:
        rc = rebuild(env=env)
        return {"success": rc == 0, "returncode": rc, "env": env}
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}


async def docker_restart_handler(env: str = "dev") -> dict:
    """Restart Docker containers for the given environment."""
    from ..docker import restart

    try:
        rc = restart(env=env)
        return {"success": rc == 0, "returncode": rc, "env": env}
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Snapshot handler (Clew integration)
# ---------------------------------------------------------------------------


async def env_snapshot_handler(
    containers_dir: str = "",
    dev_repos: list[str] | None = None,
) -> dict:
    """Capture environment snapshot for Clew integration."""
    from .._snapshot import env_snapshot

    try:
        snap = env_snapshot(
            containers_dir=containers_dir or None,
            dev_repos=dev_repos,
        )
        return {"success": True, "snapshot": snap}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# EOF
