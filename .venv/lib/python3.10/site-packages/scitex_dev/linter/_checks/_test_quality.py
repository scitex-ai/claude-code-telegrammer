"""Test-quality (TQ) helper methods for SciTeXChecker.

Pure detection helpers used by ``SciTeXChecker.visit_FunctionDef`` to emit
the TQ001-TQ007 rules. Kept as a mixin so the orchestrator stays small.
"""

from __future__ import annotations

import ast
from pathlib import Path


class TestQualityMixin:
    """TQ detection helpers. Expects host ``filepath`` / ``source_lines``."""

    # Names that count as a "real" pytest-style assertion construct.
    _TQ001_PYTEST_ASSERT_ATTRS = frozenset(
        {"raises", "warns", "fail", "deprecated_call", "skip", "xfail"}
    )

    # State-mutation method names that flag a session/module-scope fixture.
    _TQ004_MUTATION_ATTRS = frozenset(
        {
            "insert",
            "write",
            "write_text",
            "write_bytes",
            "writelines",
            "append",
            "update",
            "set",
            "save",
            "delete",
            "remove",
            "unlink",
            "mkdir",
            "rmdir",
            "touch",
        }
    )

    # Resource-acquisition call names that flag a `return`-not-`yield` fixture.
    _TQ005_RESOURCE_NAMES = frozenset(
        {"open", "connect", "urlopen", "socket", "Session", "TemporaryFile"}
    )

    def _tq001_is_test_file(self) -> bool:
        """True iff the current file looks like a pytest test file."""
        parts = Path(self.filepath).parts
        name = Path(self.filepath).name
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or any(seg in {"tests", "test"} for seg in parts)
        )

    @classmethod
    def _tq_is_pytest_fixture(cls, node) -> tuple[bool, str | None]:
        """Return (is_fixture, scope) for a function."""
        for deco in node.decorator_list:
            # @pytest.fixture (bare)
            if (
                isinstance(deco, ast.Attribute)
                and deco.attr == "fixture"
                and isinstance(deco.value, ast.Name)
                and deco.value.id == "pytest"
            ):
                return True, "function"
            # @fixture (bare, after `from pytest import fixture`)
            if isinstance(deco, ast.Name) and deco.id == "fixture":
                return True, "function"
            # @pytest.fixture(scope="session", ...) or @fixture(...)
            if isinstance(deco, ast.Call):
                f = deco.func
                is_pytest_fixture = (
                    isinstance(f, ast.Attribute)
                    and f.attr == "fixture"
                    and isinstance(f.value, ast.Name)
                    and f.value.id == "pytest"
                ) or (isinstance(f, ast.Name) and f.id == "fixture")
                if is_pytest_fixture:
                    scope = "function"
                    for kw in deco.keywords:
                        if kw.arg == "scope" and isinstance(kw.value, ast.Constant):
                            scope = str(kw.value.value)
                    return True, scope
        return False, None

    @staticmethod
    def _tq_has_parametrize(node) -> bool:
        """True iff the function is decorated with a `parametrize` form."""
        for deco in node.decorator_list:
            f = deco.func if isinstance(deco, ast.Call) else deco
            if isinstance(f, ast.Attribute) and f.attr == "parametrize":
                # @pytest.mark.parametrize  (Attribute on Attribute)
                if isinstance(f.value, ast.Attribute) and f.value.attr == "mark":
                    return True
                # @mark.parametrize  (Attribute on Name "mark")
                if isinstance(f.value, ast.Name) and f.value.id == "mark":
                    return True
            # @parametrize  (bare Name)
            if isinstance(f, ast.Name) and f.id == "parametrize":
                return True
        return False

    @classmethod
    def _tq004_body_mutates_state(cls, node) -> bool:
        """True iff the function body contains a state-mutation call."""
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            f = sub.func
            if isinstance(f, ast.Attribute) and f.attr in cls._TQ004_MUTATION_ATTRS:
                return True
            # `open(path, "w")` / `open(path, "a")`
            if (
                isinstance(f, ast.Name)
                and f.id == "open"
                and len(sub.args) >= 2
                and isinstance(sub.args[1], ast.Constant)
                and isinstance(sub.args[1].value, str)
                and any(m in sub.args[1].value for m in ("w", "a", "x", "+"))
            ):
                return True
        return False

    @classmethod
    def _tq005_acquires_resource(cls, node) -> bool:
        """True iff the body has a call to a resource-acquiring constructor."""
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            f = sub.func
            if isinstance(f, ast.Name) and f.id in cls._TQ005_RESOURCE_NAMES:
                return True
            if isinstance(f, ast.Attribute) and f.attr in cls._TQ005_RESOURCE_NAMES:
                return True
        return False

    @staticmethod
    def _tq005_returns_not_yields(node) -> bool:
        """True iff the body has a top-level `return <expr>` AND no `yield`."""
        has_yield = False
        has_return_value = False
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Yield, ast.YieldFrom)):
                has_yield = True
                break
            if isinstance(sub, ast.Return) and sub.value is not None:
                has_return_value = True
        return has_return_value and not has_yield

    @staticmethod
    def _tq006_body_has_toplevel_if(node) -> bool:
        """True iff the function body has an `if` at the top level."""
        for stmt in node.body:
            if isinstance(stmt, ast.If):
                return True
        return False

    @staticmethod
    def _tq003_name_word_count(name: str) -> int:
        """Count the word-tokens after the `test_` prefix."""
        if not name.startswith("test_"):
            return -1
        rest = name[len("test_") :]
        tokens = [t for t in rest.split("_") if t]
        return len(tokens)

    def _tq002_missing_aaa_markers(self, node) -> str:
        """Return a short reason string if the test body is missing AAA
        marker comments (`# Arrange`, `# Act`, `# Assert`) in order, else ''."""
        start = node.lineno  # 1-indexed
        end = getattr(node, "end_lineno", None) or len(self.source_lines)
        body = self.source_lines[start:end]
        seen = {"arrange": -1, "act": -1, "assert": -1}
        for i, raw in enumerate(body):
            text = raw.strip()
            if not text.startswith("#"):
                continue
            comment = text.lstrip("#").strip().lower()
            for kw in seen:
                if seen[kw] != -1:
                    continue
                if (
                    comment == kw
                    or comment.startswith(kw + ":")
                    or comment.startswith(kw + " ")
                ):
                    seen[kw] = i
                    break
        missing = [k.capitalize() for k, v in seen.items() if v == -1]
        if missing:
            return "missing " + "/".join(missing) + " marker"
        a, b, c = seen["arrange"], seen["act"], seen["assert"]
        if not (a < b < c):
            return "AAA markers are out of order"
        return ""

    @classmethod
    def _tq007_count_assertions(cls, node) -> int:
        """Count assertions in a function body."""
        count = 0
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assert):
                count += 1
                continue
            if isinstance(sub, ast.Call):
                f = sub.func
                if (
                    isinstance(f, ast.Attribute)
                    and f.attr in cls._TQ001_PYTEST_ASSERT_ATTRS
                ):
                    count += 1
                elif isinstance(f, ast.Name) and f.id in cls._TQ001_PYTEST_ASSERT_ATTRS:
                    count += 1
        return count

    @classmethod
    def _tq001_function_has_assertion(cls, node) -> bool:
        """True iff a `test_*` body contains a real assertion construct."""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assert):
                return True
            if isinstance(sub, ast.Call):
                f = sub.func
                if (
                    isinstance(f, ast.Attribute)
                    and f.attr in cls._TQ001_PYTEST_ASSERT_ATTRS
                ):
                    return True
                if isinstance(f, ast.Name) and f.id in cls._TQ001_PYTEST_ASSERT_ATTRS:
                    return True
        return False
