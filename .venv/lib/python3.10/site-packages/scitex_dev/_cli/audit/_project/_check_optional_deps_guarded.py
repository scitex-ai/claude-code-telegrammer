# -*- coding: utf-8 -*-
"""PS-148 — downstream optional-deps guarded at the peer level.

(Spec alias: the living plan ``downstream-optional-deps-audit.md`` floats
this as ``PA-302`` / ``PA-007``. It lands here as **PS-148** because it
is pyproject-driven and the natural sibling of the test-side mirror PS-210
in this same project auditor — same parse/scan machinery, opposite tree.)

Implements the rule from
`_skills/general/01_ecosystem/02_dependency-and-version-pinning.md` and the
living plan ``downstream-optional-deps-audit.md``.

Symptom this prevents (the ``ModuleNotFoundError`` class of breakage):

  A peer lists a heavy third-party lib (``torch`` / ``pandas`` / ``xarray``
  / …) under ``[project.optional-dependencies]`` — correctly making it
  optional at the *distribution* level — but then imports that lib
  UNGUARDED at module top of ``src/``. The package builds, and its own
  test suite passes (the dev venv has the extra installed), yet a fresh
  ``pip install <peer>`` (no extras) followed by ``import <peer>`` blows
  up with ``ModuleNotFoundError``.

Decision rule the auditor enforces:

  For each lib declared in any ``[project.optional-dependencies.<extra>]``
  block (other than ``[dev]`` / ``[all]`` / ``[test]``), scan every
  ``src/`` module for a MODULE-LEVEL ``import <lib>`` / ``from <lib>
  import …``. If such an import is found OUTSIDE a ``try/except
  ImportError`` and is NOT wrapped by ``try_import_optional`` →
  PS-148 (error).

Why this is distinct from PA-301 / PS-210:

- PA-301 flags unguarded top-level imports only in ``__init__.py`` and
  only by a hardcoded ``_THIRD_PARTY_ROOTS`` heuristic — it does NOT
  consult the pyproject and does NOT walk the whole ``src/`` tree.
- PS-210 (``_check_dev_extras_complete``) is the TEST-side mirror: a dep
  declared in an extra, imported unguarded in ``tests/``, missing from
  ``[dev]``.
- PS-148 is the SOURCE-side rule: a dep declared in an extra, imported
  unguarded in ``src/``. The two together close both halves of the
  install-story.

The canonical fix is the standardized helper:

    from scitex_dev import try_import_optional
    torch_fn = try_import_optional(
        "._torch_fn", "torch_fn", extra="torch", pkg="scitex-decorators"
    )

…or, when the import must stay a plain ``import``, wrap it in
``try/except ImportError`` (still flagged unless inside such a guard).

Heuristic notes
---------------

- The auditor reads ``pyproject.toml`` only for the dep list — it does
  not import the package, so it is safe on broken trees.
- Distribution name → import root mapping handles the common cases
  where the two differ (``scikit-learn`` → ``sklearn``, ``pillow`` →
  ``PIL``, ``opencv-python`` → ``cv2``, ``google-genai`` → ``google``,
  …). Both the mapped root AND the naive ``replace("-", "_")`` form are
  treated as a hit, so an import under either name is caught.
- scitex-* peer deps in an extra are ignored — those are first-party
  ecosystem packages handled by the umbrella/extra story, not the
  third-party ``ModuleNotFoundError`` failure mode this rule guards.
- Module-level only: function- and class-scoped imports are lazy and
  fire only when the function is called, so they don't break a bare
  ``import <peer>``. Same scoping discipline as PA-304.
- ``if __name__ == "__main__":`` blocks are skipped (only run on direct
  module invocation, never on ``import <peer>``).
"""

from __future__ import annotations

import ast
from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 path
    import tomli as tomllib  # type: ignore[no-redef]


