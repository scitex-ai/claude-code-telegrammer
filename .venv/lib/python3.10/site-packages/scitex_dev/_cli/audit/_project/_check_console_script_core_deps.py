# -*- coding: utf-8 -*-
"""PS-213 — console-script-deps-must-be-core.

A dep imported at MODULE-LOAD time on the reachability chain rooted at
any ``[project.scripts]`` entry-point — that is, a dep the CLI needs to
**start** — MUST appear in ``[project.dependencies]``. If it lives only
in ``[project.optional-dependencies]`` then bare ``pip install <peer>``
followed by ``<peer-cli> --help`` exits non-zero, and the operator who
just installed the package faces an opaque ``ModuleNotFoundError`` (or
the package's own graceful "Install with: pip install <peer>[<extra>]"
message — which is **not** a substitute for actually pinning the dep at
the right level: it shifts a CI-detectable bug into runtime guesswork).

The complement is :mod:`_check_optional_deps_guarded` (PS-148), which
fires when an optional-extra dep is imported unguarded in ``src/`` for
the **library** surface. PS-213 is the **CLI-launch** surface:
specifically the closure of ``[project.scripts]`` entry-points.

Decision
--------

For each entry-point declared in ``[project.scripts]``:

1. Resolve ``"<module>:<callable>"`` to ``src/<module-as-path>.py`` (or
   ``__init__.py``).
2. Build the module-load reachability set by AST-walking that file and
   recursively following every relative ``from . import X`` /
   ``from .X import Y`` / ``import .X``, and every absolute import whose
   root equals the package's own import name. Module/class/function
   bodies are NOT descended (they fire lazily at call time).
3. For each module in the reachability set, scan **module-level**
   imports (outside function/class bodies). Try/except guards are
   ignored for this rule: a graceful "pip install <pkg>[<extra>]"
   fallback is exactly the failure mode we want to surface.
4. For each non-stdlib / non-first-party imported root ``X``:

   * If ``X`` is satisfied by an entry in
     ``[project.dependencies]`` → OK.
   * If ``X`` is satisfied **only** by an entry in
     ``[project.optional-dependencies].<extra>`` → emit
     ``PS-213`` (``CORE-CLI-DEP-MISSING``) telling the operator to move
     it to ``[project.dependencies]``.

In parallel, ``_emit_lazy_pattern_info`` walks every src/ module's
**function bodies** for imports of optional-dependency roots whose
function body also raises ``SystemExit(...)`` with a literal string
containing ``pip install <pkg>[<extra>]``. Each such site is emitted as
``PS-213i`` (``LAZY-EXTRA-PATTERN-OK``) — an info-severity *signal*
that the lazy-extra pattern is in use, so the operator can audit
coverage of every optional subcommand without grepping by hand.

Stdlib detection uses :pydata:`sys.stdlib_module_names` (Python 3.10+).
The auditor itself runs on the agent venv (>=3.11 in practice) even if
the audited repo pins ``requires-python = ">=3.9"``.

References
----------

* ``_skills/general/01_ecosystem/02_dependency-and-version-pinning.md``
* ``_skills/general/03_interface/01_python-api/04_lazy-imports-and-optional-deps.md``
* PS-148 source-side optional-dep guarded check (companion rule).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterable

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 path
    import tomli as tomllib  # type: ignore[no-redef]


# Reuse the canonical distribution-name → import-root map from the
# optional-deps-guarded check so PS-148 and PS-213 stay aligned.
from ._check_optional_deps_guarded import (
    _DIST_TO_IMPORT,
    _strip_version,
)


# Extras whose presence in pyproject is not treated as "the lazy-extra
# pattern" target — they are dev/aggregate/test buckets, not
# consumer-facing optional features users would `pip install <pkg>[<x>]`
# for. Mirrors PS-148's _NON_FEATURE_EXTRAS.
_NON_FEATURE_EXTRAS = frozenset({"dev", "all", "test", "tests", "docs", "doc"})


_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ()))


def _import_roots_for(dist: str) -> set[str]:
    """All import-root spellings a distribution might appear as in source."""
    roots: set[str] = set()
    mapped = _DIST_TO_IMPORT.get(dist)
    if mapped:
        roots.add(mapped)
    roots.add(dist.replace("-", "_"))
    return roots


def _root_to_extras(meta: dict) -> dict[str, list[str]]:
    """Map each import-root → list of feature-extras that satisfy it.

    Iterates ``[project.optional-dependencies].<extra>`` (skipping
    dev/aggregate buckets) and records which extras would resolve each
    candidate root.
    """
    project = meta.get("project", {}) or {}
    od = project.get("optional-dependencies", {}) or {}
    out: dict[str, list[str]] = {}
    for extra in sorted(od):
        if extra in _NON_FEATURE_EXTRAS:
            continue
        for spec in od[extra]:
            dist = _strip_version(spec)
            if not dist or dist.startswith("scitex"):
                continue
            for root in _import_roots_for(dist):
                out.setdefault(root, []).append(extra)
    return out


def _core_roots(meta: dict) -> set[str]:
    """Set of all import-roots satisfied by ``[project.dependencies]``."""
    project = meta.get("project", {}) or {}
    deps = project.get("dependencies", []) or []
    out: set[str] = set()
    for spec in deps:
        dist = _strip_version(spec)
        if not dist:
            continue
        for root in _import_roots_for(dist):
            out.add(root)
    return out


def _parse_entry_points(meta: dict) -> dict[str, str]:
    """Return ``{script_name: "module.path:callable"}`` from [project.scripts]."""
    project = meta.get("project", {}) or {}
    scripts = project.get("scripts", {}) or {}
    return {name: target for name, target in scripts.items() if isinstance(target, str)}


def _resolve_module_file(
    src_root: Path,
    import_name: str,
    module_path: str,
) -> Path | None:
    """Locate the .py file backing ``module_path`` (a dotted import path).

    Resolves ``scitex_dev._cli`` → ``src/scitex_dev/_cli/__init__.py``
    or ``src/scitex_dev/_cli.py``, whichever exists.
    """
    parts = module_path.split(".")
    if not parts or parts[0] != import_name:
        return None
    rel = Path(*parts)
    f = src_root / rel.with_suffix(".py")
    if f.is_file():
        return f
    f = src_root / rel / "__init__.py"
    if f.is_file():
        return f
    return None


def _module_path_for(src_root: Path, py_file: Path, import_name: str) -> str:
    """Inverse of :func:`_resolve_module_file` — file path → dotted module path."""
    try:
        rel = py_file.relative_to(src_root)
    except ValueError:
        return ""
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if not parts or parts[0] != import_name:
        return ""
    return ".".join(parts)


def _toplevel_imports(tree: ast.Module) -> list[tuple[ast.AST, str, int]]:
    """Yield ``(node, root, lineno)`` for module-level imports.

    Descends ``if`` / ``try`` / ``with`` bodies (still module-load) but
    does NOT descend into ``FunctionDef`` / ``AsyncFunctionDef`` /
    ``ClassDef``. Each returned ``root`` is the top-most import root
    (``a.b.c`` → ``a``; relative imports → empty string).
    """
    out: list[tuple[ast.AST, str, int]] = []

    def walk(body: list[ast.stmt]) -> None:
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    root = alias.name.split(".", 1)[0]
                    out.append((stmt, root, stmt.lineno))
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.level and stmt.level > 0:
                    out.append((stmt, "", stmt.lineno))  # relative — sentinel
                else:
                    mod = stmt.module or ""
                    root = mod.split(".", 1)[0] if mod else ""
                    if root:
                        out.append((stmt, root, stmt.lineno))
            elif isinstance(stmt, ast.Try):
                walk(stmt.body)
                for handler in stmt.handlers:
                    walk(handler.body)
                walk(stmt.orelse)
                walk(stmt.finalbody)
            elif isinstance(stmt, (ast.If, ast.With, ast.AsyncWith)):
                walk(getattr(stmt, "body", []) or [])
                walk(getattr(stmt, "orelse", []) or [])

    walk(tree.body)
    return out


def _relative_targets(
    stmt: ast.ImportFrom,
    current_mod: str,
    import_name: str,
) -> list[str]:
    """Resolve a ``from . import X`` / ``from .X import Y`` to absolute module paths."""
    if stmt.level == 0:
        return []
    base = current_mod.rsplit(".", stmt.level - 1)[0] if stmt.level > 1 else current_mod
    base_parts = base.split(".")
    if stmt.level > 1:
        base_parts = base_parts[: -(stmt.level - 1)] if len(base_parts) >= stmt.level - 1 else []
    # `from . import` (level=1): base is current_mod's parent. The
    # imported NAMES may be submodules or attributes; we conservatively
    # treat each as a candidate submodule.
    if not base_parts or base_parts[0] != import_name:
        # parent walked past the package root — can't resolve.
        return []
    base_dotted = ".".join(base_parts)
    targets: list[str] = []
    if stmt.module:
        targets.append(f"{base_dotted}.{stmt.module}" if base_dotted else stmt.module)
    for alias in stmt.names:
        if alias.name == "*":
            continue
        # Each "name" might be a submodule (then it's a reachable file)
        # or an attribute of `stmt.module` (already covered above).
        if stmt.module:
            continue
        targets.append(f"{base_dotted}.{alias.name}" if base_dotted else alias.name)
    return targets


def _reachable_modules(
    entry_module: str,
    src_root: Path,
    import_name: str,
    *,
    max_modules: int = 200,
) -> list[Path]:
    """BFS over module-load relative imports starting at ``entry_module``."""
    seen: set[str] = set()
    out: list[Path] = []
    queue: list[str] = [entry_module]
    while queue and len(seen) < max_modules:
        mod = queue.pop(0)
        if mod in seen:
            continue
        seen.add(mod)
        f = _resolve_module_file(src_root, import_name, mod)
        if f is None:
            continue
        out.append(f)
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except (OSError, SyntaxError):
            continue
        for stmt, root, _ln in _toplevel_imports(tree):
            if isinstance(stmt, ast.ImportFrom) and stmt.level and stmt.level > 0:
                for target in _relative_targets(stmt, mod, import_name):
                    if target and target not in seen:
                        queue.append(target)
            elif isinstance(stmt, ast.Import):
                # Absolute import like `import scitex_dev.x.y`: follow the chain.
                for alias in stmt.names:
                    aroot = alias.name.split(".", 1)[0]
                    if aroot == import_name and alias.name not in seen:
                        queue.append(alias.name)
            elif isinstance(stmt, ast.ImportFrom):
                # Absolute `from scitex_dev.foo import bar`: follow.
                mod_name = stmt.module or ""
                root2 = mod_name.split(".", 1)[0]
                if root2 == import_name and mod_name not in seen:
                    queue.append(mod_name)
    return out


_PIP_INSTALL_RE = re.compile(
    r"""pip\s+install\s+["']?([A-Za-z0-9_\-]+)\s*\[\s*([A-Za-z0-9_\-]+)\s*\]"""
)


