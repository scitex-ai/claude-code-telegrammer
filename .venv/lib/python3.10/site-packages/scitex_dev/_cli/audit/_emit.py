"""Shared logging-emit helper for every `scitex-dev ecosystem audit-*` command.

The auditor headlines (`ok` / `warn` / `error` / `info` / `skip`) need to
be color-aware AND severity-aware so CI can grep the level prefix and
humans can scan the colored output. Both come from scitex-logging.

Falls back to `click.echo` with the legacy plain-text headline prefix
when scitex-logging is unavailable, so the auditor is still functional
in pristine venvs that haven't installed the dep yet.
"""

from __future__ import annotations

import click

try:
    import scitex_logging as _stx_log

    _logger = _stx_log.getLogger("scitex_dev.audit")
except ImportError:  # pragma: no cover — scitex-logging is a hard runtime dep
    _logger = None


_LEGACY_PREFIX = {
    "info": "info",
    "warning": "warn",
    "error": "error",
    "success": "ok",
    "skip": "skip",
}


def emit(level: str, text: str, *, err: bool = False) -> None:
    """Emit `text` at `level` through scitex-logging when available.

    Parameters
    ----------
    level
        One of ``info`` / ``warning`` / ``error`` / ``success`` / ``skip``.
        ``skip`` falls through to ``info`` at the logging layer; the
        legacy prefix path keeps the `skip ` headline for grep parity.
    text
        Message body. The level prefix is added automatically.
    err
        Route to stderr in the fallback path. Ignored by the
        scitex-logging path (which honours the logger's own stream
        configuration).
    """
    if _logger is not None:
        fn = {
            "info": _logger.info,
            "warning": _logger.warning,
            "error": _logger.error,
            "success": _logger.success,
            "skip": _logger.info,
        }.get(level, _logger.info)
        fn(text)
        return
    prefix = _LEGACY_PREFIX.get(level, "info")
    click.echo(f"{prefix}  {text}", err=err)
