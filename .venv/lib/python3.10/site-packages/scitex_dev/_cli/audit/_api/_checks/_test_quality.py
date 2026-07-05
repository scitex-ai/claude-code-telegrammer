"""PA-307 test-quality check for the Python API auditor.

Split out of `_audit.py` — pure refactor, no behaviour change. Re-runs the
linter's STX-TQ001-007 detection across the repo's `tests/` tree (and every
`conftest.py`) and re-emits each finding as a PA-307 violation. Re-exported
from `_audit` so existing imports keep resolving.
"""

from __future__ import annotations

from pathlib import Path

from ._model import Violation


def _audit_test_quality(
    init_path: Path, distribution: str, import_name: str
) -> list[Violation]:
    """PA-307 — run the linter's STX-TQ001-007 detection across the
    repo's `tests/` (and `conftest.py`) and re-emit each finding as a
    PA-307 violation. Avoids duplicating the AST detection logic that
    already lives in `scitex_dev.linter.checker`.
    """
    out: list[Violation] = []
    pkg_root = init_path.parent  # <repo>/src/<pkg>/
    src_parent = pkg_root.parent
    repo_root = src_parent.parent if src_parent.name == "src" else src_parent

    # Scope: tests/ tree (recursively, all *.py) + every conftest.py
    # under the repo. Fixtures often live in conftest.py and TQ004/TQ005
    # apply to them.
    tests_dir = repo_root / "tests"
    candidates: list[Path] = []
    if tests_dir.is_dir():
        candidates.extend(sorted(tests_dir.rglob("*.py")))
    for conftest in repo_root.rglob("conftest.py"):
        # Skip site-packages and venvs.
        parts = conftest.parts
        if any(
            seg in parts
            for seg in (
                "__pycache__",
                "build",
                "dist",
                ".tox",
                "site-packages",
                ".venv",
                "venv",
            )
        ):
            continue
        if conftest not in candidates:
            candidates.append(conftest)

    if not candidates:
        return out

    # Re-use the linter's detection rather than duplicate the AST logic.
    try:
        from scitex_dev.linter.checker import lint_file
    except ImportError:
        return out

    rel_anchor = repo_root
    for py_file in candidates:
        parts = py_file.parts
        if any(
            seg in parts
            for seg in (
                "__pycache__",
                "build",
                "dist",
                ".tox",
                "site-packages",
                ".venv",
                "venv",
            )
        ):
            continue
        try:
            issues = lint_file(str(py_file))
        except Exception:
            continue
        for issue in issues:
            rule_id = getattr(issue.rule, "id", "") or ""
            if not rule_id.startswith("STX-TQ"):
                continue
            try:
                rel = py_file.relative_to(rel_anchor)
            except ValueError:
                rel = py_file
            out.append(
                Violation(
                    "PA-307",
                    f"{distribution}: {rel}:{issue.line}",
                    f"{rule_id}: {issue.rule.message[:160]}",
                )
            )
    return out


__all__ = ["_audit_test_quality"]
