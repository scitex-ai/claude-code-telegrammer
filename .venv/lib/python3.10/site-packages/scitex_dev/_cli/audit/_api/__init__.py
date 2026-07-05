"""Python API auditor — checks a SciTeX package's `__init__.py` against the
`general/03_interface/01_python-api/12_audit-checklist.md` rules.

Foundation scope: static AST + import-time probe of the `(A)` automated rules
across §1 (naming/visibility), §2 (version), §3 (lazy imports), §5 (type hints).
Behavioral probes (`<cli> list-python-apis --json`) and docstring-grammar
checks (§4) are deferred to follow-ups.

Resolution order for the package under audit:
    1. `--package` / positional argument names the *distribution* (e.g. `scitex-io`).
    2. We resolve the *import name* by replacing `-` with `_` (canonical SciTeX).
    3. We probe `__init__.py` source via `importlib.util.find_spec` (no execution
       beyond what `import <pkg>` triggers — same risk profile as `audit-cli`).
"""

from __future__ import annotations

__all__ = ["audit_api", "Violation", "RULES"]

from ._audit import RULES, Violation, audit_api
