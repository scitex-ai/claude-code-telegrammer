#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure JobSpec helpers: ``kind="timer"`` → ``kind="cron"`` translation.

Extracted from ``_up.py`` to keep the orchestrator under the line-cap
and to let the (pure) translation logic be unit-tested without booting
the rest of the up flow.

The federated ``_cron_block.upsert_block`` helper only understands
``kind="cron"`` JobSpecs (5-field cron expressions). Per the supervisor
redesign (operator policy 2026-06-14), ``kind="timer"`` jobs no longer
lower to systemd timer units — they lower to cron lines instead. This
module is the translator. Each timer JobSpec becomes a synthetic
``kind="cron"`` JobSpec whose ``schedule`` is the best-effort cron
expression derived from the timer's ``on_unit_active_sec`` / ``schedule``.
"""

from __future__ import annotations

from ....jobs import JobSpec


def timer_to_cron_jobspec(job: JobSpec) -> JobSpec:
    """Lower a ``kind="timer"`` JobSpec to a synthetic ``kind="cron"`` one.

    Translation rules (first match wins):

    * ``job.schedule`` already a 5-field cron expression → preserved.
    * ``on_unit_active_sec`` ``"<N>min"`` → ``"*/N * * * *"`` (1≤N≤59).
    * ``on_unit_active_sec`` ``"<N>h"``   → ``"0 */N * * *"`` (1≤N≤23).
    * ``on_unit_active_sec`` ``"<N>d"``   → ``"0 0 */N * *"`` (1≤N≤30).
    * Anything else → ``"0 * * * *"`` (hourly fallback).

    The returned JobSpec carries ``kind="cron"`` so it lands cleanly
    in :func:`scitex_dev.jobs._cron_block.upsert_block`. ``description``
    is preserved so ``crontab -l`` stays legible.
    """
    return JobSpec(
        name=job.name,
        kind="cron",
        schedule=derive_cron_expr(job),
        command=job.command,
        description=job.description,
    )


def derive_cron_expr(job: JobSpec) -> str:
    """Inner cron-expression derivation. Pure — no I/O."""
    fields = job.schedule.split()
    if len(fields) == 5:
        return job.schedule

    cad = (job.on_unit_active_sec or "").strip().lower()
    if cad.endswith("min"):
        n = _safe_int(cad[:-3])
        if n and 1 <= n <= 59:
            return f"*/{n} * * * *"
    if cad.endswith("h"):
        n = _safe_int(cad[:-1])
        if n and 1 <= n <= 23:
            return f"0 */{n} * * *"
    if cad.endswith("d"):
        n = _safe_int(cad[:-1])
        if n and 1 <= n <= 30:
            return f"0 0 */{n} * *"
    # Hourly fallback catches "the leaf forgot to set a cadence" without
    # busy-spinning. Operators prefer a noisy-but-bounded job over a
    # silently-dropped one.
    return "0 * * * *"


def _safe_int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


def collect_cron_jobs(
    jobs: list[JobSpec],
) -> tuple[list[JobSpec], int, int]:
    """Return ``(merged, cron_native_count, timer_lowered_count)``.

    The merged list is what gets handed to
    :func:`scitex_dev.jobs._cron_block.upsert_block` — one block,
    mixed cron-native + lowered-timer entries. The counts come back
    so the orchestrator's summary line is honest about WHERE each
    cron entry came from.
    """
    cron_native = [j for j in jobs if j.kind == "cron"]
    timer_jobs = [j for j in jobs if j.kind == "timer"]
    lowered = [timer_to_cron_jobspec(t) for t in timer_jobs]
    return cron_native + lowered, len(cron_native), len(lowered)


__all__ = [
    "collect_cron_jobs",
    "derive_cron_expr",
    "timer_to_cron_jobspec",
]


# EOF
