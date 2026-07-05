#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared CLI tab-completion helper for every scitex-* package.

Per `_skills/general/03_interface/02_cli/03_required-introspection-commands.md`
§1a, every scitex-* CLI MUST expose `install-shell-completion` and
`print-shell-completion` so users actually get `<TAB>` completion.

Usage from a downstream package's CLI module:

    from scitex_dev._cli._completion import attach_shell_completion

    @click.group(...)
    def cli():
        ...

    attach_shell_completion(cli, prog_name="scitex-io")

That single call registers four leaves on `cli`:

  * `install-shell-completion --shell {bash,zsh,fish}`  (canonical)
  * `print-shell-completion   --shell {bash,zsh,fish}`  (canonical)
  * `install-tab-completion`   (hidden deprecated alias → install-shell-completion)
  * `completion`               (hidden deprecated alias → install-shell-completion)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click

_SOURCE_MAP = {"bash": "bash_source", "zsh": "zsh_source", "fish": "fish_source"}


def _env_var(prog_name: str) -> str:
    """Click's autocompletion env var format: `_<UPPER_PROG>_COMPLETE`."""
    return "_" + prog_name.upper().replace("-", "_") + "_COMPLETE"


def _rc_path(shell: str, prog_name: str) -> str:
    if shell == "fish":
        return os.path.expanduser(f"~/.config/fish/completions/{prog_name}.fish")
    return os.path.expanduser({"bash": "~/.bashrc", "zsh": "~/.zshrc"}[shell])


def _marker(prog_name: str) -> str:
    return f"# {prog_name} tab completion"


def _eval_line(shell: str, prog_name: str) -> str:
    """Legacy eval-form line. Kept for migration detection / removal only."""
    return (
        f'eval "$({_env_var(prog_name)}={_SOURCE_MAP[shell]} {prog_name})"  '
        f"{_marker(prog_name)}"
    )


def _scitex_dir() -> Path:
    """Resolve `$SCITEX_DIR` (default `~/.scitex`). Honours §6 relocation."""
    return Path(os.environ.get("SCITEX_DIR", os.path.expanduser("~/.scitex")))


def _pkg_short(prog_name: str) -> str:
    """`scitex-io` → `io`; `figrecipe` → `figrecipe`."""
    if prog_name.startswith("scitex-"):
        return prog_name[len("scitex-") :]
    return prog_name


def _cache_path(prog_name: str) -> Path:
    """Canonical primary cache: `$SCITEX_DIR/<short>/runtime/completion/<prog>`."""
    return _scitex_dir() / _pkg_short(prog_name) / "runtime" / "completion" / prog_name


def _xdg_symlink(prog_name: str) -> Path:
    """XDG bash-completion auto-discovery slot.

    Symlinking the primary cache into `~/.local/share/bash-completion/
    completions/<prog>` lets bash-completion auto-source it on first
    `<TAB>` even before the user adds the `source` line — defence in
    depth. Best-effort only; failure to create the symlink does not
    abort install.
    """
    return (
        Path(os.path.expanduser("~/.local/share/bash-completion/completions"))
        / prog_name
    )


def _source_line(cache_path: Path, prog_name: str) -> str:
    return f"[ -f {cache_path} ] && source {cache_path}  {_marker(prog_name)}"


def _generate_script(shell: str, prog_name: str) -> str:
    env = os.environ.copy()
    env[_env_var(prog_name)] = _SOURCE_MAP[shell]
    result = subprocess.run([prog_name], capture_output=True, text=True, env=env)
    script = result.stdout.strip()
    if not script:
        raise click.ClickException(
            f"Failed to generate {shell} completion script for {prog_name}."
        )
    return script