# Distribution name → import root, for the cases where they differ.
# Lowercased dist name (hyphens preserved) → import root used in source.
_DIST_TO_IMPORT: dict[str, str] = {
    "scikit-learn": "sklearn",
    "scikit-image": "skimage",
    "pillow": "PIL",
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "google-genai": "google",
    "google-generativeai": "google",
    "beautifulsoup4": "bs4",
    "pyyaml": "yaml",
    "python-dateutil": "dateutil",
    "msgpack-python": "msgpack",
    "protobuf": "google",
    "pytorch-lightning": "lightning",
    "pytorch": "torch",
    "faiss-cpu": "faiss",
    "faiss-gpu": "faiss",
    "umap-learn": "umap",
    "hdbscan": "hdbscan",
}

# Extras that are NOT consumer-facing optional features — they bundle dev
# / aggregate / test tooling and their members are not part of the
# "fresh `pip install <peer>` then import <peer>" failure mode.
_NON_FEATURE_EXTRAS = frozenset({"dev", "all", "test", "tests", "docs", "doc"})


def _strip_version(spec: str) -> str:
    """``torch>=2.0`` → ``torch``; ``scitex-clew[mcp]>=0.2`` → ``scitex-clew``.

    Returns the lowercased distribution name with hyphens preserved (so the
    ``_DIST_TO_IMPORT`` table can key on it).
    """
    import re

    name = re.split(r"[<>=!~;\s\[]", spec, maxsplit=1)[0].strip()
    return name.lower()


def _import_roots_for(dist: str) -> set[str]:
    """All import-root spellings a distribution might appear as in source."""
    roots: set[str] = set()
    mapped = _DIST_TO_IMPORT.get(dist)
    if mapped:
        roots.add(mapped)
    # Naive form is always a candidate (covers torch, pandas, xarray,
    # joblib, h5py, zarr, mne, optuna, anthropic, openai, …).
    roots.add(dist.replace("-", "_"))
    return roots


def _optional_lib_roots(meta: dict) -> dict[str, tuple[str, str]]:
    """Map each candidate import-root → (extra_name, dist_name).

    Skips ``[dev]``/``[all]``/``[test]`` extras and scitex-* peer deps.
    When two extras declare the same root, the first wins (deterministic
    via sorted iteration).
    """
    project = meta.get("project", {}) or {}
    od = project.get("optional-dependencies", {}) or {}
    out: dict[str, tuple[str, str]] = {}
    for extra in sorted(od):
        if extra in _NON_FEATURE_EXTRAS:
            continue
        for spec in od[extra]:
            dist = _strip_version(spec)
            if not dist or dist.startswith("scitex"):
                continue
            for root in _import_roots_for(dist):
                out.setdefault(root, (extra, dist))
    return out


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


def _scan_unguarded(
    body: list[ast.stmt],
    roots: dict[str, tuple[str, str]],
    in_try_importerror: bool,
    found: list[tuple[str, int, str]],
) -> None:
    """Collect (import_root, lineno, kind) for module-level unguarded imports.

    ``in_try_importerror`` is True when inside a ``try`` whose handlers catch
    ``ImportError`` (or bare ``except``) — such imports ARE guarded.
    Function / class bodies are not descended into (lazy). ``if __name__``
    blocks are skipped.
    """
    for stmt in body:
        if _is_dunder_main_if(stmt):
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(stmt, ast.Import):
            if in_try_importerror:
                continue
            for alias in stmt.names:
                root = alias.name.split(".", 1)[0]
                if root in roots:
                    found.append((root, stmt.lineno, f"import {alias.name}"))
        elif isinstance(stmt, ast.ImportFrom):
            if in_try_importerror:
                continue
            if stmt.level and stmt.level > 0:
                continue  # relative — first-party, never an optional 3rd-party
            mod = stmt.module or ""
            root = mod.split(".", 1)[0] if mod else ""
            if root in roots:
                found.append((root, stmt.lineno, f"from {mod} import ..."))
        elif isinstance(stmt, ast.Try):
            guards_importerror = _try_guards_importerror(stmt)
            _scan_unguarded(stmt.body, roots, guards_importerror, found)
            for handler in stmt.handlers:
                _scan_unguarded(handler.body, roots, in_try_importerror, found)
            _scan_unguarded(stmt.orelse, roots, in_try_importerror, found)
            _scan_unguarded(stmt.finalbody, roots, in_try_importerror, found)
        elif isinstance(stmt, (ast.If, ast.With, ast.AsyncWith)):
            children: list[ast.stmt] = []
            children.extend(getattr(stmt, "body", []) or [])
            children.extend(getattr(stmt, "orelse", []) or [])
            _scan_unguarded(children, roots, in_try_importerror, found)


