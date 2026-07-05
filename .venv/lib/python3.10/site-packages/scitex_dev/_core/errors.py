#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Error code registry for LLM-friendly error categorization.

Provides machine-readable error codes that map to CLI exit codes
and guide LLM error recovery.
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Machine-readable error codes for structured error responses."""

    OK = "E000"
    VALIDATION = "E001"
    FILE_NOT_FOUND = "E002"
    PERMISSION = "E003"
    DEPENDENCY = "E004"
    TIMEOUT = "E005"
    RATE_LIMITED = "E006"
    NETWORK = "E007"
    CONFIG = "E008"
    CONFLICT = "E009"
    INTERNAL = "E999"

    @property
    def exit_code(self) -> int:
        """POSIX-style exit code for this error category."""
        return _EXIT_CODES.get(self, 1)


_EXIT_CODES = {
    ErrorCode.OK: 0,
    ErrorCode.VALIDATION: 2,
    ErrorCode.FILE_NOT_FOUND: 1,
    ErrorCode.PERMISSION: 4,
    ErrorCode.DEPENDENCY: 3,
    ErrorCode.TIMEOUT: 5,
    ErrorCode.RATE_LIMITED: 5,
    ErrorCode.NETWORK: 1,
    ErrorCode.CONFIG: 2,
    ErrorCode.CONFLICT: 6,
    ErrorCode.INTERNAL: 1,
}

_BUILTIN_ERROR_MAP: dict[type, ErrorCode] = {
    FileNotFoundError: ErrorCode.FILE_NOT_FOUND,
    PermissionError: ErrorCode.PERMISSION,
    TimeoutError: ErrorCode.TIMEOUT,
    ConnectionError: ErrorCode.NETWORK,
    ImportError: ErrorCode.DEPENDENCY,
    ValueError: ErrorCode.VALIDATION,
    TypeError: ErrorCode.VALIDATION,
    KeyError: ErrorCode.CONFIG,
}


class ScitexError(Exception):
    """Canonical SciTeX exception for structured failures.

    Use when the failure crosses an MCP / CLI / HTTP boundary and the caller
    (often an LLM agent) needs a machine-readable category plus a human
    remediation hint. For plain Python errors raised inside a script,
    prefer the standard library exceptions (``ValueError``, ``FileNotFoundError``,
    etc.) — see ``general/03_interface/01_python-api/09_error-handling.md``.

    Parameters
    ----------
    message : str
        Human-readable description of the failure.
    code : ErrorCode, optional
        Machine-readable category. Defaults to ``ErrorCode.INTERNAL``.
    remediation : str, optional
        How to fix it (e.g. ``"pip install scitex-io[h5]"``).

    Examples
    --------
    >>> raise ScitexError(
    ...     "h5py not installed",
    ...     code=ErrorCode.DEPENDENCY,
    ...     remediation="pip install scitex-io[h5]",
    ... )
    """

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INTERNAL,
        remediation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = code
        self.remediation = remediation

    def to_dict(self) -> dict[str, str]:
        """Serialize to the structured shape consumed by MCP tools and `--json`."""
        out: dict[str, str] = {
            "code": self.error_code.value,
            "message": self.message,
        }
        if self.remediation:
            out["remediation"] = self.remediation
        return out

    def __str__(self) -> str:
        base = f"[{self.error_code.value}] {self.message}"
        if self.remediation:
            return f"{base} (remediation: {self.remediation})"
        return base


def classify_exception(exc: Exception) -> ErrorCode:
    """Classify an exception into an ErrorCode.

    Checks for a ``.error_code`` attribute first (SciTeXError convention),
    then falls back to built-in exception type mapping.
    """
    code = getattr(exc, "error_code", None)
    if code is not None:
        if isinstance(code, ErrorCode):
            return code
        if isinstance(code, str):
            try:
                return ErrorCode(code)
            except ValueError:
                pass

    for exc_type, error_code in _BUILTIN_ERROR_MAP.items():
        if isinstance(exc, exc_type):
            return error_code

    return ErrorCode.INTERNAL


# EOF
