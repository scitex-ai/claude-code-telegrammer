#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `prune-merged` — list/delete branches merged into develop.

Routine hygiene: topic branches that have already landed on `develop`
accumulate in every clone (scitex-dev had 11 stale, scitex-agent-
container 27). This enumerates them per package and, with `--apply`,
safe-deletes them (`git branch -d`, never `-D`).

HARD safety rails:
  * dry-run is the DEFAULT; --apply is required to mutate.
  * develop / main / master and the currently-checked-out branch are
    never touched.
  * `git branch -d` (merged-only safe delete) — never force.
  * --remote only deletes branches merged into origin/develop and never
    one with an open PR (checked via `gh pr list --head`).
"""

from __future__ import annotations

import click

from ._sync_helpers import (
    PROTECTED_BRANCHES,
    git,
    parse_package_filter,
    resolve_repo,
    run_remote_json,
    selected_packages,
)


def _merged_local_branches(repo) -> list[str]:
    """Local branches merged into refs/heads/develop, minus protected.

    Excludes develop/main/master and the currently-checked-out branch.
    Branches checked out in a linked worktree are left in (git refuses
    `-d` on them; we surface that as a 'skipped' at delete time).
    """
    out = git(
        repo,
        "for-each-ref",
        "--merged",
        "refs/heads/develop",
        "--format=%(refname:short)",
        "refs/heads/",
    )
    if not out:
        return []
    current = git(repo, "branch", "--show-current")
    branches = []
    for line in out.splitlines():
        name = line.strip()
        if not name or name in PROTECTED_BRANCHES or name == current:
            continue
        branches.append(name)
    return branches


def _merged_remote_branches(repo) -> list[str]:
    """Remote branches merged into origin/develop, minus protected.

    Returns short names (e.g. `feature/x`), stripping the `origin/`
    prefix. Excludes origin/HEAD and origin/{develop,main,master}.
    """
    out = git(
        repo,
        "for-each-ref",
        "--merged",
        "refs/remotes/origin/develop",
        "--format=%(refname:short)",
        "refs/remotes/origin/",
    )
    if not out:
        return []
    branches = []
    for line in out.splitlines():
        name = line.strip()
        if not name.startswith("origin/"):
            continue
        short = name[len("origin/") :]
        if short in PROTECTED_BRANCHES or short == "HEAD":
            continue
        branches.append(short)
    return branches


def _has_open_pr(repo, branch: str) -> bool:
    """True if an open GitHub PR targets `branch` as its head.

    Uses `gh pr list --head <branch> --state open`. On any gh failure
    we conservatively return True (skip the delete) so a network hiccup
    never lets us delete a branch with a live PR.
    """
    import json as _json
    import subprocess

    try:
        proc = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "open",
                "--json",
                "number",
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return True
    if proc.returncode != 0:
        return True
    try:
        data = _json.loads(proc.stdout or "[]")
    except _json.JSONDecodeError:
        return True
    return bool(data)


def _delete_local(repo, branch: str) -> tuple[bool, str]:
    """`git branch -d <branch>` (safe). Returns (deleted, reason)."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "branch", "-d", branch],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, "deleted"
    # git refuses -d on a worktree-checked-out branch or an unmerged one.
    return False, (proc.stderr or proc.stdout or "git branch -d failed").strip()