def _try_guards_importerror(node: ast.Try) -> bool:
    """True when the ``try`` has a handler catching ImportError / bare except."""
    for handler in node.handlers:
        exc = handler.type
        if exc is None:  # bare `except:`
            return True
        names: list[str] = []
        if isinstance(exc, ast.Name):
            names.append(exc.id)
        elif isinstance(exc, ast.Attribute):
            names.append(exc.attr)
        elif isinstance(exc, ast.Tuple):
            for elt in exc.elts:
                if isinstance(elt, ast.Name):
                    names.append(elt.id)
                elif isinstance(elt, ast.Attribute):
                    names.append(elt.attr)
        if any(n in ("ImportError", "ModuleNotFoundError", "Exception") for n in names):
            return True
    return False


def check_ps148_optional_deps_guarded(
    repo: Path,
    distribution: str,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-148 violations for unguarded optional-extra imports in ``src/``.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing ``pyproject.toml`` and ``src/``).
    distribution : str
        Distribution name, e.g. ``"scitex-decorators"``.
    violation_cls : type
        The auditor's ``Violation`` dataclass ``(rule, where, detail)``.
    out : list
        Violations are appended in place (project-auditor convention).
    """
    repo_root = repo
    import_name = distribution.replace("-", "_")

    pp = repo_root / "pyproject.toml"
    if not pp.is_file():
        return
    try:
        meta = tomllib.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return

    roots = _optional_lib_roots(meta)
    if not roots:
        return

    # Scan the package source. Canonical layout is `<repo>/src/`; a few
    # legacy packages keep the source flat at `<repo>/<pkg>/`.
    src_root = repo_root / "src"
    scan_root = src_root if src_root.is_dir() else (repo_root / import_name)
    if not scan_root.is_dir():
        return

    for py_file in sorted(scan_root.rglob("*.py")):
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
                "examples",
                "docs",
                # Non-library subtrees: scratch/dev sandboxes, vendored
                # agent assets, Django migrations (framework-generated,
                # only imported under the django app context), bundled
                # skill markdown helper scripts. None of these are part of
                # the `import <peer>` path, so a missing optional dep there
                # never breaks a bare import of the package.
                "_dev",
                ".claude",
                "_skills",
                "migrations",
            )
        ):
            continue
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
        if not isinstance(tree, ast.Module):
            continue
        found: list[tuple[str, int, str]] = []
        _scan_unguarded(tree.body, roots, in_try_importerror=False, found=found)
        for root, lineno, kind in found:
            extra, dist = roots[root]
            try:
                rel = py_file.relative_to(repo_root)
            except ValueError:
                rel = py_file
            out.append(
                violation_cls(
                    "PS-148",
                    f"{distribution}: {rel}:{lineno}",
                    (
                        f"`{kind}` — `{dist}` is declared optional via "
                        f"`[{extra}]` but imported unguarded at module top. "
                        f"A fresh `pip install {distribution}` (no extras) "
                        f"then `import {import_name}` would raise "
                        f"ModuleNotFoundError. Wrap with `try_import_optional"
                        f'("...", extra="{extra}", pkg="{distribution}")` or a '
                        f"`try/except ImportError` guard. See _skills/general/"
                        f"03_interface/01_python-api/"
                        f"04_lazy-imports-and-optional-deps.md."
                    ),
                )
            )


# EOF
