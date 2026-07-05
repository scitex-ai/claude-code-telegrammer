#!/usr/bin/env python3
# Timestamp: 2026-04-27
# File: scitex_dev/ecosystem_packages.py

"""Unified observation/dry-run/apply auditing for ecosystem packages.

Backs ``scitex-dev ecosystem packages``. Three modes:

  - **observation** (default): read-only audit. For each (host, pkg)
    cell render the remote SHA, mark mismatches with ``*``, ``MISSING``
    when absent, ``???`` when the host can't be reached. Adds an
    ``origin/develop`` and ``localhost`` column for reference. Exits 0
    iff every reachable cell matches origin/develop.
  - **dry-run**: print the exact shell commands that would run on each
    host for each out-of-sync (host, pkg) pair.
  - **apply**: actually run them via ``sync.sync_all``.

This module purposely uses the *audit* logic to also emit the package
table — the same SHA fetch is reused for observation and for the
"who's out-of-sync" filter that feeds dry-run / apply.
"""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .._core.config import DevConfig, HostConfig, get_enabled_hosts, load_config
from .._sync import _build_ssh_args, _build_sync_commands, _get_host_packages, sync_all


def _short(sha: str | None) -> str:
    if not sha:
        return ""
    return sha[:7]


def _origin_sha(local_path: Path, branch: str = "develop") -> str | None:
    """Read origin/<branch> SHA from a local clone via ``git ls-remote``."""
    if not local_path.exists():
        return None
    try:
        r = subprocess.run(
            ["git", "ls-remote", "origin", f"refs/heads/{branch}"],
            cwd=str(local_path),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode != 0:
            return None
        line = r.stdout.strip().split("\n")[0]
        return line.split()[0] if line else None
    except Exception:
        return None


def _local_sha(local_path: Path) -> str | None:
    if not local_path.exists():
        return None
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(local_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _remote_sha(host: HostConfig, dir_name: str) -> str | None:
    """SSH to host and read HEAD SHA for a single package directory.

    Returns None for missing dir or any error. Caller distinguishes
    "missing" (None) vs "unreachable" via the host-reachability cache.
    """
    base = f"{host.remote_base}/{dir_name}"
    cmd = (
        f"cd {base} 2>/dev/null || {{ echo SACDEV_MISSING; exit 0; }}; "
        "if [ ! -d .git ]; then echo SACDEV_MISSING; exit 0; fi; "
        "git rev-parse HEAD 2>/dev/null || echo SACDEV_ERROR"
    )
    args = _build_ssh_args(host) + [cmd]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=30)
        out = r.stdout.strip()
        if r.returncode != 0 or not out or "SACDEV_MISSING" in out:
            return None
        if "SACDEV_ERROR" in out:
            return None
        return out.split()[-1]
    except Exception:
        return None


def collect_state(
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    config: DevConfig | None = None,
    *,
    origin_sha_fn=None,
    local_sha_fn=None,
    remote_sha_fn=None,
) -> dict[str, Any]:
    """Gather origin/develop, localhost, and per-host SHAs.

    Returns
    -------
    dict
        ``{"hosts": [host_name, ...], "rows": [{pkg, origin, localhost,
        cells: {host: sha_or_None}}, ...]}``.
    """
    if config is None:
        config = load_config()

    origin_fn = origin_sha_fn if origin_sha_fn is not None else _origin_sha
    local_fn = local_sha_fn if local_sha_fn is not None else _local_sha
    remote_fn = remote_sha_fn if remote_sha_fn is not None else _remote_sha

    enabled = get_enabled_hosts(config)
    if hosts:
        enabled = [h for h in enabled if h.name in hosts]

    pkg_filter = set(packages) if packages else None
    pkgs = [
        p
        for p in config.packages
        if p.local_path and (pkg_filter is None or p.name in pkg_filter)
    ]

    rows = []
    for pkg in pkgs:
        path = Path(pkg.local_path).expanduser()
        rows.append(
            {
                "pkg": pkg.name,
                "dir": path.name,
                "origin": origin_fn(path),
                "localhost": local_fn(path),
                "cells": {},
            }
        )

    # Parallel remote SHA collection: (host, pkg) tuples
    pairs: list[tuple[HostConfig, dict[str, Any]]] = []
    for host in enabled:
        host_pkg_dirs = dict(_get_host_packages(host, config))
        for row in rows:
            if row["pkg"] in host_pkg_dirs:
                pairs.append((host, row))
            else:
                row["cells"][host.name] = "EXCLUDED"

    if pairs:
        with ThreadPoolExecutor(max_workers=min(16, len(pairs))) as ex:
            fut_map = {ex.submit(remote_fn, h, r["dir"]): (h.name, r) for h, r in pairs}
            for fut in as_completed(fut_map):
                host_name, row = fut_map[fut]
                try:
                    row["cells"][host_name] = fut.result()
                except Exception:
                    row["cells"][host_name] = "ERROR"

    return {"hosts": [h.name for h in enabled], "rows": rows}


def _cell_repr(sha: Any, origin: str | None) -> str:
    if sha == "EXCLUDED":
        return "-"
    if sha == "ERROR" or sha is None:
        return "MISSING"
    if not isinstance(sha, str):
        return "???"
    if origin and sha == origin:
        return _short(sha)
    return _short(sha) + "*"


def render_table(state: dict[str, Any]) -> str:
    """Render observation table as a markdown-ish fixed-width table."""
    hosts = state["hosts"]
    headers = ["pkg", "origin/develop", "localhost"] + hosts
    rows = state["rows"]
    body = []
    for r in rows:
        origin = r["origin"]
        line = [
            r["pkg"],
            _short(origin) if origin else "???",
            _cell_repr(r["localhost"], origin),
        ]
        for h in hosts:
            line.append(_cell_repr(r["cells"].get(h), origin))
        body.append(line)

    # Column widths
    cols = [headers] + body
    widths = [max(len(str(row[i])) for row in cols) for i in range(len(headers))]

    def fmt(row: list[str]) -> str:
        return "  ".join(str(v).ljust(widths[i]) for i, v in enumerate(row))

    out = [fmt(headers), fmt(["-" * w for w in widths])]
    out.extend(fmt(r) for r in body)
    return "\n".join(out)


def out_of_sync_pairs(state: dict[str, Any]) -> list[tuple[str, str]]:
    """Return list of (host, pkg) needing sync (cell != origin)."""
    pairs = []
    for r in state["rows"]:
        origin = r["origin"]
        if not origin:
            continue
        for host, sha in r["cells"].items():
            if sha == "EXCLUDED":
                continue
            if sha != origin:
                pairs.append((host, r["pkg"]))
    return pairs


def summarize(state: dict[str, Any]) -> dict[str, Any]:
    """Return summary stats."""
    total = 0
    matching = 0
    needing = []
    for r in state["rows"]:
        origin = r["origin"]
        if not origin:
            continue
        for host, sha in r["cells"].items():
            if sha == "EXCLUDED":
                continue
            total += 1
            if sha == origin:
                matching += 1
            else:
                needing.append({"host": host, "pkg": r["pkg"]})
    return {"total": total, "matching": matching, "needing_sync": needing}


def dry_run_commands(
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    config: DevConfig | None = None,
    only_out_of_sync: bool = True,
    *,
    origin_sha_fn=None,
    local_sha_fn=None,
    remote_sha_fn=None,
) -> dict[str, Any]:
    """Build the exact shell commands per (host, pkg) without executing.

    When ``only_out_of_sync`` (default), restricts to mismatched cells
    determined by an observation pass.
    """
    if config is None:
        config = load_config()

    state = collect_state(
        hosts=hosts,
        packages=packages,
        config=config,
        origin_sha_fn=origin_sha_fn,
        local_sha_fn=local_sha_fn,
        remote_sha_fn=remote_sha_fn,
    )
    enabled_map = {h.name: h for h in get_enabled_hosts(config)}

    target_pairs: set[tuple[str, str]] = set()
    if only_out_of_sync:
        target_pairs = set(out_of_sync_pairs(state))
    else:
        for r in state["rows"]:
            for h in state["hosts"]:
                if r["cells"].get(h) != "EXCLUDED":
                    target_pairs.add((h, r["pkg"]))

    out: dict[str, Any] = {}
    for host_name, pkg_name in sorted(target_pairs):
        host = enabled_map.get(host_name)
        if host is None:
            continue
        host_pkg_dirs = dict(_get_host_packages(host, config))
        dir_name = host_pkg_dirs.get(pkg_name)
        if not dir_name:
            continue
        cmds = _build_sync_commands(host, dir_name, stash=True, install=True)
        out.setdefault(host_name, {})[pkg_name] = cmds
    return out


def packages_audit(
    mode: str = "observe",
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    unsafe: bool = False,
    config: DevConfig | None = None,
    *,
    origin_sha_fn=None,
    local_sha_fn=None,
    remote_sha_fn=None,
) -> dict[str, Any]:
    """Top-level entry consumed by the CLI.

    Modes: ``"observe"``, ``"dry-run"``, ``"apply"``.
    """
    if config is None:
        config = load_config()

    sha_kwargs = dict(
        origin_sha_fn=origin_sha_fn,
        local_sha_fn=local_sha_fn,
        remote_sha_fn=remote_sha_fn,
    )

    if mode == "observe":
        state = collect_state(
            hosts=hosts, packages=packages, config=config, **sha_kwargs
        )
        return {
            "mode": "observe",
            "table": render_table(state),
            "state": state,
            "summary": summarize(state),
        }

    if mode == "dry-run":
        return {
            "mode": "dry-run",
            "commands": dry_run_commands(
                hosts=hosts, packages=packages, config=config, **sha_kwargs
            ),
        }

    if mode == "apply":
        # Restrict to out-of-sync pairs to avoid wasted work.
        state = collect_state(
            hosts=hosts, packages=packages, config=config, **sha_kwargs
        )
        oos = out_of_sync_pairs(state)
        if not oos:
            return {"mode": "apply", "results": {}, "note": "already in sync"}
        # Group: hosts with at least one mismatch, sync only those pkgs.
        by_host: dict[str, list[str]] = {}
        for h, p in oos:
            by_host.setdefault(h, []).append(p)
        results: dict[str, Any] = {}
        for host_name, pkg_list in by_host.items():
            results[host_name] = sync_all(
                hosts=[host_name],
                packages=pkg_list,
                stash=True,
                install=True,
                safe=not unsafe,
                confirm=True,
                config=config,
            ).get(host_name, {})
        return {"mode": "apply", "results": results}

    raise ValueError(f"unknown mode: {mode!r}")


# EOF
