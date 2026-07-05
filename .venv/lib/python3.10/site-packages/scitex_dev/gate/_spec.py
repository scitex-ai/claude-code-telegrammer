#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/gate/_spec.py
"""Frozen contract for the submission-gate plugin federation.

A ``GateCheck`` is one submission-stage validation a package contributes.
scitex-dev owns this contract + the aggregation + the CLI; each leaf owns
its RULE and reads its OWN state given the capsule workdir (scitex-dev
stays package-agnostic — it never imports scitex-clew / scitex-dataset).

Design (operator-directed, 2026-07-03; card cohort-A submission gate):
- STAGES: a check declares whether it runs ``pre-submission`` (the GATE —
  block a submit that lacks real provenance) or ``post-submission``
  (scoring-side; v1 leaves this seam open, scoring stays paper-side).
- ``run(workdir, config) -> GateResult``: the check locates its own state
  under ``workdir`` (clew → ``.scitex/clew/*.db``; dataset → the bound
  capsule's submission file) and returns pass/fail + findings. It must not
  need an API handle to the owning package from scitex-dev's side.
- ``Finding.fix_hint`` is the actionable string the pre-submission hook
  echoes to the solver on block ("wrap analysis in @stx.session …").
- ``severity`` is the check's INTRINSIC opinion; whether a failure BLOCKS
  (exit 2) is decided separately by the per-check ``enforce`` knob in
  ``.scitex/dev/config.yaml`` (warn-default), applied by ``run_gate`` —
  mirroring the linter's project-type severity-escalation model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

#: The submission stages a GateCheck may declare.
STAGES: tuple[str, ...] = ("pre-submission", "post-submission")

#: Severity levels a Finding may carry (the check's intrinsic opinion).
SEVERITIES: tuple[str, ...] = ("error", "warning", "info")


@dataclass(frozen=True)
class Finding:
    """One issue a GateCheck reports.

    Fields
    ------
    check_id
        The ``GateCheck.id`` that produced this finding.
    kind
        A short check-defined code (e.g. ``"runs_zero"``, ``"unsourced"``,
        ``"no_file"``) — stable enough for a hook to branch on.
    message
        Human-readable description of the issue.
    severity
        The check's intrinsic ``"error"|"warning"|"info"``. Whether it
        BLOCKS is decided by the gate's ``enforce`` config, not here.
    fix_hint
        The actionable remediation the pre-submission hook shows the
        solver (e.g. "wrap analysis in @stx.session, register claims to
        the run's output, then resubmit").
    """

    check_id: str
    kind: str
    message: str
    severity: str = "error"
    fix_hint: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(
                f"Finding.severity must be one of {SEVERITIES}; "
                f"got {self.severity!r}"
            )


@dataclass(frozen=True)
class GateResult:
    """A single GateCheck's verdict for one workdir.

    ``passed`` is the check's intrinsic pass/fail (e.g. dataset's
    ``validate_submission(...)["ok"]``, clew's runs>0 AND all-sourced).
    ``findings`` carry the context/fix_hints regardless of pass/fail.
    """

    passed: bool
    findings: tuple[Finding, ...] = ()


@dataclass(frozen=True)
class GateCheck:
    """One package-contributed submission check.

    Fields
    ------
    id
        Stable, unique check id (e.g. ``"clew-source-reachability"``,
        ``"dataset-submission-format"``). Config enable/disable/enforce
        key by this id. Duplicate ids across providers are dropped
        first-wins (like the jobs / system_deps federations).
    stage
        One of :data:`STAGES`.
    run
        ``(workdir: Path, config: Mapping) -> GateResult``. Receives the
        capsule workdir and the raw ``gate`` config section (so a check
        can read its own sub-keys); locates its own state under workdir.
    requires
        Optional import name of a package the check needs to RUN (beyond
        its own provider being installed). When absent/not-importable the
        check is SKIPPED with a notice — never a hard failure. Usually
        empty: a check registered via a package's entry point already
        implies that package is installed.
    description
        One-line human description for ``gate --list`` / docs.
    """

    id: str
    stage: str
    run: Callable[[Path, Mapping], GateResult]
    requires: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError(f"GateCheck.id must be a non-empty str; got {self.id!r}")
        if self.stage not in STAGES:
            raise ValueError(
                f"GateCheck({self.id!r}).stage must be one of {STAGES}; "
                f"got {self.stage!r}"
            )
        if not callable(self.run):
            raise ValueError(f"GateCheck({self.id!r}).run must be callable")


# Provider callable shape leaves register under the entry-point group.
GateCheckProvider = Callable[[], "list[GateCheck]"]

__all__ = [
    "STAGES",
    "SEVERITIES",
    "Finding",
    "GateResult",
    "GateCheck",
    "GateCheckProvider",
]
