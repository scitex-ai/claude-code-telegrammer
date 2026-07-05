"""Per-section rule checks for the Python API auditor.

Split out of `_audit.py` to stay under the 512-line file hook (mirrors the
`_project/_check_*.py` and `_django/_checks.py` splits). The engine
(`audit_api`) lives in `_audit.py` and stays thin; each cohesive
responsibility (init-surface, umbrella, playwright, no-mocks, test-quality)
lives in its own module here. The rule registry (`Rule`/`RULES`), the
`Violation` dataclass, and the shared heuristic constants live in `_model`
so both these checks and the `_audit` orchestrator import them without an
import cycle.

`_audit` re-exports every public name below for backward compatibility, so
`from ..._audit import _audit_init, _audit_no_mocks, _locate_init, …` all
keep resolving.
"""

from __future__ import annotations

from ._discovery import _import_name, _locate_init
from ._init_surface import _audit_init, _inspect_version_pattern
from ._model import (
    RULES,
    Rule,
    Violation,
    _MOCK_FIXTURE_PARAMS_AUDIT,
    _MOCK_MODULES_AUDIT,
    _MOCK_SYMBOLS_AUDIT,
    _STDLIB_SAFE_ROOTS,
    _THIRD_PARTY_ROOTS,
)
from ._no_mocks import _audit_no_mocks
from ._playwright import _audit_playwright_capture, _type_checking_import_node_ids
from ._test_quality import _audit_test_quality
from ._umbrella import _audit_umbrella_imports

__all__ = [
    "RULES",
    "Rule",
    "Violation",
    "_import_name",
    "_locate_init",
    "_audit_init",
    "_inspect_version_pattern",
    "_audit_umbrella_imports",
    "_audit_playwright_capture",
    "_type_checking_import_node_ids",
    "_audit_no_mocks",
    "_audit_test_quality",
    "_THIRD_PARTY_ROOTS",
    "_STDLIB_SAFE_ROOTS",
    "_MOCK_MODULES_AUDIT",
    "_MOCK_SYMBOLS_AUDIT",
    "_MOCK_FIXTURE_PARAMS_AUDIT",
]
