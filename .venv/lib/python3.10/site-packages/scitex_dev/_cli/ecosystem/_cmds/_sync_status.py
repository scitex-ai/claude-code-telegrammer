#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `check-sync` — per-package develop-sha sync across hosts.

Read-only by default. For each ecosystem clone it reports the current
branch, the local `develop` sha, the `origin/develop` sha, and (with
`--host H`, repeatable) the SAME data gathered on host H over ssh —
then diffs local-vs-remote `develop` and classifies the drift.

The user develops on Spartan now, so the local clones routinely drift
behind. `check-sync -h spartan` shows, at a glance, which packages are
behind / ahead / diverged without fetching or mutating anything.
"""

from __future__ import annotations

import click

from ._sync_helpers import (
    git,
    parse_package_filter,
    resolve_repo,
    run_remote_json,
    selected_packages,
)


def _local_row(pkg: str, info: dict, *, fetch: bool) -> dict:
    """Gather branch + develop shas for one package's local checkout."""
    repo = resolve_repo(pkg, info)
    if not repo.is_dir():
        return {
            "package": pkg,
            "exists": False,
            "branch": "",
            "develop": "",
            "origin_develop": "",
        }
    if fetch:
        # Networked refresh of origin/develop only. Off by default.
        git(repo, "fetch", "origin", "develop")
    return {
        "package": pkg,
        "exists": True,
        "branch": git(repo, "branch", "--show-current"),
        "develop": git(repo, "rev-parse", "refs/heads/develop"),
        "origin_develop": git(repo, "rev-parse", "refs/remotes/origin/develop"),
    }


def _classify(repo, local_sha: str, remote_sha: str) -> str:
    """Classify a local-vs-remote develop sha relationship.

    Uses `git rev-list --count` when BOTH commits are present in the
    local object store (so ahead/behind can be measured); otherwise
    falls back to the coarse "differs".
    """
    if not local_sha and not remote_sha:
        return "missing"
    if not local_sha or not remote_sha:
        return "differs"
    if local_sha == remote_sha:
        return "synced"
    if repo is None or not repo.is_dir():
        return "differs"

    behind = git(repo, "rev-list", "--count", f"{local_sha}..{remote_sha}")
    ahead = git(repo, "rev-list", "--count", f"{remote_sha}..{local_sha}")
    try:
        n_behind = int(behind)
        n_ahead = int(ahead)
    except ValueError:
        return "differs"
    if n_ahead and n_behind:
        return "diverged"
    if n_behind:
        return "behind"
    if n_ahead:
        return "ahead"
    return "differs"


_STATUS_STYLE = {
    "synced": ("green", "✓"),
    "behind": ("yellow", "behind"),
    "ahead": ("yellow", "ahead"),
    "differs": ("yellow", "differs"),
    "diverged": ("red", "diverged"),
    "off-develop": ("yellow", "off-develop"),
    "missing": ("red", "missing"),
}