def attach_shell_completion(main_group, *, prog_name: str) -> None:
    """Register the 4 shell-completion leaves on `main_group`."""

    @main_group.command("print-shell-completion")
    @click.option(
        "--shell",
        type=click.Choice(["bash", "zsh", "fish"]),
        default="bash",
        help="Target shell. Default: bash.",
    )
    def print_shell_completion(shell):
        """Print the click-generated completion script to stdout.

        \b
        Example:
          $ <cli> print-shell-completion --shell bash
          $ <cli> print-shell-completion --shell zsh
          $ eval "$(<cli> print-shell-completion --shell bash)"
        """
        click.echo(_generate_script(shell, prog_name))

    # Click caches `help` from the docstring at decoration time, so
    # mutating __doc__ post-hoc is too late — also overwrite the
    # registered Command's `help` attribute so `<cli>` is rendered as
    # the actual prog name in `--help` output (audit-cli §4 expects a
    # concrete example, not a placeholder).
    _psc_cmd = main_group.commands["print-shell-completion"]
    _psc_cmd.help = (_psc_cmd.help or "").replace("<cli>", prog_name)
    print_shell_completion.__doc__ = (print_shell_completion.__doc__ or "").replace(
        "<cli>", prog_name
    )

    def _swap_cli_placeholder_post(name: str, fn) -> None:
        cmd = main_group.commands[name]
        cmd.help = (cmd.help or "").replace("<cli>", prog_name)
        fn.__doc__ = (fn.__doc__ or "").replace("<cli>", prog_name)

    @main_group.command("install-shell-completion")
    @click.option(
        "--shell",
        type=click.Choice(["bash", "zsh", "fish"]),
        default="bash",
        help="Target shell. Default: bash.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the eval line and target rc file without writing.",
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def install_shell_completion(shell, dry_run, yes):
        """Wire up `<TAB>` completion in the user's shell rc.

        \b
        Example:
          $ <cli> install-shell-completion              # → ~/.bashrc
          $ <cli> install-shell-completion --shell zsh  # → ~/.zshrc
          $ <cli> install-shell-completion --dry-run    # preview only

        \b
        Activate in the current shell after install:
          source ~/.bashrc
        """
        del yes  # accepted for §2 compliance; use --dry-run for preview
        rc_path = _rc_path(shell, prog_name)

        if shell == "fish":
            if dry_run:
                click.echo(f"Would write fish completion to {rc_path}")
                return
            os.makedirs(os.path.dirname(rc_path), exist_ok=True)
            with open(rc_path, "w") as f:
                f.write(_generate_script(shell, prog_name))
            click.echo(f"Tab completion installed at {rc_path}")
            click.echo(f"Run: source {rc_path}")
            return

        # Cache-file pattern (§11 + 03_required-introspection §1a):
        #   1. Generate completion script ONCE → cache file under
        #      $SCITEX_DIR/<short>/runtime/completion/<prog>.
        #   2. Symlink it into the XDG bash-completion auto-discovery
        #      slot (best-effort).
        #   3. Append a `[ -f cache ] && source cache` line to rc.
        # Sourcing rc takes microseconds vs. ~0.4s for the eval form
        # that re-invokes the binary on every shell start.
        cache = _cache_path(prog_name)
        line = _source_line(cache, prog_name)
        marker = _marker(prog_name)
        legacy_eval = _eval_line(shell, prog_name)

        if dry_run:
            click.echo(f"Would write completion cache to {cache}")
            click.echo(f"Would symlink XDG slot {_xdg_symlink(prog_name)}")
            click.echo(f"Would append to {rc_path}:")
            click.echo(f"  {line}")
            return

        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(_generate_script(shell, prog_name) + "\n")

        xdg = _xdg_symlink(prog_name)
        try:
            xdg.parent.mkdir(parents=True, exist_ok=True)
            if xdg.is_symlink() or xdg.exists():
                xdg.unlink()
            xdg.symlink_to(cache)
        except OSError:
            pass  # XDG slot is convenience; rc source line is canonical

        # Migrate: drop the legacy eval line if a previous install left
        # one in rc — otherwise the user gets both, slow start lingers.
        existing = ""
        if os.path.isfile(rc_path):
            with open(rc_path) as f:
                existing = f.read()
        if marker in existing and line.strip() in existing:
            click.echo(f"Tab completion already installed in {rc_path}")
            return
        if marker in existing:
            # Strip every line carrying the marker so we replace cleanly.
            kept = [ln for ln in existing.splitlines() if marker not in ln]
            existing = "\n".join(kept).rstrip() + "\n"
            with open(rc_path, "w") as f:
                f.write(existing)
            click.echo(f"Removed previous {prog_name} completion line from {rc_path}")
        del legacy_eval  # informational only

        with open(rc_path, "a") as f:
            f.write(f"\n{line}\n")
        click.echo(f"Tab completion installed for {prog_name}")
        click.echo(f"  cache:  {cache}")
        click.echo(f"  rc:     {rc_path}  (source line appended)")
        click.echo(f"Run: source {rc_path}")

    _swap_cli_placeholder_post("install-shell-completion", install_shell_completion)

    @main_group.command(
        "install-tab-completion",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def install_tab_completion_deprecated(ctx):
        """(deprecated) Renamed to `install-shell-completion`."""
        click.echo(
            f"error: `{prog_name} install-tab-completion` was renamed to "
            f"`{prog_name} install-shell-completion`.\n"
            f"Re-run with: {prog_name} install-shell-completion",
            err=True,
        )
        ctx.exit(2)

    @main_group.command(
        "completion",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def completion_deprecated(ctx):
        """(deprecated) Renamed to `install-shell-completion`."""
        click.echo(
            f"error: `{prog_name} completion` was renamed to "
            f"`{prog_name} install-shell-completion`.\n"
            f"Re-run with: {prog_name} install-shell-completion",
            err=True,
        )
        ctx.exit(2)


# ----- Backwards compat for scitex-dev's own _root.py call site ----------
# The legacy entry point `register_completion_command(main_group)` is kept
# so scitex-dev's existing import doesn't break during the rollout.


def register_completion_command(main_group):
    """(legacy) Use `attach_shell_completion(main_group, prog_name=...)`."""
    attach_shell_completion(main_group, prog_name="scitex-dev")
