#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Idempotent BEGIN/END managed-block crontab editing for ecosystem jobs.

The legacy ``scitex-dev cron`` CLI manages *individual* lines tagged
``# scitex-dev cron: <name>`` (see ``_cli/cron/_crontab.py``). The
federated ``ecosystem cron`` surface instead manages a single contiguous
*block* delimited by sentinel comments::

    # >>> scitex-dev-ecosystem (managed; do not edit) >>>
    <schedule> <command>   # scitex-dev-ecosystem: <name>
    ...
    # <<< scitex-dev-ecosystem <<<

Re-running ``install`` replaces the whole block in place, so jobs are
never duplicated. Lines outside the block are preserved verbatim.

Crontab read/write reuses the well-tested helpers from
``_cli.cron._crontab`` (``read_crontab`` / ``write_crontab``), keeping a
single subprocess path.
"""

from __future__ import annotations

from .. import jobs as _jobs

BLOCK_BEGIN = "# >>> scitex-dev-ecosystem (managed; do not edit) >>>"
BLOCK_END = "# <<< scitex-dev-ecosystem <<<"
LINE_MARKER_PREFIX = "# scitex-dev-ecosystem: "


def _line_marker(name: str) -> str:
    return f"{LINE_MARKER_PREFIX}{name}"


def build_cron_line(job: _jobs.JobSpec) -> str:
    """Build one managed crontab line for a cron-kind ``job``."""
    if "\n" in job.command:
        raise ValueError("cron command must not contain newlines")
    return f"{job.schedule} {job.command} {_line_marker(job.name)}"


def render_block(jobs: list[_jobs.JobSpec]) -> str:
    """Render the full BEGIN..END managed block for ``jobs`` (no trailing NL)."""
    lines = [BLOCK_BEGIN]
    for job in jobs:
        lines.append(build_cron_line(job))
    lines.append(BLOCK_END)
    return "\n".join(lines)


def strip_block(text: str) -> str:
    """Return ``text`` with any existing managed block removed.

    Tolerant of a missing END marker (strips to end of file) so a
    truncated/half-written block can still be cleaned up.
    """
    out: list[str] = []
    in_block = False
    for line in text.splitlines():
        if line.strip() == BLOCK_BEGIN:
            in_block = True
            continue
        if in_block:
            if line.strip() == BLOCK_END:
                in_block = False
            continue
        out.append(line)
    new = "\n".join(out).rstrip("\n")
    return new


def upsert_block(text: str, jobs: list[_jobs.JobSpec]) -> str:
    """Return ``text`` with the managed block replaced/appended.

    Idempotent: an existing block is stripped first, so re-running with
    the same ``jobs`` yields identical output (no duplicate lines).
    Passing an empty ``jobs`` list removes the block entirely.
    """
    base = strip_block(text)
    if not jobs:
        return (base + "\n") if base else ""
    block = render_block(jobs)
    if base:
        return base + "\n" + block + "\n"
    return block + "\n"


def remove_line(text: str, name: str) -> tuple[str, int]:
    """Remove a single managed line by ``name`` from within the block.

    Returns ``(new_text, removed_count)``. If removing the line empties
    the block, the BEGIN/END markers are dropped too.
    """
    marker = _line_marker(name)
    kept: list[str] = []
    removed = 0
    for line in text.splitlines():
        if marker in line and line.strip() != BLOCK_BEGIN:
            removed += 1
            continue
        kept.append(line)
    new = "\n".join(kept)
    # If the block is now empty (BEGIN immediately followed by END),
    # collapse the markers away.
    new = _drop_empty_block(new)
    if text.endswith("\n") and new:
        new += "\n"
    return new, removed


def _drop_empty_block(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if (
            lines[i].strip() == BLOCK_BEGIN
            and i + 1 < len(lines)
            and lines[i + 1].strip() == BLOCK_END
        ):
            i += 2
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out).rstrip("\n")


# EOF
