"""PS-210 — `[dev]` extras completeness.

Implements the rule from
`_skills/general/01_ecosystem/02_dependency-and-version-pinning.md`
section "`[dev]` extras completeness — fastmcp lesson, 2026-05-02".

Symptom this prevents: a package adds an optional feature behind an
`[X]` extra (e.g. ``[mcp]``), tests import the dep unconditionally
(e.g. ``from fastmcp import FastMCP``), but ``[dev]`` does not include
the dep. The first contributor / CI run after the push fails at
test-collection time with ``ModuleNotFoundError``.

Decision rule the auditor enforces:

  if a project distribution name imported anywhere in ``tests/``
  is declared in some ``[X]`` extra and NOT in ``[dev]``,
  AND the test imports it WITHOUT a guarding ``pytest.importorskip``,
  emit PS-210 (warn).

The auditor is intentionally limited to **distribution-level** deps so
it stays language-agnostic and doesn't need to model every transitive
import — the failure mode the lesson describes is exactly the
distribution-level one.

Heuristic notes
---------------

- ``importorskip("dep")`` and ``importorskip('dep')`` (single or double
  quotes) anywhere in the test file is treated as a guard for that
  dep — if every import of ``dep`` is guarded the rule does not fire.
- Stdlib and "always-installed" deps (pytest, click, numpy, …) are
  treated as ambient and not checked. The point is optional 3rd-party
  surface, not core deps that everyone has.
- The auditor reads ``pyproject.toml`` only — does not import the
  package, so it is safe to run on broken trees.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 path
    import tomli as tomllib  # type: ignore[no-redef]


# Distribution names that every Python install or the SciTeX baseline
# is assumed to provide. Tests are allowed to import these without an
# accompanying [dev] entry — they are either stdlib or in [dev]
# transitively via pytest/scitex-dev.
_AMBIENT = frozenset(
    {
        "pytest",
        "pytest_cov",
        "pytest_asyncio",
        "pytest_timeout",
        "click",
        "numpy",
        "pandas",
        "scipy",
        "matplotlib",
        "yaml",
        "toml",
        "tomllib",
        "tomli",
    }
)


_RE_IMPORT = re.compile(
    r"^\s*(?:from\s+([A-Za-z_][A-Za-z0-9_]*)|import\s+([A-Za-z_][A-Za-z0-9_]*))",
    re.MULTILINE,
)
_RE_IMPORTORSKIP = re.compile(r"""importorskip\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]""")


def _parse_pyproject(repo: Path) -> dict | None:
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return None
    try:
        return tomllib.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return None


def _strip_version(spec: str) -> str:
    """``fastmcp>=2.0`` → ``fastmcp``; ``scitex-clew[mcp]>=0.2`` → ``scitex_clew``."""
    name = re.split(r"[<>=!\s\[]", spec, maxsplit=1)[0].strip()
    return name.replace("-", "_").lower()


def _extras_index(
    meta: dict,
) -> tuple[set[str], dict[str, set[str]], str]:
    """Return (deps_in_dev, {extra_name: {dep_dist_name, …}, …}, self_name)."""
    project = meta.get("project", {}) or {}
    self_name = (project.get("name") or "").replace("-", "_").lower()
    od = project.get("optional-dependencies", {}) or {}
    dev = {_strip_version(s) for s in od.get("dev", [])}
    others = {
        name: {_strip_version(s) for s in deps}
        for name, deps in od.items()
        if name != "dev"
    }
    return dev, others, self_name


def _scan_py_dir(py_dir: Path) -> tuple[set[str], set[str]]:
    """Return (top-level imports under ``py_dir``, importorskip dep names)."""
    imports: set[str] = set()
    guarded: set[str] = set()
    if not py_dir.is_dir():
        return imports, guarded
    for py in py_dir.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _RE_IMPORT.finditer(text):
            mod = m.group(1) or m.group(2)
            if mod:
                imports.add(mod.lower())
        for m in _RE_IMPORTORSKIP.finditer(text):
            guarded.add(m.group(1).lower())
    return imports, guarded


def check_dev_extras_complete(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS-210 violations.

    Fires when a dep is declared in some `[X]` extra, used unguarded in
    tests, but absent from `[dev]`. The fix is to add the dep to `[dev]`
    or guard the tests with ``pytest.importorskip``.
    """
    meta = _parse_pyproject(repo)
    if meta is None:
        return

    dev, extras, self_name = _extras_index(meta)
    if not extras:
        return

    test_imports, guarded = _scan_py_dir(repo / "tests")
    src_imports, _ = _scan_py_dir(repo / "src")
    if not test_imports:
        return

    # For each [X] extra dep, check if tests import it unguarded and [dev]
    # doesn't already cover it.
    #
    # Coverage is direct OR transitive:
    #   - direct: a test file does ``from <dep> import …``
    #   - transitive: src/ imports the dep AND tests import a src/ module
    #     (the failure mode is "fresh `[dev]` install can't collect tests").
    for extra_name, deps in extras.items():
        for dep in sorted(deps):
            if dep in _AMBIENT:
                continue
            if dep == self_name:
                continue  # `[all] = ["pkg[mcp]"]` recursion is benign
            if dep in dev:
                continue  # already in [dev] — not an issue
            direct = dep in test_imports
            transitive = (
                dep in src_imports and self_name in test_imports and self_name != ""
            )
            if not (direct or transitive):
                continue
            if dep in guarded:
                continue  # importorskip handles it
            out.append(
                violation_cls(
                    "PS-210",
                    str(repo / "pyproject.toml"),
                    (
                        f"`[{extra_name}]` extra declares `{dep}` and tests "
                        f"import it unguarded, but `[dev]` does not include "
                        f"it. Either add `{dep}` to `[dev]` so a fresh "
                        f"`pip install -e .[dev]` runs the full suite, or "
                        f"guard the test imports with "
                        f'`pytest.importorskip("{dep}")`. See '
                        f"_skills/general/01_ecosystem/02_dependency-and-"
                        f"version-pinning.md `[dev]` extras completeness."
                    ),
                )
            )
