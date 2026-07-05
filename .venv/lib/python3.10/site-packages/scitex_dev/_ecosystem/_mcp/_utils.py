#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP utilities for consuming Result objects."""

from __future__ import annotations

from typing import Any, Callable

from ..._core.types import Result


def run_as_mcp(fn: Callable, **kwargs: Any) -> str:
    """Call a ``@supports_return_as`` function and return MCP-ready JSON.

    Parameters
    ----------
    fn : Callable
        A function decorated with ``@supports_return_as``.
    **kwargs
        Arguments to pass to ``fn``.

    Returns
    -------
    str
        JSON string with the full Result structure.
    """
    result = fn(**kwargs, return_as="result")
    return result.to_json()


def wrap_as_mcp(
    fn: Callable,
    *,
    side_effects: list[str] | None = None,
    hints_on_error: list[str] | None = None,
    idempotent: bool = False,
    **kwargs: Any,
) -> str:
    """Call any function and wrap its return in Result JSON.

    Unlike ``run_as_mcp`` (which requires ``@supports_return_as``),
    this wraps any plain function. Use this to retrofit existing
    handlers without modifying the underlying function.

    Parameters
    ----------
    fn : Callable
        Any callable returning data or raising exceptions.
    side_effects : list[str], optional
        Declared side effects (e.g. ``["file_create: /tmp/out.csv"]``).
    hints_on_error : list[str], optional
        Recovery guidance for expected failures (FAQ-style).
    idempotent : bool
        Whether the operation is safe to retry.
    **kwargs
        Arguments to pass to ``fn``.

    Returns
    -------
    str
        JSON string with Result structure.
    """
    from ..._core.errors import classify_exception

    try:
        data = fn(**kwargs)
        return Result(
            success=True,
            data=data,
            side_effects=side_effects,
            idempotent=idempotent,
        ).to_json()
    except Exception as exc:
        error_code = classify_exception(exc)
        err_hints = list(hints_on_error or [])
        suggestion = getattr(exc, "suggestion", None)
        if suggestion:
            err_hints.append(suggestion)
        suggestions = getattr(exc, "suggestions", None)
        if suggestions and isinstance(suggestions, list):
            err_hints.extend(suggestions)
        context = getattr(exc, "context", {})
        return Result(
            success=False,
            error=str(exc),
            error_code=error_code.value,
            context=context if isinstance(context, dict) else {},
            hints_on_error=err_hints,
        ).to_json()


async def async_wrap_as_mcp(
    coro_fn: Callable,
    *,
    side_effects: list[str] | None = None,
    hints_on_error: list[str] | None = None,
    idempotent: bool = False,
    **kwargs: Any,
) -> str:
    """Async version of ``wrap_as_mcp`` for async handlers.

    Parameters
    ----------
    coro_fn : Callable
        Any async callable (coroutine function) returning data
        or raising exceptions.
    side_effects : list[str], optional
        Declared side effects.
    hints_on_error : list[str], optional
        Recovery guidance for expected failures (FAQ-style).
    idempotent : bool
        Whether the operation is safe to retry.
    **kwargs
        Arguments to pass to ``coro_fn``.

    Returns
    -------
    str
        JSON string with Result structure.
    """
    from ..._core.errors import classify_exception

    try:
        data = await coro_fn(**kwargs)
        return Result(
            success=True,
            data=data,
            side_effects=side_effects,
            idempotent=idempotent,
        ).to_json()
    except Exception as exc:
        error_code = classify_exception(exc)
        err_hints = list(hints_on_error or [])
        suggestion = getattr(exc, "suggestion", None)
        if suggestion:
            err_hints.append(suggestion)
        suggestions = getattr(exc, "suggestions", None)
        if suggestions and isinstance(suggestions, list):
            err_hints.extend(suggestions)
        context = getattr(exc, "context", {})
        return Result(
            success=False,
            error=str(exc),
            error_code=error_code.value,
            context=context if isinstance(context, dict) else {},
            hints_on_error=err_hints,
        ).to_json()


def result_to_mcp(result: Result) -> str:
    """Convert an existing Result to MCP-ready JSON."""
    return result.to_json()


# EOF
