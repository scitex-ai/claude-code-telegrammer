"""Pytest helpers for downstream SciTeX packages.

Public re-exports:
- `audit_all_for_package` — assert `audit-all <pkg>` exits 0.

Each ecosystem package drops a one-liner test that calls this helper
so the package's local pytest run includes the same audit gates that
CI used to run as a separate workflow. See the auto-generated
`tests/test_audit.py` template (via
`scitex-dev ecosystem write-audit-test <pkg>`) and the skill leaf
`_skills/general/02_package/07_github-actions.md` for the canonical
shape.
"""

from __future__ import annotations

from ._audit_conformance import audit_all_for_package

__all__ = ["audit_all_for_package"]
