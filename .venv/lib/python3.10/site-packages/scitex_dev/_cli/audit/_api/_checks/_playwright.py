"""PA-305 Playwright debug-capture check for the Python API auditor.

Split out of `_audit.py` — pure refactor, no behaviour change. Flags modules
that import `playwright.async_api` (live browser automation) without any
`capture_debug_artifacts_async` call. Re-exported from `_audit` so existing
imports (`from ..._audit import _audit_playwright_capture`) keep resolving.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._model import Violation


def _type_checking_import_node_ids(tree: ast.AST) -> set[int]:
    """Return id()s of Import/ImportFrom nodes that live *only* inside an
    ``if TYPE_CHECKING:`` guard.

    Such imports are type-only — they are never executed at runtime, so a
    ``playwright.async_api`` import guarded this way is a type annotation
    (e.g. ``page: Page``), not live browser automation. PA-305 must not
    flag them; otherwise pure-logic modules that merely *type* a handed-in
    ``Page`` (Zotero-style translators, parsers) trip the rule despite
    never opening a browser.
    """
    out: set[int] = set()

    def _is_type_checking_test(test: ast.expr) -> bool:
        # `if TYPE_CHECKING:` or `if typing.TYPE_CHECKING:`
        if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
            return True
        if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
            return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_test(node.test):
            # Only the `if` body is type-only; an `else:` branch runs at
            # runtime, so its imports are not exempt.
            for child in node.body:
                for sub in ast.walk(child):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        out.add(id(sub))
    return out


def _audit_playwright_capture(
    init_path: Path, distribution: str, import_name: str
) -> list[Violation]:
    """PA-305 — every module that imports `playwright.async_api` (a sign
    of live browser automation) must contain at least one
    `capture_debug_artifacts_async` call. Helper-routed callers can opt
    in via `from scitex_browser.debugging import capture_debug_artifacts_async`
    (presence-only check; semantics not enforced).

    Imports guarded by ``if TYPE_CHECKING:`` are ignored — they are
    type-only (``page: Page`` annotations) and never drive a browser, so
    they are not a sign of live automation.

    The auditor doesn't check call frequency or coverage — just
    presence-or-absence. Reviewers should still apply the stepwise
    rule from `02_package/09_browser-automation-debugging.md`.
    """
    out: list[Violation] = []
    # The rule applies to packages that USE playwright in production. We
    # exempt scitex-browser itself (it's the home of the helper and may
    # have helper-implementation modules without consumer-style calls).
    if import_name == "scitex_browser":
        return out
    pkg_root = init_path.parent
    for py_file in sorted(pkg_root.rglob("*.py")):
        parts = py_file.parts
        if any(
            seg in parts
            for seg in (
                "__pycache__",
                "build",
                "dist",
                ".tox",
                "site-packages",
                "tests",
                "examples",
                "docs",
            )
        ):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        # Cheap pre-check: skip files that don't even mention playwright.
        if "playwright" not in text:
            continue
        try:
            tree = ast.parse(text, filename=str(py_file))
        except SyntaxError:
            continue
        # Imports under `if TYPE_CHECKING:` are type-only — exempt them so a
        # `page: Page` annotation does not masquerade as live automation.
        type_only_ids = _type_checking_import_node_ids(tree)
        imports_playwright = False
        calls_capture = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if (
                    mod == "playwright.async_api"
                    or mod.startswith("playwright.async_api.")
                ) and id(node) not in type_only_ids:
                    imports_playwright = True
            elif isinstance(node, ast.Import):
                if id(node) in type_only_ids:
                    continue
                for alias in node.names:
                    if alias.name == "playwright.async_api" or alias.name.startswith(
                        "playwright.async_api."
                    ):
                        imports_playwright = True
            # Calls — both bare `capture_debug_artifacts_async(...)` and
            # `something.capture_debug_artifacts_async(...)` (e.g. via
            # an instance method that delegates).
            elif isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id == "capture_debug_artifacts_async":
                    calls_capture = True
                elif (
                    isinstance(f, ast.Attribute)
                    and f.attr == "capture_debug_artifacts_async"
                ):
                    calls_capture = True
        if imports_playwright and not calls_capture:
            out.append(
                Violation(
                    "PA-305",
                    f"{distribution}: {py_file.relative_to(pkg_root.parent)}",
                    "imports `playwright.async_api` but no "
                    "`capture_debug_artifacts_async` call in module",
                )
            )
    return out


__all__ = ["_type_checking_import_node_ids", "_audit_playwright_capture"]
