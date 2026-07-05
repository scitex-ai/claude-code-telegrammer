#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex-dev: Shared developer utilities for the SciTeX ecosystem.

Zero-dependency package providing:
- Docs aggregation and serving across all scitex packages
- Unified search across APIs, CLI, MCP tools, and documentation
- Version management and ecosystem registry
- Bulk rename with cross-reference updates
- LLM-friendly types (Result, ErrorCode, @supports_return_as)

Public API (20 functions)::

    # Docs
    get_docs, build_docs, search_docs

    # Search
    search

    # Versions
    list_versions, check_versions, get_mismatches, fix_mismatches

    # LLM-friendly types
    Result, ErrorCode, supports_return_as, SideEffect,
    classify_exception, handle_result, run_as_cli, run_as_mcp,
    result_to_mcp, wrap_as_mcp
"""

from __future__ import annotations

try:
    from importlib.metadata import version as _v, PackageNotFoundError

    try:
        __version__ = _v("scitex-dev")
    except PackageNotFoundError:
        __version__ = "0.0.0+local"
    del _v, PackageNotFoundError
except ImportError:  # pragma: no cover — only on ancient Pythons
    __version__ = "0.0.0+local"
# PEP 562 lazy public API.
#
# Every public name is loaded on first attribute access — `import scitex_dev`
# costs ~50ms (down from 8.4s) because nothing transitively pulls in the
# `scitex` umbrella, `figrecipe`, `scitex_scholar`, etc. until you actually
# touch a function that needs them. This makes CLI tab-completion, --help,
# and quick scripts an order of magnitude faster.
#
# To add a new public name: extend `_LAZY_ATTRS`. Don't add `from .X import Y`
# at module top — that re-introduces eager loading and slows every CLI call.
# See `_skills/general/03_interface/01_python-api/04_lazy-imports-and-optional-deps.md`.
_LAZY_ATTRS: dict[str, str] = {
    # cli_utils
    "add_dry_run_argument": "_cli",
    "add_json_argument": "_cli",
    "dry_run_option": "_cli",
    "handle_result": "_cli",
    "json_option": "_cli",
    "run_as_cli": "_cli",
    "wrap_as_cli": "_cli",
    # decorators
    "supports_return_as": "_core.decorators",
    # errors
    "ErrorCode": "_core.errors",
    "ScitexError": "_core.errors",
    "classify_exception": "_core.errors",
    # _imports
    "InstallHint": "_core.imports",
    "last_install_hint": "_core.imports",
    "try_import_optional": "_core.imports",
    # ecosystem MCP helpers (re-exported via scitex_dev.ecosystem)
    "get_tools_sync": "_ecosystem._mcp",
    "async_wrap_as_mcp": "_ecosystem._mcp",
    "result_to_mcp": "_ecosystem._mcp",
    "run_as_mcp": "_ecosystem._mcp",
    "wrap_as_mcp": "_ecosystem._mcp",
    # side_effects
    "SideEffect": "_core.side_effects",
    # types
    "RESULT_SCHEMA": "_core.types",
    "Result": "_core.types",
    # docs
    "build_docs": "_docs.docs",
    "get_docs": "_docs.docs",
    "search_docs": "_docs.docs",
    # search
    "search": "_docs.search",
    # versions
    "check_versions": "_release.versions",
    "get_ecosystem_versions": "_release.versions",
    "get_mismatches": "_release.versions",
    "list_versions": "_release.versions",
    # fix
    "bump_version": "_release.fix",
    "detect_mismatches": "_release.fix",
    "determine_bump_type": "_release.fix",
    "fix_init_version": "_release.fix",
    "fix_local": "_release.fix",
    "fix_mismatches": "_release.fix",
    "fix_remote": "_release.fix",
    "verify_versions": "_release.fix",
    # config
    "DevConfig": "_core.config",
    "GitHubRemote": "_core.config",
    "HostConfig": "_core.config",
    "PackageConfig": "_core.config",
    "PyPIAccount": "_core.config",
    "config_to_dict": "_core.config",
    "create_default_config": "_core.config",
    "get_config_path": "_core.config",
    "get_enabled_hosts": "_core.config",
    "get_enabled_remotes": "_core.config",
    "load_config": "_core.config",
    # ecosystem
    "ECOSYSTEM": "_ecosystem",
    "get_all_packages": "_ecosystem",
    "get_local_path": "_ecosystem",
    # rtd
    "check_all_rtd": "_release.rtd",
    "check_rtd_status": "_release.rtd",
    # _pypi_package_data
    "PackageDataAuditReport": "_release.pypi_package_data",
    "audit_package_data": "_release.pypi_package_data",
    # github
    "check_all_remotes": "_release.github",
    "compare_with_local": "_release.github",
    "get_github_latest_tag": "_release.github",
    "get_github_release": "_release.github",
    "get_github_tags": "_release.github",
    # runtime — supervised async periodic-task primitive
    "PeriodicTask": "runtime",
    "PeriodicTaskGroup": "runtime",
    # rename
    "RenameConfig": "rename",
    "RenameResult": "rename",
    "bulk_rename": "rename",
    "execute_rename": "rename",
    "preview_rename": "rename",
    # ssh
    "check_all_hosts": "ssh",
    "get_remote_version": "ssh",
    "get_remote_versions": "ssh",
    "test_host_connection": "ssh",
    # sync
    "sync_all": "_sync",
    "sync_host": "_sync",
    "sync_local": "_sync",
    "sync_tags": "_sync",
    # sync_remote
    "pull_local": "_sync",
    "remote_commit": "_sync",
    "remote_diff": "_sync",
    # ci
    "CIStatus": "_release.ci",
    "WorkflowRun": "_release.ci",
    "check_ci": "_release.ci",
    "check_pypi_publish": "_release.ci",
    "create_github_release": "_release.ci",
    "get_failing_packages": "_release.ci",
    "verify_all_pypi_configs": "_release.ci",
    "verify_pypi_config": "_release.ci",
    "wait_all_pypi": "_release.ci",
    "wait_for_workflow": "_release.ci",
    # deploy
    "deploy_scitex_hub": "_release.deploy",
    "verify_production": "_release.deploy",
    # skills
    "verify_docs_and_skills": "_docs.skills",
    # test_runner
    "TestConfig": "test_runner",
    "fetch_hpc_result": "test_runner",
    "poll_hpc_job": "test_runner",
    "run_hpc_sbatch": "test_runner",
    "run_hpc_srun": "test_runner",
    "run_local": "test_runner",
    "sync_to_hpc": "test_runner",
    "watch_hpc_job": "test_runner",
}


# Editable-install drift warning — fires once per process when the working
# tree is ahead of/behind the latest tag. Cheap (~1ms cache hit; skipped
# entirely on non-editable installs). Suppress with SCITEX_DEV_NO_DRIFT_WARN=1.
try:
    from ._release.check_editable_drift import emit_if_drift as _emit_drift

    _emit_drift("scitex-dev")
except Exception:
    pass


def __getattr__(name: str):
    """PEP 562 lazy-loader: import on first access, cache, then return."""
    mod_name = _LAZY_ATTRS.get(name)
    if mod_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    attr = getattr(import_module(f".{mod_name}", __name__), name)
    globals()[name] = (
        attr  # cache in module globals; subsequent access skips this branch
    )
    return attr


def __dir__() -> list[str]:
    return sorted(set(_LAZY_ATTRS) | set(globals()))


__all__ = [
    # Version
    "__version__",
    # Docs
    "get_docs",
    "build_docs",
    "search_docs",
    # Search
    "search",
    # Versions
    "list_versions",
    "check_versions",
    "get_mismatches",
    "fix_mismatches",
    "get_ecosystem_versions",
    # LLM-friendly types
    "Result",
    "RESULT_SCHEMA",
    "ErrorCode",
    "ScitexError",
    "classify_exception",
    "try_import_optional",
    "last_install_hint",
    "InstallHint",
    "supports_return_as",
    "SideEffect",
    "handle_result",
    "run_as_cli",
    "wrap_as_cli",
    "run_as_mcp",
    "wrap_as_mcp",
    "async_wrap_as_mcp",
    "result_to_mcp",
    # CLI option factories
    "json_option",
    "dry_run_option",
    "add_json_argument",
    "add_dry_run_argument",
    # Sync
    "sync_all",
    "sync_host",
    "sync_local",
    "sync_tags",
    "remote_diff",
    "remote_commit",
    "pull_local",
    # Async runtime primitives
    "PeriodicTask",
    "PeriodicTaskGroup",
]
