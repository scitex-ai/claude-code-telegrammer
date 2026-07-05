#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/gate/_config.py
"""Load the ``gate`` section of ``.scitex/dev/config.yaml``.

The gate's SEVERITY model is config-driven (operator directive
2026-07-03): a check's failure is ADVISORY by default (warn, exit 0) and
only BLOCKS (exit 2) when the check id is listed under ``gate.enforce`` in
the project-root ``.scitex/dev/config.yaml`` — the same research-project
flags SSOT the linter's ``project-type`` escalation reads. This mirrors
that escalation model: warn-by-default, opt-in hard-enforce per check.

Schema::

    # .scitex/dev/config.yaml
    gate:
      enforce:            # check ids that HARD-BLOCK (exit 2) on failure
        - clew-source-reachability
        - dataset-submission-format
      disable:            # check ids skipped entirely
        - some-check
      # arbitrary extra keys are passed through to each check's run(config)

Resolution walks up from the workdir to the first ``.scitex/dev/config.yaml``
(same walk as ``linter._project_type``), so one repo has one SSOT. Missing
file / missing ``gate`` section ⇒ empty enforce+disable ⇒ everything
advisory (warn-default). Fail-open: a malformed file yields the empty
config rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_CONFIG_REL = Path(".scitex") / "dev" / "config.yaml"


@dataclass(frozen=True)
class GateConfig:
    """Resolved ``gate`` config for one workdir."""

    enforce: frozenset[str] = frozenset()
    disable: frozenset[str] = frozenset()
    raw: dict = field(default_factory=dict)
    source: str | None = None  # path of the config file, or None

    def is_enforced(self, check_id: str) -> bool:
        return check_id in self.enforce

    def is_disabled(self, check_id: str) -> bool:
        return check_id in self.disable


def _find_config_file(start_dir: Path) -> Path | None:
    current = start_dir.resolve()
    while True:
        candidate = current / _CONFIG_REL
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_gate_config(start_path: str | Path) -> GateConfig:
    """Resolve the ``gate`` config by walking up from ``start_path``.

    ``start_path`` may be a file or directory; the walk begins at its
    directory. Warn-default on any absence/parse error.
    """
    start = Path(start_path)
    start_dir = start if start.is_dir() else start.parent
    cfg_path = _find_config_file(start_dir)
    if cfg_path is None:
        return GateConfig()

    try:
        text = cfg_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return GateConfig()

    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(text) or {}
    except Exception:
        # No PyYAML or malformed YAML → warn-default (fail-open). A gate
        # that silently HARD-BLOCKED on an unreadable config would wedge
        # every submission; advisory-default is the safe degradation.
        return GateConfig(source=str(cfg_path))

    gate = data.get("gate") if isinstance(data, dict) else None
    if not isinstance(gate, dict):
        return GateConfig(source=str(cfg_path))

    enforce = frozenset(_as_str_list(gate.get("enforce")))
    disable = frozenset(_as_str_list(gate.get("disable")))
    return GateConfig(enforce=enforce, disable=disable, raw=gate, source=str(cfg_path))


def _as_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []


__all__ = ["GateConfig", "load_gate_config"]
