#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI utilities for consuming Result objects."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from .._core.types import Result


def handle_result(
    result: Result,
    as_json: bool = False,
    file: Any = None,
) -> int:
    """Format and print a Result, return the exit code.

    Parameters
    ----------
    result : Result
        The structured result to display.
    as_json : bool
        If True, output full JSON. If False, human-friendly text.
    file : file-like | None
        Output stream. Defaults to stdout/stderr based on success.

    Returns
    -------
    int
        Exit code suitable for ``sys.exit()``.
    """
    if as_json:
        out = file or sys.stdout
        print(result.to_json(), file=out)
    elif result.success:
        out = file or sys.stdout
        data = result.data
        if isinstance(data, (dict, list, tuple)):
            print(json.dumps(data, indent=2, default=str), file=out)
        else:
            print(data, file=out)
    else:
        out = file or sys.stderr
        print(f"Error: {result.error}", file=out)
        if result.hints_on_error:
            print("", file=out)
            for hint in result.hints_on_error:
                print(f"  - {hint}", file=out)

    return result.exit_code


def run_as_cli(
    fn: Callable,
    as_json: bool = False,
    **kwargs: Any,
) -> None:
    """Call a ``@supports_return_as`` function and exit with proper code.

    Parameters
    ----------
    fn : Callable
        A function decorated with ``@supports_return_as``.
    as_json : bool
        If True, output full JSON.
    **kwargs
        Arguments to pass to ``fn``.
    """
    result = fn(**kwargs, return_as="result")
    code = handle_result(result, as_json=as_json)
    sys.exit(code)


def wrap_as_cli(
    fn: Callable,
    as_json: bool = False,
    **kwargs: Any,
) -> None:
    """Call any function and display its result via CLI.

    Like ``wrap_as_mcp`` but for terminal output. Wraps any plain
    function in Result, formats based on ``as_json``, and exits
    with proper exit code.

    Parameters
    ----------
    fn : Callable
        Any callable returning data or raising exceptions.
    as_json : bool
        If True, output full JSON Result. If False, human-friendly text.
    **kwargs
        Arguments to pass to ``fn``.
    """
    from .._core.errors import classify_exception

    try:
        data = fn(**kwargs)
        result = Result(success=True, data=data)
    except Exception as exc:
        error_code = classify_exception(exc)
        hints_on_error = []
        suggestion = getattr(exc, "suggestion", None)
        if suggestion:
            hints_on_error.append(suggestion)
        suggestions = getattr(exc, "suggestions", None)
        if suggestions and isinstance(suggestions, list):
            hints_on_error.extend(suggestions)
        context = getattr(exc, "context", {})
        result = Result(
            success=False,
            error=str(exc),
            error_code=error_code.value,
            context=context if isinstance(context, dict) else {},
            hints_on_error=hints_on_error,
        )

    code = handle_result(result, as_json=as_json)
    sys.exit(code)


# --- Reusable CLI option factories ---


def json_option(fn: Callable) -> Callable:
    """Click decorator: adds ``--json`` flag as ``as_json`` parameter.

    Uses lazy ``import click`` so scitex-dev stays stdlib-only.
    """
    import click

    return click.option(
        "--json",
        "as_json",
        is_flag=True,
        help="Output as structured JSON (Result envelope).",
    )(fn)


def dry_run_option(fn: Callable) -> Callable:
    """Click decorator: adds ``--dry-run`` flag.

    Uses lazy ``import click`` so scitex-dev stays stdlib-only.
    """
    import click

    return click.option(
        "--dry-run",
        is_flag=True,
        help="Preview changes without executing.",
    )(fn)


def add_json_argument(parser: Any) -> None:
    """Add ``--json`` flag to an argparse parser."""
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        default=False,
        help="Output as structured JSON (Result envelope).",
    )


def add_dry_run_argument(parser: Any) -> None:
    """Add ``--dry-run`` flag to an argparse parser."""
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help="Preview changes without executing.",
    )


# EOF
