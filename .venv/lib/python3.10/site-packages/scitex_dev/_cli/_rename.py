#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev rename-symbols`` — bulk-rename CLI surface.

Extracted from ``_root.py`` for line-budget hygiene. The single
``register(main)`` entry-point attaches both the canonical
``rename-symbols`` command and the hidden ``rename`` deprecation alias
to the top-level click group.

Two ergonomic flags worth knowing:

- ``--allow-dirty`` skips the uncommitted-changes guard. Lets you chain
  multiple regex passes within one logical rename without committing
  between each pass. The reverse-rename safety contract still holds:
  every rename is invertible by re-running with old/new swapped.
- ``--quiet`` (``-q``) emits a one-line ``N files / M matches /
  K collisions`` summary instead of the full ``RenameResult`` repr.
  Useful for chained renames and CI logs.
"""

from __future__ import annotations

import sys

import click


def register(main: click.Group) -> None:
    """Attach rename commands to the top-level click group."""

    @main.command(
        "rename",
        hidden=True,
        context_settings={
            "ignore_unknown_options": True,
            "allow_extra_args": True,
        },
    )
    @click.pass_context
    def _rename_deprecated(ctx):
        """(deprecated) Renamed to ``rename-symbols``."""
        click.echo(
            "error: `scitex-dev rename` was renamed to `scitex-dev rename-symbols`.\n"
            "Re-run with: scitex-dev rename-symbols <old> <new> [...]",
            err=True,
        )
        ctx.exit(2)

    @main.command("rename-symbols")
    @click.argument("old_name")
    @click.argument("new_name")
    @click.option("--root", default=".", help="Root directory for rename.")
    @click.option("--dry-run", is_flag=True, help="Preview without renaming.")
    @click.option("--regex", is_flag=True, help="Treat pattern as Python regex.")
    @click.option(
        "--exclude",
        multiple=True,
        help="Exclude paths containing this substring. Repeatable.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    @click.option(
        "--allow-dirty",
        is_flag=True,
        help=(
            "Skip the uncommitted-changes check. Lets you chain "
            "multiple regex passes within one logical rename without "
            "committing between each pass. The reverse-rename safety "
            "contract still holds — every rename is invertible by "
            "re-running with old/new swapped."
        ),
    )
    @click.option(
        "--quiet",
        "-q",
        is_flag=True,
        help=(
            "Emit a one-line summary ('N files / M matches / "
            "K collisions') instead of the full RenameResult repr. "
            "Useful for chained renames and CI logs."
        ),
    )
    def _rename_symbols(
        old_name,
        new_name,
        root,
        dry_run,
        regex,
        exclude,
        as_json,
        yes,
        allow_dirty,
        quiet,
    ):
        """Bulk rename with cross-reference updates. Supports --regex.

        \b
        Example:
            $ scitex-dev rename-symbols old_func new_func --dry-run
            $ scitex-dev rename-symbols old_func new_func --yes
            $ scitex-dev rename-symbols 'old_(\\w+)' 'new_\\1' --regex --dry-run
            $ scitex-dev rename-symbols old new --regex --allow-dirty -q
        """
        del yes  # accepted for §2; use --dry-run for preview
        extra_excludes = list(exclude) if exclude else []

        # Quiet mode short-circuits wrap_as_cli's RenameResult repr and
        # emits a one-line summary directly. JSON mode wins over quiet
        # because callers asked explicitly for the full envelope.
        if quiet and not as_json:
            from .. import execute_rename, preview_rename

            common = dict(
                pattern=old_name,
                replacement=new_name,
                directory=root,
                regex=regex,
                extra_excludes=extra_excludes,
            )
            if dry_run:
                result = preview_rename(**common)
            else:
                result = execute_rename(**common, force=allow_dirty)
            if result.error:
                click.echo(f"error: {result.error}", err=True)
                sys.exit(1)
            s = result.summary or {}
            verb = "would rename" if dry_run else "renamed"
            click.echo(
                f"{verb}: "
                f"{s.get('content_files', 0)} files / "
                f"{s.get('content_matches', 0)} matches / "
                f"{s.get('collisions', 0)} collisions"
            )
            sys.exit(0)

        from ._utils import wrap_as_cli

        if dry_run:
            from .. import preview_rename

            wrap_as_cli(
                preview_rename,
                as_json=as_json,
                pattern=old_name,
                replacement=new_name,
                directory=root,
                regex=regex,
                extra_excludes=extra_excludes,
            )
        else:
            from .. import execute_rename

            wrap_as_cli(
                execute_rename,
                as_json=as_json,
                pattern=old_name,
                replacement=new_name,
                directory=root,
                regex=regex,
                extra_excludes=extra_excludes,
                force=allow_dirty,
            )


# EOF
