"""Reusable Click helpers shared across SciTeX ecosystem CLIs.

Currently exports `CategorizedGroup` so any package's top-level CLI can
render a grouped command list (per general/03_interface/02_cli §6).

Usage::

    import click
    from scitex_dev.ecosystem import CategorizedGroup, make_categorized_group

    CATEGORIES = [
        ("Lifecycle", ["start", "stop", "restart"]),
        ("Health", ["check-health", "show-status"]),
    ]

    @click.group(cls=make_categorized_group(CATEGORIES))
    def main():
        pass
"""

from __future__ import annotations

from typing import Sequence

import click


class CategorizedGroup(click.Group):
    """Click `Group` that renders `--help` commands under named sections.

    Subclass and set ``COMMAND_CATEGORIES`` as a class attribute, OR use
    :func:`make_categorized_group` to build a one-off subclass with the
    categories baked in.

    Categories format: list of ``(section_name, [command_name, ...])``.
    Anything not listed falls into a final ``Other`` section so nothing
    silently disappears.
    """

    COMMAND_CATEGORIES: Sequence[tuple[str, Sequence[str]]] = ()

    def format_commands(self, ctx, formatter):
        commands = {}
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is not None and not cmd.hidden:
                commands[subcommand] = cmd

        if not commands:
            return

        displayed: set[str] = set()
        for section, names in self.COMMAND_CATEGORIES:
            items = []
            for name in names:
                if name in commands and name not in displayed:
                    cmd = commands[name]
                    items.append((name, cmd.get_short_help_str(limit=formatter.width)))
                    displayed.add(name)
            if items:
                with formatter.section(section):
                    formatter.write_dl(items)

        leftover = [
            (n, commands[n].get_short_help_str(limit=formatter.width))
            for n in sorted(commands)
            if n not in displayed
        ]
        if leftover:
            with formatter.section("Other"):
                formatter.write_dl(leftover)


def make_categorized_group(
    categories: Sequence[tuple[str, Sequence[str]]],
    *,
    base: type[click.Group] = CategorizedGroup,
) -> type[click.Group]:
    """Return a fresh subclass of ``base`` with ``categories`` baked in.

    Useful when the CLI's top-level group already inherits from a custom
    base (e.g. an existing ``HelpRecursiveGroup``) — pass that base via
    ``base=`` and you get a multi-inheriting subclass that combines both.
    """

    class _Categorized(base):  # type: ignore[misc, valid-type]
        COMMAND_CATEGORIES = tuple(categories)

    _Categorized.__name__ = "CategorizedGroup"
    _Categorized.__qualname__ = "CategorizedGroup"
    return _Categorized


__all__ = ["CategorizedGroup", "make_categorized_group"]
