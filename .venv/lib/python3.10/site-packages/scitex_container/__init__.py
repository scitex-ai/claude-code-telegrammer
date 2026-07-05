#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/__init__.py
"""scitex-container: Unified container management for Apptainer and Docker."""

from __future__ import annotations

from . import apptainer, docker, host
from ._snapshot import env_snapshot

# ---------------------------------------------------------------------------
# Top-level re-exports — establish parity with MCP tool surface so each
# `container_*` / `sandbox_*` / `docker_*` / `host_*` tool maps to a
# top-level Python callable. See _cli/audit/_summary/_mcp_audit.py §6.
# ---------------------------------------------------------------------------
from .apptainer import (
    build,
    build_reproducible,
    check_verified,
    cleanup,
    deploy,
    list_builds,
    list_versions,
    rollback,
    sandbox_create,
    status,
    switch_version as switch,
    verify,
    verify_roundtrip,
)
from .docker import (
    rebuild as docker_rebuild,
    restart as docker_restart,
)
from .host import (
    check_packages as host_check,
    install_packages as host_install,
)

try:
    from importlib.metadata import version as _v, PackageNotFoundError

    try:
        __version__ = _v("scitex-container")
    except PackageNotFoundError:
        __version__ = "0.0.0+local"
    del _v, PackageNotFoundError
except ImportError:  # pragma: no cover — only on ancient Pythons
    __version__ = "0.0.0+local"

__all__ = [
    "__version__",
    "apptainer",
    "docker",
    "host",
    "env_snapshot",
    # MCP-parity re-exports
    "build",
    "cleanup",
    "deploy",
    "list_versions",
    "rollback",
    "sandbox_create",
    "status",
    "switch",
    "verify",
    "docker_rebuild",
    "docker_restart",
    "host_check",
    "host_install",
    # reproducible round-trip
    "build_reproducible",
    "verify_roundtrip",
    "check_verified",
    "list_builds",
]