def register(ecosystem):
    @ecosystem.command(
        "check-sync",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem check-sync                       # local only\n"
            "  $ scitex-dev ecosystem check-sync -h spartan            # diff vs spartan\n"
            "  $ scitex-dev ecosystem check-sync -h spartan --json | jq\n"
            "  $ scitex-dev ecosystem check-sync -p scitex-io -h spartan\n"
            "  $ scitex-dev ecosystem check-sync -h spartan --fetch    # refresh origin first\n"
            "\n"
            "Read-only: never fetches/pulls/mutates unless --fetch is\n"
            "passed (which only runs `git fetch origin develop` per repo)."
        ),
    )
    @click.option(
        "--host",
        "-h",
        "hosts",
        multiple=True,
        help="Remote host(s) to diff against (repeatable). Requires "
        "scitex-dev installed on the remote.",
    )
    @click.option(
        "--package",
        "-p",
        multiple=True,
        help="Limit to specific packages (comma-separated or repeat the flag; "
        "'all' = every package).",
    )
    @click.option(
        "--fetch",
        is_flag=True,
        help="Run `git fetch origin develop` per repo before comparing "
        "(networked/slow; OFF by default).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON rows.")
    def ecosystem_sync_status(hosts, package, fetch, as_json):
        """Per-package develop-sha sync between local and remote host(s).

        Captures each ecosystem clone's branch + local/origin develop
        sha; with --host also gathers the same over ssh and classifies
        the drift (synced / behind / ahead / diverged).
        """
        import json as _json

        pkg_filter = parse_package_filter(package)
        items = selected_packages(pkg_filter)
        host_list = list(hosts)

        # Local rows, keyed by package.
        local_rows = {pkg: _local_row(pkg, info, fetch=fetch) for pkg, info in items}

        # Remote rows: one ssh round-trip per host emitting our own JSON.
        # We pass the SAME -p filter and --fetch so the remote gathers an
        # identical per-package shape, then deserialise rows[].
        remote_by_host: dict[str, dict[str, dict]] = {}
        for host in host_list:
            remote_argv = ["ecosystem", "check-sync", "--json"]
            if fetch:
                remote_argv.append("--fetch")
            for p in package:
                remote_argv.extend(["-p", p])
            rc, out, err = run_remote_json(host, remote_argv)
            parsed: dict[str, dict] = {}
            if rc == 0:
                try:
                    payload = _json.loads(out)
                except _json.JSONDecodeError:
                    payload = {}
                for row in payload.get("rows", []):
                    parsed[row.get("package", "")] = row
            else:
                click.echo(
                    f"warning: remote check-sync on {host} exited {rc}: "
                    f"{err.strip()[:300]}",
                    err=True,
                )
            remote_by_host[host] = parsed

        # Build the unified row set.
        rows: list[dict] = []
        for pkg, info in items:
            lr = local_rows[pkg]
            repo = resolve_repo(pkg, info)
            row: dict = {
                "package": pkg,
                "branch": lr["branch"],
                "exists": lr["exists"],
                "local_develop": lr["develop"],
                "origin_develop": lr["origin_develop"],
                "hosts": {},
            }
            if not lr["exists"]:
                row["status"] = "missing"
            elif lr["branch"] and lr["branch"] != "develop":
                row["status"] = "off-develop"
            else:
                row["status"] = "synced" if lr["develop"] else "missing"

            for host in host_list:
                rr = remote_by_host[host].get(pkg, {})
                remote_dev = rr.get("local_develop", "")
                status = _classify(
                    repo if lr["exists"] else None, lr["develop"], remote_dev
                )
                row["hosts"][host] = {
                    "develop": remote_dev,
                    "branch": rr.get("branch", ""),
                    "status": status,
                }
            rows.append(row)

        payload = {"hosts": host_list, "rows": rows}

        if as_json:
            click.echo(_json.dumps(payload, indent=2, default=str))
            return

        _render_table(rows, host_list)

    def _render_table(rows, host_list):
        from rich.console import Console
        from rich.table import Table

        table = Table(show_header=True, header_style="bold")
        table.add_column("package")
        table.add_column("branch")
        table.add_column("local develop")
        for host in host_list:
            table.add_column(f"{host} develop")
        table.add_column("status")

        for row in rows:
            local_dev = (row["local_develop"] or "")[:10] or "-"
            # When hosts are given, the overall status is the worst host
            # status; otherwise it's the local-only status.
            if host_list:
                statuses = [row["hosts"][h]["status"] for h in host_list]
                overall = _worst_status(statuses, row["status"])
            else:
                overall = row["status"]
            color, label = _STATUS_STYLE.get(overall, ("white", overall))

            cells = [row["package"], row["branch"] or "-", local_dev]
            for host in host_list:
                hd = (row["hosts"][host]["develop"] or "")[:10] or "-"
                cells.append(hd)
            cells.append(f"[{color}]{label}[/{color}]")
            table.add_row(*cells)

        Console().print(table)

    def _worst_status(host_statuses, local_status):
        # Severity ladder: diverged/missing (red) > drift (yellow) > synced.
        order = ["diverged", "missing", "off-develop", "behind", "ahead", "differs"]
        if local_status in ("missing", "off-develop"):
            return local_status
        for s in order:
            if s in host_statuses:
                return s
        return "synced"