def _delete_remote(repo, branch: str) -> tuple[bool, str]:
    """`git push origin --delete <branch>`. Returns (deleted, reason)."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "push", "origin", "--delete", branch],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, "deleted"
    return False, (proc.stderr or proc.stdout or "git push --delete failed").strip()


def _prune_one(pkg: str, info: dict, *, apply: bool, remote: bool) -> dict:
    """Compute (and optionally apply) the prune plan for one package."""
    repo = resolve_repo(pkg, info)
    if not repo.is_dir():
        return {"package": pkg, "exists": False, "local": [], "remote": []}

    result: dict = {"package": pkg, "exists": True, "local": [], "remote": []}

    for branch in _merged_local_branches(repo):
        entry = {"branch": branch, "action": "would-delete", "reason": ""}
        if apply:
            ok, reason = _delete_local(repo, branch)
            entry["action"] = "deleted" if ok else "skipped"
            entry["reason"] = reason
        result["local"].append(entry)

    if remote:
        for branch in _merged_remote_branches(repo):
            entry = {"branch": branch, "action": "would-delete", "reason": ""}
            if _has_open_pr(repo, branch):
                entry["action"] = "skipped"
                entry["reason"] = "open PR"
            elif apply:
                ok, reason = _delete_remote(repo, branch)
                entry["action"] = "deleted" if ok else "skipped"
                entry["reason"] = reason
            result["remote"].append(entry)

    return result


def register(ecosystem):
    @ecosystem.command(
        "prune-merged",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem prune-merged                     # dry-run, all pkgs\n"
            "  $ scitex-dev ecosystem prune-merged -p scitex-dev       # dry-run, one pkg\n"
            "  $ scitex-dev ecosystem prune-merged --apply             # delete local merged\n"
            "  $ scitex-dev ecosystem prune-merged --remote            # also list remote\n"
            "  $ scitex-dev ecosystem prune-merged --apply --remote    # delete both\n"
            "  $ scitex-dev ecosystem prune-merged -h spartan --apply  # prune on spartan\n"
            "\n"
            "Safety: dry-run is the DEFAULT; --apply required to mutate.\n"
            "develop/main/master + the checked-out branch are NEVER\n"
            "touched; only `git branch -d` (merged-safe) is used; a\n"
            "remote branch with an open PR is always skipped."
        ),
    )
    @click.option(
        "--package",
        "-p",
        multiple=True,
        help="Limit to specific packages (comma-separated or repeat the flag; "
        "'all' = every package).",
    )
    @click.option(
        "--apply",
        "do_apply",
        is_flag=True,
        help="Actually delete (default is dry-run). Uses safe `git branch -d`.",
    )
    @click.option(
        "--remote",
        "do_remote",
        is_flag=True,
        help="Also list/delete branches merged into origin/develop (skips "
        "any with an open PR).",
    )
    @click.option(
        "--host",
        "-h",
        "host",
        default=None,
        help="Run the prune on a remote host over ssh (dry-run there too "
        "unless --apply).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    def ecosystem_prune_merged(package, do_apply, do_remote, host, as_json):
        """List (and with --apply delete) branches merged into develop.

        Default = dry-run: prints what WOULD be deleted, grouped by
        package, with a total. --apply safe-deletes (never -D). --remote
        extends to origin-merged branches (open-PR branches skipped).
        """
        import json as _json

        # --host: delegate the whole prune to the remote scitex-dev and
        # forward its JSON. The remote applies the same dry-run/apply
        # semantics (we pass --apply/--remote/-p straight through).
        if host:
            remote_argv = ["ecosystem", "prune-merged", "--json"]
            if do_apply:
                remote_argv.append("--apply")
            if do_remote:
                remote_argv.append("--remote")
            for p in package:
                remote_argv.extend(["-p", p])
            rc, out, err = run_remote_json(host, remote_argv)
            if rc != 0:
                raise click.ClickException(
                    f"remote prune-merged on {host} exited {rc}: {err.strip()[:500]}"
                )
            if as_json:
                click.echo(out.strip())
            else:
                try:
                    payload = _json.loads(out)
                except _json.JSONDecodeError:
                    click.echo(out)
                    return
                _render(payload, do_apply, do_remote, host=host)
            return

        pkg_filter = parse_package_filter(package)
        items = selected_packages(pkg_filter)

        results = [
            _prune_one(pkg, info, apply=do_apply, remote=do_remote)
            for pkg, info in items
        ]
        payload = {"apply": do_apply, "remote": do_remote, "results": results}

        if as_json:
            click.echo(_json.dumps(payload, indent=2, default=str))
            return

        _render(payload, do_apply, do_remote, host=None)

    def _render(payload, do_apply, do_remote, *, host):
        results = payload.get("results", [])
        total_local = 0
        total_remote = 0
        loc = f" on {host}" if host else ""
        verb = "Deleted" if do_apply else "Would delete"

        for res in results:
            pkg = res.get("package", "?")
            if not res.get("exists", True):
                continue
            local = res.get("local", [])
            remote = res.get("remote", []) if do_remote else []
            if not local and not remote:
                continue
            click.echo(f"{pkg}:")
            for entry in local:
                total_local += (
                    1 if entry["action"] in ("would-delete", "deleted") else 0
                )
                _echo_entry(entry, scope="local")
            for entry in remote:
                total_remote += (
                    1 if entry["action"] in ("would-delete", "deleted") else 0
                )
                _echo_entry(entry, scope="remote")

        parts = [f"{total_local} local"]
        if do_remote:
            parts.append(f"{total_remote} remote")
        click.echo("")
        click.echo(
            f"{verb}{loc}: {', '.join(parts)} merged branch(es) across "
            f"{len(results)} package(s).",
            err=True,
        )
        if not do_apply:
            click.echo("Re-run with --apply to delete.", err=True)

    def _echo_entry(entry, *, scope):
        action = entry["action"]
        reason = entry.get("reason") or ""
        mark = {"deleted": "✓", "would-delete": "·", "skipped": "✗"}.get(action, "?")
        tag = "remote " if scope == "remote" else ""
        suffix = f"  ({reason})" if reason and action != "deleted" else ""
        click.echo(f"  {mark} {tag}{entry['branch']}{suffix}")
