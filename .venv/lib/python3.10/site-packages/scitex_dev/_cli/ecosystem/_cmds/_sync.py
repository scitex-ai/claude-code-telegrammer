#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `sync` — bring every local checkout's `develop` current (ff-only).

The WRITE companion to the read-only `check-sync`. The ecosystem runs on
editable installs that import the working tree, but `origin/develop` advances on
its own (CI commits docs-HTML / version bumps back), so a checkout silently
serves stale code until someone pulls (the Spartan runner was found 145 commits
behind). This command closes that "self-pull" leg of the feedback loop.

Safety rails (so the operator's un-pushed work is NEVER clobbered):
  * develop-only   — only touches the `develop` branch; a checkout on any other
                     branch is reported `off-develop` and skipped.
  * ff-only        — `git merge --ff-only`; a diverged develop is reported and
                     skipped, never force-updated.
  * skip-dirty     — a checkout with uncommitted changes is reported `dirty` and
                     skipped (no `git pull` over local edits).
Per package it fetches `origin develop`, then ff-merges. `--dry-run` previews
without fetching or merging.
"""

from __future__ import annotations

import click

from ._sync_helpers import git, parse_package_filter, resolve_repo, selected_packages


def _is_dirty(repo) -> bool:
    """True if the checkout has uncommitted tracked changes (staged or not)."""
    return bool(git(repo, "status", "--porcelain", "--untracked-files=no"))


def _sync_one(pkg: str, info: dict, *, dry_run: bool) -> dict:
    """Bring one checkout's develop current (ff-only); never clobber local work.

    Returns a row: {package, action, behind, detail}. ``action`` ∈
    missing / off-develop / dirty / diverged / synced / pulled / would-pull.
    """
    repo = resolve_repo(pkg, info)
    if not repo.is_dir():
        return {"package": pkg, "action": "missing", "behind": 0, "detail": str(repo)}

    branch = git(repo, "branch", "--show-current")
    if branch != "develop":
        return {
            "package": pkg,
            "action": "off-develop",
            "behind": 0,
            "detail": f"on {branch or '(detached)'}",
        }

    if _is_dirty(repo):
        return {
            "package": pkg,
            "action": "dirty",
            "behind": 0,
            "detail": "uncommitted changes",
        }

    # Refresh origin/develop. In dry-run we still fetch (read-only network) so
    # the behind-count is accurate; only the merge is withheld.
    git(repo, "fetch", "origin", "develop")
    local = git(repo, "rev-parse", "refs/heads/develop")
    remote = git(repo, "rev-parse", "refs/remotes/origin/develop")
    if not remote:
        return {
            "package": pkg,
            "action": "missing",
            "behind": 0,
            "detail": "no origin/develop",
        }
    if local == remote:
        return {"package": pkg, "action": "synced", "behind": 0, "detail": ""}

    # Count how far behind, and detect divergence (local commits not on origin).
    behind = git(repo, "rev-list", "--count", f"{local}..{remote}", default="0")
    ahead = git(repo, "rev-list", "--count", f"{remote}..{local}", default="0")
    try:
        n_behind, n_ahead = int(behind), int(ahead)
    except ValueError:
        n_behind, n_ahead = 0, 0
    if n_ahead:
        return {
            "package": pkg,
            "action": "diverged",
            "behind": n_behind,
            "detail": f"{n_ahead} local commit(s) not on origin — ff-only refuses",
        }

    if dry_run:
        return {
            "package": pkg,
            "action": "would-pull",
            "behind": n_behind,
            "detail": "",
        }

    # The only mutation: a fast-forward. Cannot lose work (no merge commit, no
    # rebase); fails loudly if it somehow can't ff (treated as diverged).
    out = git(
        repo, "merge", "--ff-only", "refs/remotes/origin/develop", default="__FAIL__"
    )
    if out == "__FAIL__":
        return {
            "package": pkg,
            "action": "diverged",
            "behind": n_behind,
            "detail": "ff-only merge refused",
        }
    return {"package": pkg, "action": "pulled", "behind": n_behind, "detail": ""}


def _shell_emit(pkg: str) -> None:
    """Emit a ``pulled`` card-event for ``pkg`` via the scitex-todo CLI.

    Decoupled by SHELLING OUT (no import of scitex-todo) so a slow/absent
    consumer can't hang or break the sweep. Best-effort: if scitex-todo isn't
    on PATH or the emit fails, the sync is unaffected. ``pulled`` is default-
    quiet (the dispatcher no-ops without a card_id), so this is a recorded,
    non-notifying signal — exactly the auto-pull C8 contract.
    """
    import subprocess

    try:
        subprocess.run(
            ["scitex-todo", "emit-event", "--type", "pulled",
             "--repo", pkg, "--actor", "scitex-dev"],
            check=False,
            capture_output=True,
        )
    except OSError:
        pass  # scitex-todo not installed / not on PATH — never fail the sync


def _emit_pulled_events(rows, *, emit_fn=None) -> None:
    """Fire a ``pulled`` event for each repo that ACTUALLY fast-forwarded.

    Only ``action == "pulled"`` rows advance (a real ff-merge); ``synced`` /
    ``would-pull`` / skipped rows emit nothing, so no-op pulls stay quiet.
    ``emit_fn`` is the injection seam for tests (default = real shell-out).
    """
    emit = emit_fn or _shell_emit
    for row in rows:
        if row.get("action") == "pulled":
            emit(row["package"])


_ACTION_STYLE = {
    "pulled": ("green", "pulled"),
    "would-pull": ("cyan", "would-pull"),
    "synced": ("green", "✓ synced"),
    "off-develop": ("yellow", "off-develop"),
    "dirty": ("yellow", "dirty (skipped)"),
    "diverged": ("red", "diverged (skipped)"),
    "missing": ("red", "missing"),
}


def register(ecosystem):
    @ecosystem.command(
        "sync",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem sync                 # preview (dry-run)\n"
            "  $ scitex-dev ecosystem sync --yes           # ff-pull develop everywhere\n"
            "  $ scitex-dev ecosystem sync -p scitex-io -y # one package, execute\n"
            "  $ scitex-dev ecosystem sync --json | jq\n"
            "\n"
            "Default is a read-only preview; pass --yes/-y to actually merge. Safe by\n"
            "construction even then: develop-only, ff-only, skips dirty checkouts —\n"
            "your un-pushed work is never touched. See `check-sync` for the\n"
            "cross-host view."
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
        "--execute",
        "-y",
        "--yes",
        "execute",
        is_flag=True,
        help="Actually fast-forward (mutating). Without this, previews only: "
        "still fetches to count, but merges nothing.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Force preview even with --yes (no merge). Preview is also the "
        "default when --yes is omitted.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON rows.")
    def ecosystem_sync(package, execute, dry_run, as_json):
        """Fast-forward every local checkout's `develop` to origin (self-pull).

        For each ecosystem clone on `develop` with a clean tree, fetch and
        `merge --ff-only origin/develop`. Off-develop, dirty, or diverged
        checkouts are reported and skipped — never clobbered. Read-only preview
        by default; pass --yes/-y to perform the merges.
        """
        import json as _json

        # Preview unless explicitly executing; an explicit --dry-run always wins.
        dry_run = dry_run or not execute
        pkg_filter = parse_package_filter(package)
        items = selected_packages(pkg_filter)
        rows = [_sync_one(pkg, info, dry_run=dry_run) for pkg, info in items]

        # C8: emit a card-event for each repo that actually fast-forwarded.
        # Only on real execution (dry-run yields would-pull, never pulled).
        if not dry_run:
            _emit_pulled_events(rows)

        if as_json:
            click.echo(
                _json.dumps({"dry_run": dry_run, "rows": rows}, indent=2, default=str)
            )
            return

        _render(rows, dry_run)

    def _render(rows, dry_run):
        from rich.console import Console
        from rich.table import Table

        table = Table(show_header=True, header_style="bold")
        table.add_column("package")
        table.add_column("action")
        table.add_column("behind")
        table.add_column("detail")
        n_pulled = n_skipped = 0
        for row in rows:
            color, label = _ACTION_STYLE.get(row["action"], ("white", row["action"]))
            if row["action"] in ("pulled", "would-pull"):
                n_pulled += 1
            elif row["action"] in ("dirty", "off-develop", "diverged", "missing"):
                n_skipped += 1
            behind = str(row["behind"]) if row["behind"] else "-"
            table.add_row(
                row["package"],
                f"[{color}]{label}[/{color}]",
                behind,
                row["detail"] or "",
            )
        Console().print(table)
        verb = "would pull" if dry_run else "pulled"
        Console().print(
            f"[bold]{n_pulled}[/bold] {verb}, [bold]{n_skipped}[/bold] skipped "
            f"(dirty/off-develop/diverged/missing)."
        )
