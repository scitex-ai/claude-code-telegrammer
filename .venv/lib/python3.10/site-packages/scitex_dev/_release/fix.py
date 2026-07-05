#!/usr/bin/env python3
# Timestamp: 2026-03-27
# File: scitex_dev/fix.py

"""Detect and fix version mismatches across the ecosystem.

Single-responsibility functions:
- detect_mismatches: find packages with version inconsistencies
- fix_local: pip install -e for local mismatches
- fix_remote: git pull + pip install on remote hosts
- fix_init_version: sync __init__.py with pyproject.toml
- verify_versions: confirm all versions are aligned after fixes

The combined fix_mismatches is kept for backward compatibility.

Safety model: all mutating functions default to confirm=False (dry run).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .._core.config import DevConfig, load_config
from .._sync import sync_all, sync_local
from .versions import get_mismatches


# --- Single-responsibility functions ---


def detect_mismatches(
    packages: list[str] | None = None,
) -> dict[str, Any]:
    """Detect version mismatches. Read-only, no side effects.

    Parameters
    ----------
    packages : list[str] | None
        Package names. None = all ecosystem packages.

    Returns
    -------
    dict
        {package_name: {status, issues, local, git, remote}}
        Only packages with mismatches are included.
    """
    return get_mismatches(packages)


def fix_local(
    packages: list[str] | None = None,
    confirm: bool = False,
    config: DevConfig | None = None,
) -> dict[str, Any]:
    """Fix local mismatches only: pip install -e for each package.

    Parameters
    ----------
    packages : list[str] | None
        Package names to fix. None = auto-detect from mismatches.
    confirm : bool
        If False (default), preview only.
    config : DevConfig | None
        Configuration.

    Returns
    -------
    dict
        {package_name: {status, output|commands}}
    """
    if config is None:
        config = load_config()

    if packages is None:
        mismatches = get_mismatches()
        packages = _find_local_mismatches(mismatches)

    if not packages:
        return {}

    return sync_local(packages=packages, confirm=confirm, config=config)


def fix_remote(
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    install: bool = True,
    confirm: bool = False,
    config: DevConfig | None = None,
) -> dict[str, Any]:
    """Fix remote mismatches only: git pull + pip install on hosts.

    Parameters
    ----------
    hosts : list[str] | None
        Host names. None = all enabled hosts.
    packages : list[str] | None
        Package names. None = auto-detect from mismatches.
    install : bool
        Run pip install after git pull (default True).
    confirm : bool
        If False (default), preview only.
    config : DevConfig | None
        Configuration.

    Returns
    -------
    dict
        {host: {package: {status, output|commands}}}
    """
    if config is None:
        config = load_config()

    if packages is None:
        mismatches = get_mismatches()
        packages = list(mismatches.keys())

    if not packages:
        return {}

    return sync_all(
        hosts=hosts,
        packages=packages,
        stash=True,
        install=install,
        confirm=confirm,
        config=config,
    )


def fix_init_version(
    package_path: str | Path,
    confirm: bool = False,
) -> dict[str, Any]:
    """Sync __init__.py __version__ with pyproject.toml version.

    Parameters
    ----------
    package_path : str | Path
        Path to package root (containing pyproject.toml).
    confirm : bool
        If False, preview only.

    Returns
    -------
    dict
        {toml_version, init_version, init_path, action, status}
    """
    import re

    path = Path(package_path)
    toml_path = path / "pyproject.toml"

    if not toml_path.exists():
        return {"status": "error", "error": "pyproject.toml not found"}

    # Read toml version
    toml_text = toml_path.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', toml_text, re.MULTILINE)
    if not m:
        return {"status": "error", "error": "version not found in pyproject.toml"}
    toml_version = m.group(1)

    # Find __init__.py with __version__
    init_files = list(path.glob("src/**/__init__.py"))
    for init_path in init_files:
        init_text = init_path.read_text()
        vm = re.search(r'^__version__\s*=\s*"([^"]+)"', init_text, re.MULTILINE)
        if vm:
            init_version = vm.group(1)
            if init_version == toml_version:
                return {
                    "toml_version": toml_version,
                    "init_version": init_version,
                    "init_path": str(init_path),
                    "action": "skip",
                    "status": "ok",
                }

            if confirm:
                new_text = re.sub(
                    r'^__version__\s*=\s*"[^"]+"',
                    f'__version__ = "{toml_version}"',
                    init_text,
                    count=1,
                    flags=re.MULTILINE,
                )
                init_path.write_text(new_text)

            return {
                "toml_version": toml_version,
                "init_version": init_version,
                "init_path": str(init_path),
                "action": "updated" if confirm else "would_update",
                "status": "ok",
            }

    return {"toml_version": toml_version, "action": "no_init_version", "status": "ok"}


def verify_versions(
    packages: list[str] | None = None,
) -> dict[str, str]:
    """Verify all versions are aligned after fixes.

    Parameters
    ----------
    packages : list[str] | None
        Package names. None = all.

    Returns
    -------
    dict
        {package_name: "ok" | "mismatch: <details>"}
    """
    mismatches = get_mismatches(packages)
    from .versions import list_versions

    all_versions = list_versions(packages)
    result: dict[str, str] = {}
    for pkg, info in all_versions.items():
        if pkg in mismatches:
            issues = mismatches[pkg].get("issues", [])
            result[pkg] = f"mismatch: {'; '.join(issues)}"
        else:
            result[pkg] = "ok"
    return result


def bump_version(
    package_path: str | Path,
    new_version: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Bump version in pyproject.toml and __init__.py.

    Parameters
    ----------
    package_path : str | Path
        Path to package root (containing pyproject.toml).
    new_version : str
        New version string (e.g. "0.5.0").
    confirm : bool
        If False, preview only.

    Returns
    -------
    dict
        {old_version, new_version, toml_updated, init_updated, status}
    """
    import re

    path = Path(package_path)
    toml_path = path / "pyproject.toml"

    if not toml_path.exists():
        return {"status": "error", "error": "pyproject.toml not found"}

    toml_text = toml_path.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', toml_text, re.MULTILINE)
    if not m:
        return {"status": "error", "error": "version not found in pyproject.toml"}

    old_version = m.group(1)
    if old_version == new_version:
        return {
            "old_version": old_version,
            "new_version": new_version,
            "action": "skip",
            "status": "ok",
        }

    result: dict[str, Any] = {
        "old_version": old_version,
        "new_version": new_version,
        "toml_updated": False,
        "init_updated": False,
        "status": "ok",
    }

    if confirm:
        new_toml = re.sub(
            r'^version\s*=\s*"[^"]+"',
            f'version = "{new_version}"',
            toml_text,
            count=1,
            flags=re.MULTILINE,
        )
        toml_path.write_text(new_toml)
        result["toml_updated"] = True

        # Also update __init__.py
        init_result = fix_init_version(package_path, confirm=True)
        result["init_updated"] = init_result.get("action") == "updated"
    else:
        result["action"] = "would_bump"

    return result


