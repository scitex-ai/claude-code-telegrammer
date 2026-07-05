"""`__init__.py` surface checks for the Python API auditor.

Split out of `_audit.py` — pure refactor, no behaviour change. Covers the
static AST checks against the package's ``__init__.py``: §1 naming/visibility
(PA-101..104), §2 version strategy (PA-201..203), §3 top-level optional-import
(PA-301), and §5 type hints (PA-501). Re-exported from `_audit` so existing
imports (`from ..._audit import _audit_init`) keep resolving.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._model import _STDLIB_SAFE_ROOTS, _THIRD_PARTY_ROOTS, Violation


def _audit_init(init_path: Path, distribution: str) -> list[Violation]:
    src = init_path.read_text()
    tree = ast.parse(src, filename=str(init_path))
    out: list[Violation] = []

    where = f"{distribution}/__init__.py"

    # Collect: __all__, bound names, imports (with try/except context),
    # presence of `from __future__ import annotations`, __version__ details.
    all_names: list[str] | None = None
    bound_names: set[str] = set()
    third_party_bound: set[str] = set()
    state: dict[str, object] = {
        "future": False,
        "all": None,
        "version_nodes": [],
        # Local names bound to `importlib.metadata.version` (incl. aliases like
        # `from importlib.metadata import version as _v`). Used by PA-202.
        "version_aliases": {"version"},
    }

    def _record_import(node: ast.AST, in_try: bool) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                local = alias.asname or alias.name.split(".", 1)[0]
                bound_names.add(local)
                if root in _THIRD_PARTY_ROOTS:
                    third_party_bound.add(local)
                if (
                    not in_try
                    and root not in _STDLIB_SAFE_ROOTS
                    and not root.startswith("scitex")
                    and root != distribution.replace("-", "_").split("_")[0]
                ):
                    out.append(
                        Violation(
                            "PA-301",
                            where,
                            f"`import {alias.name}` at module top-level "
                            "(wrap in try/except ImportError if optional)",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            root = mod.split(".", 1)[0] if mod else ""
            if mod == "__future__" and any(a.name == "annotations" for a in node.names):
                state["future"] = True
                return
            for alias in node.names:
                local = alias.asname or alias.name
                bound_names.add(local)
                # Record `from importlib.metadata import version [as X]` aliases
                # so PA-202 recognizes the canonical pattern through any alias.
                if mod == "importlib.metadata" and alias.name == "version":
                    aliases = state["version_aliases"]
                    assert isinstance(aliases, set)
                    aliases.add(local)
                if root in _THIRD_PARTY_ROOTS:
                    third_party_bound.add(local)
                if (
                    not in_try
                    and root
                    and root not in _STDLIB_SAFE_ROOTS
                    and not root.startswith("scitex")
                    and not mod.startswith(".")
                    and root != ""
                ):
                    # Relative imports have empty `module` resolved to "" —
                    # ast.ImportFrom.level > 0 marks them.
                    if node.level == 0:
                        out.append(
                            Violation(
                                "PA-301",
                                where,
                                f"`from {mod} import ...` at module top-level "
                                "(wrap in try/except ImportError if optional)",
                            )
                        )

    def _walk(body: list[ast.stmt], in_try: bool) -> None:
        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                _record_import(node, in_try)
            elif isinstance(node, ast.Try):
                _walk(node.body, in_try=True)
                for handler in node.handlers:
                    _walk(handler.body, in_try=True)
                _walk(node.orelse, in_try=in_try)
                _walk(node.finalbody, in_try=in_try)
            elif isinstance(node, ast.If):
                _walk(node.body, in_try)
                _walk(node.orelse, in_try)
            elif isinstance(node, ast.Assign):
                # Capture __all__, bound names, __version__ pattern.
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bound_names.add(target.id)
                        if target.id == "__all__" and isinstance(
                            node.value, (ast.List, ast.Tuple)
                        ):
                            state["all"] = [
                                elt.value
                                for elt in node.value.elts
                                if isinstance(elt, ast.Constant)
                                and isinstance(elt.value, str)
                            ]
                        if target.id == "__version__":
                            nodes = state.setdefault("version_nodes", [])
                            assert isinstance(nodes, list)
                            nodes.append(node)
                        # Track string-keyed dict literals at module level —
                        # these are commonly used by PEP 562 dispatch tables
                        # like `_LAZY_ATTRS = {"foo": "submod", ...}`.
                        if isinstance(node.value, ast.Dict):
                            keys = [
                                k.value
                                for k in node.value.keys
                                if isinstance(k, ast.Constant)
                                and isinstance(k.value, str)
                            ]
                            if keys:
                                tables = state.setdefault("dispatch_tables", {})
                                assert isinstance(tables, dict)
                                tables[target.id] = keys
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                # Annotated assignments: `__all__: list[str] = [...]`,
                # `__version__: str = ...`, `_LAZY_ATTRS: dict[str, str] = {...}`.
                # Treat them like ast.Assign.
                bound_names.add(node.target.id)
                if (
                    node.target.id == "__all__"
                    and node.value is not None
                    and isinstance(node.value, (ast.List, ast.Tuple))
                ):
                    state["all"] = [
                        elt.value
                        for elt in node.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]
                # Annotated dispatch table: `_LAZY_ATTRS: dict[str, str] = {...}`.
                if isinstance(node.value, ast.Dict):
                    keys = [
                        k.value
                        for k in node.value.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    ]
                    if keys:
                        tables = state.setdefault("dispatch_tables", {})
                        assert isinstance(tables, dict)
                        tables[node.target.id] = keys
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                bound_names.add(node.name)
                # Recognise PEP 562 lazy-load: `def __getattr__(name): if name == "X": ...`.
                # Pytest collects any module-level callable; PEP 562 lets a
                # module expose names dynamically without binding them at
                # import time. Treat each `name == "..."` literal inside
                # __getattr__ as a bound name so PA-102 doesn't false-fire.
                if node.name == "__getattr__":
                    for sub in ast.walk(node):
                        # Pattern A: `if name == "X":`
                        if (
                            isinstance(sub, ast.Compare)
                            and len(sub.ops) == 1
                            and isinstance(sub.ops[0], ast.Eq)
                            and isinstance(sub.left, ast.Name)
                            and sub.left.id == "name"
                            and len(sub.comparators) == 1
                            and isinstance(sub.comparators[0], ast.Constant)
                            and isinstance(sub.comparators[0].value, str)
                        ):
                            bound_names.add(sub.comparators[0].value)
                        # Pattern B: `_LAZY_ATTRS.get(name)` / `_LAZY_ATTRS[name]`
                        # — pull keys from the module-level dispatch table.
                        ref_name = None
                        if (
                            isinstance(sub, ast.Call)
                            and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr in ("get", "__getitem__")
                            and isinstance(sub.func.value, ast.Name)
                        ):
                            ref_name = sub.func.value.id
                        elif isinstance(sub, ast.Subscript) and isinstance(
                            sub.value, ast.Name
                        ):
                            ref_name = sub.value.id
                        if ref_name:
                            tables = state.get("dispatch_tables", {})
                            if isinstance(tables, dict):
                                for k in tables.get(ref_name, []):
                                    bound_names.add(k)

    _walk(tree.body, in_try=False)

    has_future_annotations = bool(state["future"])
    raw_all = state["all"]
    all_names: list[str] | None = raw_all if isinstance(raw_all, list) else None
    raw_versions = state["version_nodes"]
    version_nodes: list[ast.Assign] = (
        [n for n in raw_versions if isinstance(n, ast.Assign)]
        if isinstance(raw_versions, list)
        else []
    )

    # §5
    if not has_future_annotations:
        out.append(
            Violation("PA-501", where, "add `from __future__ import annotations`")
        )

    # §1
    if all_names is None:
        out.append(Violation("PA-101", where, "declare `__all__ = [...]`"))
    else:
        for n in all_names:
            if n.startswith("_") and n not in {"__version__"}:
                out.append(
                    Violation(
                        "PA-103", where, f"'{n}' is private but listed in __all__"
                    )
                )
            if n not in bound_names:
                out.append(
                    Violation(
                        "PA-102",
                        where,
                        f"'{n}' is in __all__ but not imported/defined in __init__.py",
                    )
                )
            if n in third_party_bound:
                out.append(
                    Violation(
                        "PA-104",
                        where,
                        f"'{n}' resolves to a third-party symbol — re-export breaks the API surface",
                    )
                )

    # §2 — version strategy
    # PA-201 only fires when __version__ is actually defined. Modules that
    # delegate everything (sys.modules aliases, e.g. scitex-plt → figrecipe)
    # don't define __version__ themselves.
    if (
        all_names is not None
        and "__version__" not in all_names
        and "__version__" in bound_names
    ):
        out.append(Violation("PA-201", where, "add `__version__` to __all__"))

    if version_nodes:
        raw_aliases = state["version_aliases"]
        version_aliases: set[str] = (
            raw_aliases if isinstance(raw_aliases, set) else {"version"}
        )
        results = [_inspect_version_pattern(n, version_aliases) for n in version_nodes]
        uses_metadata = any(ok for ok, _ in results)
        fallbacks = [fb for _, fb in results if fb is not None]
        if not uses_metadata:
            out.append(
                Violation(
                    "PA-202",
                    where,
                    "compute __version__ via importlib.metadata.version('<dist>') "
                    "with PackageNotFoundError fallback",
                )
            )
        for fb in fallbacks:
            if fb != "0.0.0+local":
                out.append(
                    Violation(
                        "PA-203",
                        where,
                        f"fallback is {fb!r}; use '0.0.0+local' (PEP 440 local segment)",
                    )
                )

    return out


def _inspect_version_pattern(
    node: ast.Assign,
    version_aliases: set[str] = frozenset({"version"}),  # type: ignore[assignment]
) -> tuple[bool, str | None]:
    """Return (uses_importlib_metadata, fallback_string_if_present).

    Recognized patterns:
        try:
            __version__ = version("<dist>")          # bare or aliased import
        except PackageNotFoundError:
            __version__ = "0.0.0+local"

        __version__ = importlib.metadata.version("<dist>")

    ``version_aliases`` is the set of local names bound to
    ``importlib.metadata.version`` (e.g. ``{"version", "_v"}`` after
    ``from importlib.metadata import version as _v``).
    """
    value = node.value
    if isinstance(value, ast.Call):
        callee = value.func
        if isinstance(callee, ast.Name) and callee.id in version_aliases:
            return True, None
        if (
            isinstance(callee, ast.Attribute)
            and callee.attr == "version"
            and isinstance(callee.value, ast.Attribute)
            and callee.value.attr == "metadata"
        ):
            return True, None
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        # Bare literal — considered drift unless it's exactly the local fallback.
        return False, value.value
    return False, None


__all__ = ["_audit_init", "_inspect_version_pattern"]
