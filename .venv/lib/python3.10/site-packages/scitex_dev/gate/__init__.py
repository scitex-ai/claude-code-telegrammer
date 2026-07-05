#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/gate/__init__.py
"""Submission-gate plugin federation for scitex-dev.

A capsule/submission GATE that aggregates per-package validation checks
as PLUGINS: leaves register a ``GateCheck`` provider under the
``scitex_dev.gate.checks`` entry-point group; scitex-dev owns the
contract, the aggregation, and the ``scitex-dev gate`` CLI, and stays
package-agnostic (each check locates + reads its own state given the
capsule workdir). Behaviour is configured by which packages are installed
plus a per-check ``enforce`` knob in ``.scitex/dev/config.yaml`` — the
pre-submission hook depends ONLY on scitex-dev.

See ``_skills/... submission-gate`` / the design doc for the full model.
"""

from __future__ import annotations

from ._config import GateConfig, load_gate_config
from ._discover import ENTRY_POINT_GROUP, discover_gate_checks
from ._run import CheckOutcome, GateReport, report_to_dict, run_gate
from ._spec import (
    SEVERITIES,
    STAGES,
    Finding,
    GateCheck,
    GateCheckProvider,
    GateResult,
)

__all__ = [
    "STAGES",
    "SEVERITIES",
    "Finding",
    "GateResult",
    "GateCheck",
    "GateCheckProvider",
    "ENTRY_POINT_GROUP",
    "discover_gate_checks",
    "GateConfig",
    "load_gate_config",
    "CheckOutcome",
    "GateReport",
    "run_gate",
    "report_to_dict",
]
