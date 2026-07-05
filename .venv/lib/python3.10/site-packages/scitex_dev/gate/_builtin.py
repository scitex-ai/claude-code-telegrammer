#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/gate/_builtin.py
"""scitex-dev's own built-in GateCheck(s).

Ships a single trivial pre-submission check — ``gate-workdir-present`` —
so the cohort's pre/post-submission hooks can wire and test
``scitex-dev gate --stage=pre-submission <workdir>`` end-to-end BEFORE
scitex-clew's source-reachability and scitex-dataset's format checks
register (paper-scitex-clew explicitly asked for this skeleton).

Registered via an INTERNAL provider (always merged by
``discover_gate_checks``), not an entry point — so scitex-dev never
double-counts its own built-in and it is always available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ._spec import Finding, GateCheck, GateResult


def _workdir_present(workdir: Path, config: Mapping) -> GateResult:
    """Pass iff ``workdir`` exists and is a directory.

    Deliberately minimal — it validates the HOOK WIRING (a real capsule
    workdir was passed) rather than any package's provenance. Its value
    is being installable-free: it lets the hook be built and exercised
    while the real package checks are still in flight.
    """
    p = Path(workdir)
    if p.is_dir():
        return GateResult(passed=True)
    return GateResult(
        passed=False,
        findings=(
            Finding(
                check_id="gate-workdir-present",
                kind="no_workdir",
                message=f"submission workdir does not exist or is not a directory: {p}",
                severity="error",
                fix_hint=(
                    "pass an existing capsule workdir to "
                    "`scitex-dev gate --stage=pre-submission <workdir>`"
                ),
            ),
        ),
    )


BUILTIN_CHECKS: tuple[GateCheck, ...] = (
    GateCheck(
        id="gate-workdir-present",
        stage="pre-submission",
        run=_workdir_present,
        requires="",
        description=(
            "scitex-dev built-in: the submission workdir exists "
            "(validates hook wiring before package checks land)."
        ),
    ),
)


def provide() -> list[GateCheck]:
    """Internal provider — scitex-dev's own built-in gate checks."""
    return list(BUILTIN_CHECKS)


__all__ = ["BUILTIN_CHECKS", "provide"]
