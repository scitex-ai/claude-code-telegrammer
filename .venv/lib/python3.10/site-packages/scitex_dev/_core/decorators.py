#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decorator for opt-in structured Result wrapping.

The ``@supports_return_as`` decorator adds a ``return_as`` keyword
parameter to any function. By default the function behaves normally.
With ``return_as="result"``, the return value is wrapped in a Result.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from .errors import classify_exception
from .types import Result


def supports_return_as(fn: Callable) -> Callable:
    """Add ``return_as="result"`` support to a function.

    - ``return_as=None`` (default): data returned, exceptions raised.
    - ``return_as="result"``: wrapped in ``Result``.
    - Any other value: passed through to the original function.

    Examples
    --------
    >>> @supports_return_as
    ... def add(a: int, b: int) -> int:
    ...     return a + b
    >>> add(1, 2)
    3
    >>> result = add(1, 2, return_as="result")
    >>> result.success
    True
    >>> result.data
    3
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, return_as: str | None = None, **kwargs: Any) -> Any:
        if return_as != "result":
            if return_as is not None:
                kwargs["return_as"] = return_as
            return fn(*args, **kwargs)

        try:
            data = fn(*args, **kwargs)
            return Result(success=True, data=data)
        except Exception as exc:
            error_code = classify_exception(exc)
            suggestion = getattr(exc, "suggestion", None)
            context = getattr(exc, "context", {})
            hints_on_error = []
            if suggestion:
                hints_on_error.append(suggestion)
            suggestions = getattr(exc, "suggestions", None)
            if suggestions and isinstance(suggestions, list):
                hints_on_error.extend(suggestions)

            return Result(
                success=False,
                error=str(exc),
                error_code=error_code.value,
                context=context if isinstance(context, dict) else {},
                hints_on_error=hints_on_error,
            )

    return wrapper


# EOF
