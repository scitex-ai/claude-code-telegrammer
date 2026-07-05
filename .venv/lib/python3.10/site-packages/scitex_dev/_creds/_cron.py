#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crontab installer for the ecosystem-wide credentials rotation.

Manages a single crontab line tagged with the marker comment
``# scitex-dev creds-rotate (managed)`` so reinstall is idempotent —
the line is replaced in place rather than appended.

Public API
----------
- ``MARKER``            — sentinel comment that identifies our line
- ``LOG_PATH``          — default log destination
- ``build_cron_line``   — pure builder (used by tests + install)
- ``read_crontab``      — current user's crontab as text (``""`` if none)
- ``write_crontab``     — replace the entire crontab from text
- ``install``           — idempotent install with a given interval
- ``uninstall``         — remove any line tagged with ``MARKER``
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

MARKER = "# scitex-dev creds-rotate (managed)"
LOG_PATH = Path.home() / ".scitex" / "dev" / "logs" / "creds-rotate.log"
_LOG_ROTATE_BYTES = 1_048_576  # 1 MiB — rotate via `mv` to .1 on overflow


def _interval_to_schedule(interval_minutes: int) -> str:
    """Map an interval in minutes onto a 5-field cron schedule.

    For 60 (the default) we emit ``0 * * * *`` rather than ``*/60 * * * *``
    so the output matches what an operator would write by hand.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    if interval_minutes == 60:
        return "0 * * * *"
    if interval_minutes < 60 and 60 % interval_minutes == 0:
        return f"*/{interval_minutes} * * * *"
    if interval_minutes % 60 == 0:
        hours = interval_minutes // 60
        if hours == 1:
            return "0 * * * *"
        if 24 % hours == 0:
            return f"0 */{hours} * * *"
    # Fallback: best-effort minute slot.
    return f"*/{min(interval_minutes, 59)} * * * *"


def _resolve_cli() -> str:
    """Locate the ``scitex-dev`` console script for the cron line."""
    found = shutil.which("scitex-dev")
    if found:
        return found
    # Best-effort fallback: invoke via the current interpreter so the
    # cron line still works when shutil.which fails (PATH stripped).
    return f"{sys.executable} -m scitex_dev"


def build_cron_line(
    interval_minutes: int = 60,
    *,
    log_path: Path = LOG_PATH,
    cli_path: str | None = None,
) -> str:
    """Build the single managed crontab line."""
    schedule = _interval_to_schedule(interval_minutes)
    exe = cli_path or _resolve_cli()
    log = str(log_path)
    # Size-based rotation: when log grows past 1 MiB, move to .1 then
    # re-open. Keep the shell-fu inline — one cron line, no helper script.
    rotate = (
        f'[ -f {log} ] && [ "$(stat -c%s {log} 2>/dev/null || echo 0)" '
        f"-gt {_LOG_ROTATE_BYTES} ] && mv {log} {log}.1; "
    )
    body = (
        f"mkdir -p $(dirname {log}); {rotate}{exe} creds rotate-all --yes >> {log} 2>&1"
    )
    return f"{schedule} {body} {MARKER}"


def read_crontab() -> str:
    """Return the current user's crontab, or ``\"\"`` if none."""
    try:
        r = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("'crontab' not found on PATH") from exc
    if r.returncode != 0:
        # crontab -l returns 1 on "no crontab for $USER" — that's empty,
        # not an error from our perspective.
        return ""
    return r.stdout


def write_crontab(content: str) -> None:
    """Replace the current user's crontab with ``content``."""
    try:
        r = subprocess.run(
            ["crontab", "-"],
            input=content,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("'crontab' not found on PATH") from exc
    if r.returncode != 0:
        raise RuntimeError(
            f"crontab write failed: {r.stderr.strip() or r.stdout.strip()}"
        )


def _strip_managed(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if MARKER not in line)


def install(
    interval_minutes: int = 60,
    *,
    dry_run: bool = False,
    log_path: Path = LOG_PATH,
    cli_path: str | None = None,
    read_fn=None,
    write_fn=None,
) -> str:
    """Idempotently install / replace the managed crontab line.

    Returns the line that was (or would be) installed.

    ``read_fn`` / ``write_fn`` are test-injection seams (default to the
    module-level ``read_crontab`` / ``write_crontab`` which shell out to
    ``crontab(1)``).
    """
    if read_fn is None:
        read_fn = read_crontab
    if write_fn is None:
        write_fn = write_crontab
    line = build_cron_line(interval_minutes, log_path=log_path, cli_path=cli_path)
    if dry_run:
        return line

    current = read_fn()
    stripped = _strip_managed(current).rstrip()
    if stripped:
        new_content = stripped + "\n" + line + "\n"
    else:
        new_content = line + "\n"
    write_fn(new_content)
    # Ensure the log dir exists eagerly so the first cron invocation
    # doesn't lose any output to a missing parent.
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return line


def uninstall(*, dry_run: bool = False, read_fn=None, write_fn=None) -> int:
    """Remove every managed line. Returns the number removed."""
    if read_fn is None:
        read_fn = read_crontab
    if write_fn is None:
        write_fn = write_crontab
    current = read_fn()
    before = current.splitlines()
    removed = sum(1 for line in before if MARKER in line)
    if dry_run or removed == 0:
        return removed
    stripped = _strip_managed(current).rstrip()
    new_content = (stripped + "\n") if stripped else ""
    write_fn(new_content)
    return removed


# EOF
