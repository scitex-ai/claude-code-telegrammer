"""``scitex-dev hooks`` — install / update / list / path the canonical agent hooks.

The 2026-06-12 ripple-wm dogfood pinned the fanned-out-copy class:
~10 deployed copies of ``run_lint.sh`` across operator projects each
drift independently. Pillar 0 (#169) shipped the canonical hook
inside scitex-dev at ``scitex_dev/_hooks/run_lint.sh`` so the
authoritative source travels with the pip-installed package. This
CLI is the **durable kill** for the fan-out class: install the
canonical hook into a target project as a SYMLINK so future scitex-
dev releases automatically propagate without operator action.

Subcommands
-----------
``scitex-dev hooks install --target <project>``
    Create the standard hook tree at ``<project>/docs/to_claude/
    hooks/post-tool-use/`` and symlink the bundled ``run_lint.sh``
    into it. With ``--force`` overwrites an existing target; without
    ``--force`` refuses if a non-symlink file is already present.

``scitex-dev hooks update --target <project>``
    Re-link the project's ``run_lint.sh`` to the currently-installed
    scitex-dev's bundled script. Equivalent to ``install --force`` for
    a project that already has the directory tree.

``scitex-dev hooks list --target <project>``
    Report what's installed: each known hook + whether it points to
    the bundled canonical (✓), an out-of-date copy (≠), a stale dead
    symlink (✗), or is missing (-).

``scitex-dev hooks path <name>``
    Print the absolute filesystem path of the bundled hook ``<name>``
    (today: ``run_lint`` is the only recognised name). Useful for
    shell scripts: ``ln -s "$(scitex-dev hooks path run_lint)"
    docs/to_claude/hooks/post-tool-use/run_lint.sh``.

Hooks the CLI knows about
-------------------------
``run_lint`` → bundled at ``scitex_dev._hooks.run_lint_sh_path()``.
    The PostToolUse SciTeX-pattern-check hook from Pillar 0. Future
    canonical hooks register themselves by adding an entry to
    :data:`KNOWN_HOOKS`.
``run_testmon`` → bundled at ``scitex_dev._hooks.run_testmon_sh_path()``.
    The pre-commit pytest-testmon warm-cache wrapper that seed-copies a
    persistent per-(repo, pyXY) ``.testmondata`` in/out of each fresh
    worktree so testmon runs only impacted tests instead of the full suite.
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from .. import _hooks


# Map: canonical name → (source path, deploy-relative path).
# A SYMLINK is created at <project>/<deploy_rel> pointing at the source.
# When a future canonical hook lands, add it here.
KNOWN_HOOKS: dict[str, tuple[str, str]] = {
    "run_lint": (
        _hooks.run_lint_sh_path(),
        "docs/to_claude/hooks/post-tool-use/run_lint.sh",
    ),
    "run_testmon": (
        _hooks.run_testmon_sh_path(),
        "docs/to_claude/hooks/pre-commit/run_testmon.sh",
    ),
}


def _is_symlink_to(symlink: Path, target_abs: str) -> bool:
    """True if ``symlink`` is a symlink resolving to ``target_abs``."""
    if not symlink.is_symlink():
        return False
    try:
        return os.path.realpath(str(symlink)) == os.path.realpath(target_abs)
    except OSError:
        return False


def _install_one(
    name: str,
    source: str,
    deploy_rel: str,
    project: Path,
    force: bool,
) -> str:
    """Install one canonical hook into ``project``. Returns a status word.

    Status words (printed by the CLI in coloured form):
    ``installed``  — created a fresh symlink
    ``updated``    — re-pointed an existing symlink to the current source
    ``up-to-date`` — symlink already points at the canonical (no-op)
    ``refused``    — non-symlink file present, ``--force`` not given
    ``forced``     — overwrote a non-symlink file under ``--force``
    """
    target = project / deploy_rel
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() or target.is_symlink():
        if _is_symlink_to(target, source):
            return "up-to-date"
        if target.is_symlink():
            # Stale or out-of-date symlink — always safe to replace.
            target.unlink()
            target.symlink_to(source)
            return "updated"
        # Real file (not a symlink).
        if not force:
            return "refused"
        target.unlink()
        target.symlink_to(source)
        return "forced"

    target.symlink_to(source)
    return "installed"


def _list_one(name: str, source: str, deploy_rel: str, project: Path) -> str:
    """Report the install status of one hook in ``project`` as a status word.

    ``ok``       — points at the canonical
    ``drift``    — file present but NOT the canonical (real file or
                   symlink to elsewhere)
    ``stale``    — symlink present but broken / source missing
    ``missing``  — not installed
    """
    target = project / deploy_rel
    if not target.exists() and not target.is_symlink():
        return "missing"
    if target.is_symlink():
        if not target.exists():
            return "stale"
        if _is_symlink_to(target, source):
            return "ok"
        return "drift"
    return "drift"


def register_hooks_commands(main) -> None:
    """Attach the ``hooks`` subgroup to the top-level ``scitex-dev`` click group.

    Called from ``scitex_dev._cli._root`` alongside the other
    ``register_*_commands(main)`` registrations.
    """

    @main.group("hooks", short_help="Manage agent-feedback hook scripts.")
    def hooks_group():  # pragma: no cover - click group body is empty by design
        """Manage scitex-dev's bundled PostToolUse agent-feedback hooks.

        Pillar 0 follow-up (#169) — replaces the per-project fanned-out
        run_lint.sh copies with a symlink to the canonical version
        shipped inside the pip-installed scitex-dev package. Future
        scitex-dev releases auto-propagate without operator action.
        """

    @hooks_group.command("install", short_help="Install canonical hooks into a project.")
    @click.option(
        "--target",
        "target",
        required=True,
        type=click.Path(file_okay=False, dir_okay=True, exists=False, resolve_path=True),
        help="Project root to install hooks into (created if missing).",
    )
    @click.option(
        "--name",
        "names",
        multiple=True,
        type=click.Choice(sorted(KNOWN_HOOKS), case_sensitive=False),
        help=(
            "Limit installation to specific hook names. Defaults to all "
            "known hooks (today: just `run_lint`)."
        ),
    )
    @click.option(
        "--force",
        is_flag=True,
        help=(
            "Overwrite an existing non-symlink file at the deploy path. "
            "By default a real file blocks installation so an operator "
            "edit is never silently clobbered."
        ),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help=(
            "Print what would change without touching the filesystem. "
            "audit-cli §2 — every mutating verb must expose --dry-run."
        ),
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help=(
            "Accept all confirmation prompts (no-op today; symlink installs "
            "are non-interactive). Required by audit-cli §2 for mutating "
            "verbs so callers can scriptedly bypass any future confirm "
            "logic."
        ),
    )
    def hooks_install(target, names, force, dry_run, yes):
        """Install bundled hooks as symlinks into the target project.

        \b
        Example:
            $ scitex-dev hooks install --target ~/proj/my-research
            installed  run_lint  →  ~/proj/my-research/docs/to_claude/hooks/post-tool-use/run_lint.sh
        """
        del yes  # --yes is reserved for audit-cli §2 conformance; no
                 # confirmation prompts are issued today.
        project = Path(target)
        if not dry_run:
            project.mkdir(parents=True, exist_ok=True)
        chosen = list(names) if names else sorted(KNOWN_HOOKS)
        had_refusal = False
        for name in chosen:
            source, deploy_rel = KNOWN_HOOKS[name]
            if dry_run:
                target_path = project / deploy_rel
                click.echo(f"would install  {name}  →  {target_path}")
                continue
            status = _install_one(name, source, deploy_rel, project, force)
            symbol = {
                "installed": click.style("installed ", fg="green"),
                "updated": click.style("updated   ", fg="green"),
                "up-to-date": click.style("up-to-date", fg="cyan"),
                "refused": click.style("refused   ", fg="red"),
                "forced": click.style("forced    ", fg="yellow"),
            }[status]
            target_path = project / deploy_rel
            click.echo(f"{symbol}  {name}  →  {target_path}")
            if status == "refused":
                had_refusal = True
                click.echo(
                    click.style(
                        "  (a non-symlink file exists at the target; pass "
                        "--force to overwrite, or remove it manually.)",
                        fg="red",
                    ),
                    err=True,
                )
        if had_refusal:
            raise SystemExit(1)

    @hooks_group.command("update", short_help="Re-link installed hooks to the current canonical.")
    @click.option(
        "--target",
        "target",
        required=True,
        type=click.Path(file_okay=False, dir_okay=True, exists=True, resolve_path=True),
        help="Project root with an existing hooks directory.",
    )
    @click.option(
        "--name",
        "names",
        multiple=True,
        type=click.Choice(sorted(KNOWN_HOOKS), case_sensitive=False),
        help="Limit update to specific hook names. Defaults to all.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help=(
            "Print what would change without touching the filesystem. "
            "audit-cli §2 — every mutating verb must expose --dry-run."
        ),
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help=(
            "Accept all confirmation prompts (no-op today; no interactive "
            "confirm logic). Required by audit-cli §2 for mutating verbs."
        ),
    )
    def hooks_update(target, names, dry_run, yes):
        """Equivalent to ``install --force`` for a project that already
        has the directory tree. Replaces non-symlink files too — call
        only when you mean to discard local edits.

        \b
        Example:
            $ scitex-dev hooks update --target ~/proj/my-research
        """
        del yes
        project = Path(target)
        chosen = list(names) if names else sorted(KNOWN_HOOKS)
        for name in chosen:
            source, deploy_rel = KNOWN_HOOKS[name]
            if dry_run:
                click.echo(f"would update  {name}  →  {project / deploy_rel}")
                continue
            status = _install_one(name, source, deploy_rel, project, force=True)
            symbol = {
                "installed": click.style("installed ", fg="green"),
                "updated": click.style("updated   ", fg="green"),
                "up-to-date": click.style("up-to-date", fg="cyan"),
                "forced": click.style("forced    ", fg="yellow"),
            }.get(status, status)
            click.echo(f"{symbol}  {name}  →  {project / deploy_rel}")

    @hooks_group.command("list", short_help="Show the install status of each hook.")
    @click.option(
        "--target",
        "target",
        required=True,
        type=click.Path(file_okay=False, dir_okay=True, exists=True, resolve_path=True),
        help="Project root to inspect.",
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help=(
            "Emit machine-readable JSON instead of the coloured table. "
            "audit-cli §2 — every read verb must expose --json."
        ),
    )
    def hooks_list(target, as_json):
        """Report which hooks are installed and whether they point at
        the canonical source.

        \b
        Example:
            $ scitex-dev hooks list --target ~/proj/my-research
            ok       run_lint  → bundled canonical
            missing  …
        """
        import json as _json

        project = Path(target)
        rows = []
        for name in sorted(KNOWN_HOOKS):
            source, deploy_rel = KNOWN_HOOKS[name]
            status = _list_one(name, source, deploy_rel, project)
            rows.append((name, status, source, str(project / deploy_rel)))
        if as_json:
            click.echo(
                _json.dumps(
                    [
                        {
                            "name": n,
                            "status": s,
                            "source": src,
                            "target": tgt,
                        }
                        for n, s, src, tgt in rows
                    ],
                    indent=2,
                )
            )
            return
        for name, status, _source, target_path in rows:
            symbol = {
                "ok": click.style("ok      ", fg="green"),
                "drift": click.style("drift   ", fg="yellow"),
                "stale": click.style("stale   ", fg="red"),
                "missing": click.style("missing ", fg="white"),
            }[status]
            click.echo(f"{symbol}  {name}  →  {target_path}")

    # Renamed `path` → `print-path` per audit-cli §1: a bare noun-typed
    # leaf at the verb position is forbidden (the auditor reads `path`
    # as a noun, not an action). `print-path` is the compound-leaf form
    # the catalog recommends for a one-off read action.
    @hooks_group.command(
        "print-path",
        short_help="Print the absolute path of a bundled hook script.",
        epilog=(
            "Example:\n"
            "  $ scitex-dev hooks print-path run_lint\n"
            "  /uvwork/venv-agent/lib/python3.12/site-packages/scitex_dev/_hooks/run_lint.sh\n"
            "\n"
            "  $ ln -s \"$(scitex-dev hooks print-path run_lint)\" \\\n"
            "      docs/to_claude/hooks/post-tool-use/run_lint.sh"
        ),
    )
    @click.argument("name", type=click.Choice(sorted(KNOWN_HOOKS), case_sensitive=False))
    def hooks_print_path(name):
        """Print the bundled hook script's absolute filesystem path.

        \b
        Example:
            $ scitex-dev hooks print-path run_lint
            /uvwork/venv-agent/lib/python3.12/site-packages/scitex_dev/_hooks/run_lint.sh

        Useful in shell scripts:

        \b
            ln -s "$(scitex-dev hooks print-path run_lint)" \\
                docs/to_claude/hooks/post-tool-use/run_lint.sh
        """
        source, _ = KNOWN_HOOKS[name]
        click.echo(source)


__all__ = ["KNOWN_HOOKS", "register_hooks_commands"]
