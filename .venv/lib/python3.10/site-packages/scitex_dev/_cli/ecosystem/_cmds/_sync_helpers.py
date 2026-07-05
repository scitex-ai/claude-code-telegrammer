#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for the `sync-status` / `prune-merged` ecosystem commands.

Local git introspection (read-only by default) plus the
`ssh host bash -lc '<scitex-dev ... --json>'` round-trip pattern reused
from `_dashboard._render_remote_dashboard`. Both commands speak the same
per-package data shape so a remote payload deserialises identically to a
local one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_PROJ_ROOT = Path("~/proj").expanduser()

# Branches that must NEVER be deleted/touched by prune-merged, on either
# the local clone or the remote (origin/<name>).
PROTECTED_BRANCHES = frozenset({"develop", "main", "master"})


def shquote(s: str) -> str:
    """POSIX shell single-quote for embedding in `bash -lc '...'`."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def git(repo: Path, *args: str, default: str = "") -> str:
    """Run `git -C <repo> <args>`; return stripped stdout or `default`."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), *args],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        return out.strip()
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return default


def ecosystem_packages() -> dict:
    """Read the ECOSYSTEM registry; tolerant of older scitex-dev versions."""
    try:
        from scitex_dev._ecosystem._core import ECOSYSTEM
    except Exception:
        # Broad on purpose: a misconfigured optional dep can raise more
        # than ImportError on import; an empty registry degrades to a
        # no-op (no packages to act on) rather than crashing the CLI.
        return {}
    return dict(ECOSYSTEM)


def resolve_repo(pkg: str, info: dict) -> Path:
    """Local checkout path for a package, expanding `~`."""
    raw = info.get("local_path", "")
    return Path(raw).expanduser() if raw else DEFAULT_PROJ_ROOT / pkg


def parse_package_filter(raw_entries) -> list[str] | None:
    """Parse `-p` values (repeat + comma-split + literal `all`).

    Mirrors the dashboard's argument style:
      -p scitex-io -p scitex-stats  -> ["scitex-io", "scitex-stats"]
      -p scitex-io,scitex-stats     -> ["scitex-io", "scitex-stats"]
      -p all                        -> None (every package)
      (nothing)                     -> None (every package)
    """
    raw: list[str] = []
    for entry in raw_entries:
        raw.extend(p.strip() for p in entry.split(",") if p.strip())
    if "all" in raw or not raw:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for p in raw:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def selected_packages(package_filter: list[str] | None) -> list[tuple[str, dict]]:
    """ECOSYSTEM items honoring a (possibly None = all) package filter."""
    eco = ecosystem_packages()
    if package_filter is not None:
        eco = {k: v for k, v in eco.items() if k in package_filter}
    return list(eco.items())


def run_remote_json(host: str, remote_argv: list[str]) -> tuple[int, str, str]:
    """Run `scitex-dev <remote_argv> --json` on `host` over ssh.

    Returns (returncode, stdout, stderr). The remote command is sourced
    through `bash -lc` so the user's PATH (incl. ~/.env-*/bin) is set up,
    and `-o BatchMode=yes` prevents an interactive password prompt from
    hanging the call. Mirrors `_dashboard._render_remote_dashboard`.
    """
    remote_cmd = " ".join(["scitex-dev", *remote_argv])
    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        host,
        f"bash -lc {shquote(remote_cmd)}",
    ]
    try:
        proc = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError as exc:
        return 127, "", f"ssh not found: {exc}"
    except subprocess.TimeoutExpired:
        return 124, "", f"ssh to {host} timed out"
    return proc.returncode, proc.stdout, proc.stderr
