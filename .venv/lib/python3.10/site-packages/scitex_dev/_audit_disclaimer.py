#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: "2026-05-14 23:52:08 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-dev/src/scitex_dev/_audit_disclaimer.py


"""Sufficiency disclaimer printed at the end of every audit-* run.

Auditors check necessity (codified rules pass) but cannot judge
sufficiency (whether the package is genuinely well-organized,
documented, and useful). Surfacing this on every run keeps consumers
honest about the audit's limits.
"""

import os as _os

import click


def _skills_root() -> str:
    """Absolute path to scitex-dev's `_skills/` directory.

    Resolves via `scitex_dev.__file__` so the same hint works in an
    editable checkout (`<repo>/src/scitex_dev/_skills/`) and a
    pip-installed wheel (`<site-packages>/scitex_dev/_skills/`).
    """
    import scitex_dev as _m
    from pathlib import Path

    return str(Path(_m.__file__).parent / "_skills")


def _skill_hints_text() -> str:
    """Per-rule-prefix pointer into the two skill trees that scitex-dev
    carries.

    Two trees:
    - `_skills/general/`    — ecosystem-wide rules every package follows.
                              Audited by audit-cli / audit-mcp-tools /
                              audit-skills / audit-python-apis /
                              audit-project. This is what the rule
                              codes below map to.
    - `_skills/scitex-dev/` — scitex-dev's own user-facing skill leaves
                              (CLI reference, ecosystem helpers,
                              agentic-test, etc.). NOT audit rules;
                              read these to learn how to *use* the
                              tool, not to diagnose a violation.

    Kept as a flat block instead of per-rule URLs to avoid maintenance
    churn when the tree moves; the leaf filename is documented in each
    Rule's `section` token.
    """
    root = _skills_root()
    return (
        f"spec: rules live in `{root}/general/`:\n"
        f"  PS*  → 02_package/ (project structure, README, sphinx, RTD)\n"
        f"  §*   → 03_interface/02_cli/  (audit-cli) "
        f"or 03_interface/03_mcp/  (audit-mcp-tools)\n"
        f"  SK*  → 03_interface/04_skills/  (skill files)\n"
        f"  PA*  → 03_interface/01_python-api/  (Python API rules)\n"
        f"tool docs: `{root}/scitex-dev/` — how to use scitex-dev itself "
        f"(CLI reference, ecosystem helpers, agentic-test). Not audit rules.\n"
        f"escalation: think a rule fires wrongly, is too strict, or that "
        f"a missing rule should exist? Open an issue at "
        f"https://github.com/ywatanabe1989/scitex-dev/issues/new with "
        f"the violation block above pasted in — that's the feedback loop "
        f"the rule corpus learns from."
    )


def _scitex_dev_version() -> str:
    """Live scitex-dev version string for the auditor signature."""
    try:
        from importlib.metadata import version

        return version("scitex-dev")
    except Exception:
        return "unknown"


def _disclaimer_text() -> str:
    """Sufficiency disclaimer with the absolute path to `_skills/general/`,
    prefixed with the auditor's own version signature.

    Resolved at call time so the same string is correct under an
    editable checkout (`<repo>/src/scitex_dev/_skills/general/`) and a
    pip-installed wheel (`<site-packages>/scitex_dev/_skills/general/`).
    The signature line lets a CI failure be tied to a specific
    scitex-dev version when the rule corpus shifts between releases.
    """
    return (
        f"audited by scitex-dev v{_scitex_dev_version()}\n"
        "note: passing this audit is necessary but may not be sufficient for "
        f"SciTeX standards — see `{_skills_root()}/general/` for the "
        "full quality checklist (content accuracy, prose clarity, "
        "naming taste, etc.)."
    )


def emit_disclaimer() -> None:
    """Print the sufficiency disclaimer to stderr (suppress with SCITEX_DEV_NO_AUDIT_DISCLAIMER=1)."""
    if _os.environ.get("SCITEX_DEV_NO_AUDIT_DISCLAIMER"):
        return
    click.echo(_disclaimer_text(), err=True)


def emit_skill_hints() -> None:
    """Print the rule-prefix → skill-directory map. Suppressed by the
    same env flag as the disclaimer. Auditors call this only when
    violations were emitted, so a clean run stays quiet."""
    if _os.environ.get("SCITEX_DEV_NO_AUDIT_DISCLAIMER"):
        return
    click.echo(_skill_hints_text(), err=True)


# EOF
