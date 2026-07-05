"""PA-304 umbrella-import check for the Python API auditor.

Split out of `_audit.py` — pure refactor, no behaviour change. Flags
module-level `from scitex.X` / `import scitex.X` / `import scitex` inside
standalone source. Re-exported from `_audit` so existing imports keep
resolving.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._model import Violation


def _audit_umbrella_imports(
    init_path: Path, distribution: str, import_name: str
) -> list[Violation]:
    """PA-304 — flag `from scitex.X` / `import scitex.X` / `import scitex`
    inside standalone source.

    Only **module-level** imports are flagged. Function-scoped (lazy)
    imports don't drag the umbrella when the package is imported as a
    library — they fire only when the function is actually called.
    The PA-304 cost concern is module-import time, not call time.

    Exemptions:
    - The umbrella `scitex` package itself (its source legitimately
      references `scitex.<sub>`).
    - Function-scoped imports (`def f(): import scitex …`).
    - Class-method-scoped imports.
    - Imports inside `if __name__ == "__main__":` blocks (only run on
      direct module invocation).
    """
    out: list[Violation] = []
    if import_name == "scitex":
        return out
    pkg_root = init_path.parent

    def _is_dunder_main_if(node: ast.AST) -> bool:
        if not isinstance(node, ast.If):
            return False
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.comparators) != 1:
            return False
        if not isinstance(test.ops[0], ast.Eq):
            return False
        for a, b in (
            (test.left, test.comparators[0]),
            (test.comparators[0], test.left),
        ):
            if (
                isinstance(a, ast.Name)
                and a.id == "__name__"
                and isinstance(b, ast.Constant)
                and b.value == "__main__"
            ):
                return True
        return False

    def _is_umbrella_private(mod: str) -> bool:
        """`scitex._<name>[…]` — umbrella-private (no peer standalone)."""
        if not mod.startswith("scitex."):
            return False
        first = mod[len("scitex.") :].split(".", 1)[0]
        return first.startswith("_")

    def _flag(mod: str) -> bool:
        if mod == "scitex":
            return True
        if mod.startswith("scitex.") and not _is_umbrella_private(mod):
            return True
        return False

    def _scan_module_level(body: list[ast.stmt], py_file: Path) -> None:
        """Walk only top-level statements + control-flow descendants.
        Skip function and class bodies (lazy) and `if __name__ == ...`."""
        for stmt in body:
            if _is_dunder_main_if(stmt):
                continue
            # Recurse into module-level if/try/with — imports there ARE
            # eager. Skip Function/AsyncFunction/ClassDef bodies.
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(stmt, ast.ImportFrom):
                mod = stmt.module or ""
                if _flag(mod):
                    out.append(
                        Violation(
                            "PA-304",
                            f"{distribution}: {py_file.relative_to(pkg_root.parent)}:{stmt.lineno}",
                            f"from {mod} import ... — replace with peer standalone import",
                        )
                    )
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    name = alias.name
                    if _flag(name):
                        out.append(
                            Violation(
                                "PA-304",
                                f"{distribution}: {py_file.relative_to(pkg_root.parent)}:{stmt.lineno}",
                                f"import {name} — replace with peer standalone import",
                            )
                        )
            elif isinstance(stmt, (ast.If, ast.Try, ast.With, ast.AsyncWith)):
                # Module-level if/try/with — descend into bodies.
                children: list[ast.stmt] = []
                children.extend(getattr(stmt, "body", []) or [])
                children.extend(getattr(stmt, "orelse", []) or [])
                children.extend(getattr(stmt, "finalbody", []) or [])
                for h in getattr(stmt, "handlers", []) or []:
                    children.extend(getattr(h, "body", []) or [])
                _scan_module_level(children, py_file)

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
                # Tutorial/demo subpackages — `import scitex` is the
                # canonical end-user idiom, not a library-cost concern.
                "examples",
                "docs",
            )
        ):
            continue
        # Filename pattern for in-tree demos (e.g. scitex-stats's
        # tests/categorical/_demo_chi2.py). Same exemption as `examples/`
        # — these are runnable demonstrations of the API surface, not
        # library code that consumers import.
        if py_file.name.startswith("_demo_") or py_file.name.startswith("demo_"):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(text, filename=str(py_file))
        except SyntaxError:
            continue
        if isinstance(tree, ast.Module):
            _scan_module_level(tree.body, py_file)
    return out


__all__ = ["_audit_umbrella_imports"]