def determine_bump_type(
    package_path: str | Path,
) -> dict[str, Any]:
    """Check diff since last tag and classify as minor/patch/skip.

    Parameters
    ----------
    package_path : str | Path
        Path to package root (git repo).

    Returns
    -------
    dict
        {has_diff, commits_since_tag, has_feat, bump_type, current_version, suggested_version}
    """
    import re
    import subprocess

    path = Path(package_path)

    # Get current version
    toml_path = path / "pyproject.toml"
    current_version = None
    if toml_path.exists():
        m = re.search(
            r'^version\s*=\s*"([^"]+)"',
            toml_path.read_text(),
            re.MULTILINE,
        )
        if m:
            current_version = m.group(1)

    # Get last tag
    try:
        tag_result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0", "--match", "v*"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if tag_result.returncode != 0:
            return {
                "has_diff": True,
                "commits_since_tag": None,
                "bump_type": "patch",
                "current_version": current_version,
                "error": "no tags found",
            }
        last_tag = tag_result.stdout.strip()
    except Exception as e:
        return {"status": "error", "error": str(e)}

    # Check diff
    diff_result = subprocess.run(
        ["git", "diff", f"{last_tag}..HEAD", "--stat"],
        cwd=path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    has_diff = bool(diff_result.stdout.strip())

    if not has_diff:
        return {
            "has_diff": False,
            "commits_since_tag": 0,
            "bump_type": "skip",
            "current_version": current_version,
            "last_tag": last_tag,
        }

    # Count commits and check for feat:
    log_result = subprocess.run(
        ["git", "log", f"{last_tag}..HEAD", "--oneline"],
        cwd=path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    commits = log_result.stdout.strip().splitlines()
    has_feat = any("feat:" in line or "feat(" in line for line in commits)
    bump_type = "minor" if has_feat else "patch"

    # Suggest version
    suggested = None
    if current_version:
        parts = current_version.split(".")
        if len(parts) == 3:
            major, minor, patch = (
                int(parts[0]),
                int(parts[1]),
                int(parts[2].split("-")[0]),
            )
            if bump_type == "minor":
                suggested = f"{major}.{minor + 1}.0"
            else:
                suggested = f"{major}.{minor}.{patch + 1}"

    return {
        "has_diff": True,
        "commits_since_tag": len(commits),
        "has_feat": has_feat,
        "bump_type": bump_type,
        "current_version": current_version,
        "suggested_version": suggested,
        "last_tag": last_tag,
    }


# --- Combined (backward compat) ---


def fix_mismatches(
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    local: bool = True,
    remote: bool = True,
    confirm: bool = False,
    config: DevConfig | None = None,
) -> dict[str, Any]:
    """Detect version mismatches and fix them.

    Combines detect + fix_local + fix_remote. Kept for backward compatibility.
    Prefer using the individual functions for clarity.

    Safety: defaults to preview only. Pass confirm=True to execute.
    """
    if config is None:
        config = load_config()

    mismatches = get_mismatches(packages)
    mismatch_names = list(mismatches.keys()) if not packages else packages

    result: dict[str, Any] = {
        "detected": {
            pkg: {"status": info.get("status"), "issues": info.get("issues", [])}
            for pkg, info in mismatches.items()
        },
        "local_fixes": {},
        "remote_fixes": {},
        "summary": {"detected": len(mismatches), "local_fixed": 0, "remote_fixed": 0},
    }

    if not mismatch_names:
        return result

    if local:
        result["local_fixes"] = fix_local(
            packages=_find_local_mismatches(mismatches),
            confirm=confirm,
            config=config,
        )
        if confirm:
            result["summary"]["local_fixed"] = sum(
                1 for r in result["local_fixes"].values() if r.get("status") == "ok"
            )

    if remote:
        result["remote_fixes"] = fix_remote(
            hosts=hosts,
            packages=mismatch_names,
            confirm=confirm,
            config=config,
        )
        if confirm:
            for host_results in result["remote_fixes"].values():
                if isinstance(host_results, dict):
                    result["summary"]["remote_fixed"] += sum(
                        1
                        for r in host_results.values()
                        if isinstance(r, dict) and r.get("status") == "ok"
                    )

    return result


def _find_local_mismatches(mismatches: dict[str, Any]) -> list[str]:
    """Extract package names where local installed != toml version."""
    to_fix = []
    for pkg, info in mismatches.items():
        lv = info.get("local", {})
        toml = lv.get("pyproject_toml")
        installed = lv.get("installed")
        if toml and installed and toml != installed:
            to_fix.append(pkg)
        elif toml and not installed:
            to_fix.append(pkg)
    return to_fix


# EOF