def _function_install_hint_extras(node: ast.AST) -> set[str]:
    """Walk a function body looking for ``pip install <pkg>[<extra>]`` literals.

    Returns the set of extra names referenced. Used by
    :func:`_emit_lazy_pattern_info` to confirm the lazy-import +
    install-hint pattern.
    """
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            for m in _PIP_INSTALL_RE.finditer(child.value):
                found.add(m.group(2))
        elif isinstance(child, ast.JoinedStr):
            for v in child.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    for m in _PIP_INSTALL_RE.finditer(v.value):
                        found.add(m.group(2))
    return found


def _function_imports(node: ast.AST) -> Iterable[tuple[str, int]]:
    """Yield ``(root, lineno)`` for imports anywhere inside a function body."""
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                yield alias.name.split(".", 1)[0], child.lineno
        elif isinstance(child, ast.ImportFrom):
            if child.level:
                continue
            mod = child.module or ""
            root = mod.split(".", 1)[0]
            if root:
                yield root, child.lineno


def _is_external(root: str, import_name: str) -> bool:
    """True when ``root`` is neither stdlib nor the package's own import name."""
    if not root:
        return False
    if root == import_name:
        return False
    if root in _STDLIB:
        return False
    return True


def check_ps213_console_script_core_deps(
    repo: Path,
    distribution: str,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-213 violations (and PS-213i info entries) for ``repo``.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing ``pyproject.toml`` and ``src/``).
    distribution : str
        Distribution name, e.g. ``"scitex-dev"``.
    violation_cls : type
        The auditor's ``Violation`` dataclass ``(rule, where, detail)``.
    out : list
        Violations appended in place (project-auditor convention).
    """
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return
    try:
        meta = tomllib.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return

    entry_points = _parse_entry_points(meta)
    if not entry_points:
        return

    src_root = repo / "src"
    import_name = distribution.replace("-", "_")
    scan_root = src_root if src_root.is_dir() else (repo / import_name)
    if not scan_root.is_dir():
        return

    core_roots = _core_roots(meta)
    extras_roots = _root_to_extras(meta)
    if not extras_roots:
        return  # no optional-deps to misplace

    # Collect reachability closure once across all entry-points.
    reachable: set[Path] = set()
    for _name, target in entry_points.items():
        mod = target.split(":", 1)[0].strip()
        for f in _reachable_modules(mod, src_root, import_name):
            reachable.add(f)

    # --- (a) HARD violations: a CORE CLI dep is hiding in an extra ---
    for f in sorted(reachable):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except (OSError, SyntaxError):
            continue
        for _node, root, lineno in _toplevel_imports(tree):
            if not _is_external(root, import_name):
                continue
            if root in core_roots:
                continue
            if root in extras_roots:
                extras = ", ".join(extras_roots[root])
                try:
                    rel = f.relative_to(repo)
                except ValueError:
                    rel = f
                out.append(
                    violation_cls(
                        "PS-213",
                        f"{distribution}: {rel}:{lineno}",
                        (
                            f"`{root}` is imported at module-load on the "
                            f"`[project.scripts]` reachability chain but lives in "
                            f"`[project.optional-dependencies].{extras}`, not in "
                            f"`[project.dependencies]`. Bare `pip install "
                            f"{distribution}` followed by `<cli> --help` will fail. "
                            f"Move `{root}` to `[project.dependencies]` (and drop "
                            f"any `try/except ImportError` graceful fallback in the "
                            f"source — a CI signal is the correct response, not a "
                            f"runtime hint). See _skills/general/01_ecosystem/"
                            f"02_dependency-and-version-pinning.md "
                            f"§console-script-deps-must-be-core."
                        ),
                    )
                )

    # --- (b) INFO: lazy-extra-pattern OK signals ---
    # Walk every src module's FUNCTION bodies looking for the canonical
    # pattern: an extra-only dep imported lazily, with a `pip install
    # <pkg>[<extra>]` install-hint string in the same function body.
    for py_file in sorted(scan_root.rglob("*.py")):
        if any(
            seg in py_file.parts
            for seg in ("__pycache__", "build", "dist", ".tox", "site-packages")
        ):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            hint_extras = _function_install_hint_extras(node)
            if not hint_extras:
                continue
            for root, lineno in _function_imports(node):
                if not _is_external(root, import_name):
                    continue
                if root in core_roots:
                    continue
                declared = set(extras_roots.get(root, []))
                if not declared:
                    continue
                overlap = sorted(declared & hint_extras)
                if not overlap:
                    continue
                try:
                    rel = py_file.relative_to(repo)
                except ValueError:
                    rel = py_file
                out.append(
                    violation_cls(
                        "PS-213i",
                        f"{distribution}: {rel}:{lineno}",
                        (
                            f"LAZY-EXTRA-PATTERN-OK: `{root}` lazy-imported inside "
                            f"`{node.name}()` with install hint referencing "
                            f"`[{overlap[0]}]`. Permitted by PS-213; reported as "
                            f"info so coverage of optional subcommands is auditable."
                        ),
                    )
                )


# EOF
