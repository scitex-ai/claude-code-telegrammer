"""Argparse adapter for the §11 CLI auditor.

Lives outside ``scitex_dev._cli/`` deliberately: the §11 rule scans every
``_cli/**/*.py`` for ``import argparse`` and would otherwise flag the auditor
itself. The auditor still has to *understand* argparse so it can wrap legacy
argparse-based CLIs in third-party packages and check them for the same
universal-flag/grammar invariants Click CLIs are checked against.

Public surface (imported by ``scitex_dev._cli.audit._summary._audit``):
- ``SyntheticOption``, ``ArgparseLeaf``, ``ArgparseGroup`` — Click duck-types.
- ``argparse_subcommands(parser)`` — extract subparsers from a parser.
- ``argparse_flag_params(parser)`` — extract option-string params.
- ``wrap_argparse(parser, name)`` — recursively wrap a parser as a Click tree.
- ``intercept_parse_calls(captured)`` — context manager that patches
  ``argparse.ArgumentParser.parse_args/parse_known_args`` and
  ``click.BaseCommand.main`` to capture the receiver and abort with
  ``StopBeforeParse``.
- ``StopBeforeParse`` — sentinel raised by the patched methods.
"""

from __future__ import annotations

import argparse
import contextlib

import click


class SyntheticOption:
    """Minimal Click-Option duck-type for `_flag_names()`."""

    def __init__(self, opts: list[str]):
        self.opts = list(opts)
        self.secondary_opts: list[str] = []


class ArgparseLeaf(click.Command):
    """Click.Command wrapper around a leaf argparse parser."""

    def __init__(self, name, help_text, epilog, params_):
        super().__init__(
            name=name,
            callback=lambda: None,
            help=help_text or None,
            epilog=epilog or None,
        )
        self.params = params_  # type: ignore[assignment]


class ArgparseGroup(click.Group):
    """Click.Group wrapper around an argparse parser with subparsers."""

    def __init__(self, name, help_text, epilog, params_, commands):
        super().__init__(
            name=name,
            callback=lambda: None,
            help=help_text or None,
            epilog=epilog or None,
        )
        self.params = params_  # type: ignore[assignment]
        self.commands = commands


def argparse_subcommands(parser) -> dict[str, object]:
    out: dict[str, object] = {}
    for action in getattr(parser, "_actions", []) or []:
        if isinstance(action, argparse._SubParsersAction):
            for name, sp in action.choices.items():
                out[name] = sp
    return out


def argparse_flag_params(parser) -> list[SyntheticOption]:
    params: list[SyntheticOption] = []
    for action in getattr(parser, "_actions", []) or []:
        if isinstance(action, argparse._SubParsersAction):
            continue
        if not getattr(action, "option_strings", None):
            continue  # positional argument
        params.append(SyntheticOption(list(action.option_strings)))
    return params


def wrap_argparse(parser, name: str | None = None) -> click.BaseCommand:
    name = name or getattr(parser, "prog", None) or "<root>"
    name = name.split()[0] if isinstance(name, str) else "<root>"
    help_text = (getattr(parser, "description", "") or "").strip()
    epilog = (getattr(parser, "epilog", "") or "").strip()
    params = argparse_flag_params(parser)
    children_raw = argparse_subcommands(parser)
    if children_raw:
        commands = {n: wrap_argparse(sp, n) for n, sp in children_raw.items()}
        return ArgparseGroup(name, help_text, epilog, params, commands)
    return ArgparseLeaf(name, help_text, epilog, params)


class StopBeforeParse(Exception):
    """Sentinel used to abort `main()` once it constructs its argparse parser."""


@contextlib.contextmanager
def intercept_parse_calls(captured: list[object]):
    """Patch `argparse.ArgumentParser.parse_args/parse_known_args` and
    `click.BaseCommand.main` to capture the receiver and raise
    `StopBeforeParse` instead of actually executing the CLI.

    Any list passed in receives one append per intercepted call.

    Restores all three patched methods on exit, even if the wrapped block raises.
    """
    real_pa = argparse.ArgumentParser.parse_args
    real_pka = argparse.ArgumentParser.parse_known_args
    real_click_main = click.BaseCommand.main

    def _fake_pa(self, *a, **kw):
        captured.append(self)
        raise StopBeforeParse()

    def _fake_pka(self, *a, **kw):
        captured.append(self)
        raise StopBeforeParse()

    def _fake_click_main(self, *a, **kw):
        captured.append(self)
        raise StopBeforeParse()

    argparse.ArgumentParser.parse_args = _fake_pa  # type: ignore[assignment]
    argparse.ArgumentParser.parse_known_args = _fake_pka  # type: ignore[assignment]
    click.BaseCommand.main = _fake_click_main  # type: ignore[assignment]
    try:
        yield
    finally:
        argparse.ArgumentParser.parse_args = real_pa  # type: ignore[assignment]
        argparse.ArgumentParser.parse_known_args = real_pka  # type: ignore[assignment]
        click.BaseCommand.main = real_click_main  # type: ignore[assignment]
