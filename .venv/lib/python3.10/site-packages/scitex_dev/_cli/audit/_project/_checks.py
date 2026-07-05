"""Rule-check orchestrators for the project-structure auditor.

Each `_check_*` (or `check_*`) function inspects the repo and appends
`Violation` instances. Per-rule deep checks live in sibling `_check_*.py`
modules; this file holds the in-engine checks that used to sit in
`_audit.py` directly.

Split out of `_audit.py` (issue #103) — pure refactor, no behaviour change.
Re-exported from `_audit` for backward compatibility.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._constants import (
    _FORBIDDEN_TOP_DIRS,
    _KNOWN_TEST_SUBDIRS,
    _META_TESTS_AT_ROOT,
    _PRIVATE_TEST_RE,
    _PUBLIC_TEST_RE,
    _is_blacklisted,
)
from ._discovery import (
    _has_py,
    _import_name,
    _is_git_ignored,
    _src_pkg_dir,
    _tests_root,
)
from ._violation import Violation


def _check_top_level(repo: Path, out: list[Violation]) -> None:
    """PS-101 / PS-102 / PS-103 / PS-104 / PS-105 / PS-133-PS-135."""
    if not (repo / "pyproject.toml").is_file():
        out.append(Violation("PS-101", str(repo), "no pyproject.toml at repo root"))

    # PS-133-PS-138: required community files at repo root.
    # LICENSE has no extension (PEP-639 / ecosystem convention); accept LICENSE
    # or LICENSE.md or LICENSE.txt.
    for code, fname in (
        ("PS-133", "CLA.md"),
        ("PS-134", "CHANGELOG.md"),
        ("PS-135", "CONTRIBUTING.md"),
        ("PS-137", "README.md"),
    ):
        if not (repo / fname).is_file():
            out.append(Violation(code, str(repo), f"missing {fname}"))
    from ._check_license import (
        check_license_content,
        find_license,
        spdx_from_pyproject,
    )

    license_path = find_license(repo)
    if license_path is None:
        out.append(
            Violation("PS-138", str(repo), "missing LICENSE (or LICENSE.md/.txt)")
        )
    else:
        try:
            spdx_match = spdx_from_pyproject(repo)
        except Exception:
            spdx_match = None
        violation_msg = check_license_content(license_path, spdx_match)
        if violation_msg:
            out.append(Violation("PS-138b", str(repo), violation_msg))

    # PS-136: examples/ must exist and have at least one runnable file.
    examples = repo / "examples"
    if not examples.is_dir():
        out.append(Violation("PS-136", str(repo), "no examples/ directory"))
    else:
        runnable = [
            p
            for p in examples.rglob("*")
            if p.is_file()
            and p.suffix in {".py", ".ipynb", ".sh"}
            and not p.name.startswith("__")
            and "__pycache__" not in p.parts
        ]
        if not runnable:
            out.append(
                Violation(
                    "PS-136",
                    str(examples),
                    "examples/ exists but contains no .py/.ipynb/.sh",
                )
            )
        else:
            # PS-156: prefer .ipynb examples — fires only when examples/
            # has runnable .py files but zero .ipynb. Packages that mix
            # .py and .ipynb (or are pure-.ipynb) are silent.
            py_count = sum(1 for p in runnable if p.suffix == ".py")
            ipynb_count = sum(1 for p in runnable if p.suffix == ".ipynb")
            if py_count > 0 and ipynb_count == 0:
                out.append(
                    Violation(
                        "PS-156",
                        str(examples),
                        (
                            f"examples/ has {py_count} `.py` script(s) "
                            "and zero `.ipynb` notebooks — prefer "
                            "Jupyter notebooks (see "
                            "scitex-seizure-metrics/examples/). Mixed "
                            ".py + .ipynb is also fine."
                        ),
                    )
                )

    for dirname, why in _FORBIDDEN_TOP_DIRS.items():
        candidate = repo / dirname
        if candidate.is_dir():
            code = "PS-104" if dirname == ".playground" else "PS-102"
            out.append(Violation(code, str(candidate), why))

    # PS-103: anything at repo root that is not in the strict baseline,
    # not hidden, and not whitelisted via .scitex/dev/config.yaml.
    from ._root_whitelist import _suggest_relocation, list_violations

    for basename, kind in list_violations(repo):
        out.append(
            Violation(
                "PS-103",
                str(repo / basename),
                (
                    f"top-level {kind}: {basename} "
                    f"({_suggest_relocation(basename, kind)})"
                ),
            )
        )

    # PS-105: console_scripts present but no __main__.py — `python -m <pkg>`
    # would fail with "No module named <pkg>.__main__".
    pyp = repo / "pyproject.toml"
    if pyp.is_file():
        text = pyp.read_text(encoding="utf-8", errors="replace")
        has_console_scripts = "[project.scripts]" in text or "console_scripts" in text
        if has_console_scripts:
            # Find src/<pkg>/ candidates and check each top-level __main__.py.
            src = repo / "src"
            if src.is_dir():
                for pkg_dir in src.iterdir():
                    if not pkg_dir.is_dir() or pkg_dir.name.startswith("_"):
                        continue
                    if not (pkg_dir / "__init__.py").is_file():
                        continue
                    if not (pkg_dir / "__main__.py").is_file():
                        out.append(
                            Violation(
                                "PS-105",
                                str(pkg_dir),
                                f"missing {pkg_dir.name}/__main__.py — "
                                "`python -m " + pkg_dir.name + "` will fail. "
                                "Add a __main__.py that imports & calls the CLI entry.",
                            )
                        )


def _src_pkg_dir(repo: Path, distribution: str) -> Path | None:
    """Return `src/<pkg>/` if it exists, else None."""
    candidate = repo / "src" / _import_name(distribution)
    return candidate if candidate.is_dir() else None


def _tests_root(repo: Path) -> Path | None:
    candidate = repo / "tests"
    return candidate if candidate.is_dir() else None


def _check_mirror(
    repo: Path,
    distribution: str,
    out: list[Violation],
) -> None:
    """PS-201 / PS-202 / PS-203 / PS-204 / PS-205 — src ↔ tests mirror."""
    src_pkg = _src_pkg_dir(repo, distribution)
    tests_root = _tests_root(repo)
    if src_pkg is None or tests_root is None:
        # Without either side, mirror checks don't apply (a different rule
        # — PS-101 / future PS-105 — will catch missing structure).
        return

    import_name = _import_name(distribution)
    tests_pkg = tests_root / import_name

    # PS-201: tests/<pkg>/ must exist
    if not tests_pkg.is_dir():
        out.append(
            Violation(
                "PS-201",
                str(tests_root),
                f"missing `tests/{import_name}/` parent — needed even when most tests are flat",
            )
        )
        # Without the parent we can't run the deeper mirror checks meaningfully.
        # Still scan PS-203 / loose top-level test files.
        _check_loose_top_level_tests(tests_root, src_pkg, import_name, out)
        return

    # PS-203: any test_*.py at tests/ root that's not a known meta-test
    _check_loose_top_level_tests(tests_root, src_pkg, import_name, out)

    # Walk src/<pkg>/ — every directory with .py files needs a mirror.
    # Skip directories that aren't tracked in git (gitignored local-only
    # artifacts like src/<pkg>/app/ — they don't ship in the wheel and
    # don't need test coverage). The ignore-aware check is silent when
    # git isn't available so non-git checkouts still get flagged.
    for src_dir in [d for d in src_pkg.rglob("*") if d.is_dir() and _has_py(d)]:
        if _is_git_ignored(src_dir, repo):
            continue
        rel = src_dir.relative_to(src_pkg)
        mirror_dir = tests_pkg / rel
        if not mirror_dir.is_dir():
            out.append(
                Violation(
                    "PS-202",
                    str(src_dir),
                    f"no matching tests/{import_name}/{rel}/",
                )
            )

    # PS-205: per-file public/private prefix consistency.
    # For each src .py file, expected test name lives under tests/<pkg>/<rel>/.
    # When src has BOTH a public `foo.py` AND a private `_foo.py` in the
    # same directory (rare but legitimate — see scitex-dev dashboard), each
    # of `test_foo.py` / `test__foo.py` is the legitimate counterpart of one
    # of them. The naive "wrong_name exists" check then false-positives
    # because the OTHER variant's correct test looks misnamed for THIS one.
    # Skip the flag when both src variants exist.
    for src_file in src_pkg.rglob("*.py"):
        if src_file.name == "__init__.py":
            continue
        rel = src_file.relative_to(src_pkg)
        is_private = src_file.name.startswith("_")
        stem = src_file.stem
        if is_private:
            expected_name = f"test_{stem}.py"  # _foo.py → test__foo.py
        else:
            expected_name = f"test_{stem}.py"  # foo.py  → test_foo.py
        wrong_name = f"test_{stem.lstrip('_')}.py" if is_private else f"test__{stem}.py"
        target_dir = tests_pkg / rel.parent
        if not target_dir.is_dir():
            continue  # PS-202 already flagged this
        # Both-variant guard: if the "other" src file also exists, the file
        # at wrong_path is its legitimate test, not a misnamed copy of ours.
        if is_private:
            other_src = src_file.with_name(src_file.name[1:])  # strip leading _
        else:
            other_src = src_file.with_name(f"_{src_file.name}")
        if other_src.is_file():
            continue
        wrong_path = target_dir / wrong_name
        if wrong_path.is_file():
            out.append(
                Violation(
                    "PS-205",
                    str(wrong_path),
                    (
                        f"private `{rel.name}` should be tested by `{expected_name}` "
                        f"(double underscore), not `{wrong_name}`"
                        if is_private
                        else f"public `{rel.name}` should be `{expected_name}` "
                        f"(single underscore), not `{wrong_name}`"
                    ),
                )
            )

    # PS-204: orphan test files — every test_*.py under tests/<pkg>/ should
    # have a matching src counterpart. Hinter is built once and reused so
    # the basename index is amortized across all orphans in this package.
    from ._check_orphan_hint import build_orphan_hinter

    _hint = build_orphan_hinter(src_pkg, repo)
    for test_file in tests_pkg.rglob("test_*.py"):
        rel = test_file.relative_to(tests_pkg)
        if not _test_has_src_match(test_file, rel, src_pkg):
            out.append(Violation("PS-204", str(test_file), _hint(rel)))


def _has_py(d: Path) -> bool:
    """True iff this dir has at least one .py file (excluding __init__)."""
    if not d.is_dir():
        return False
    for child in d.iterdir():
        if child.is_file() and child.suffix == ".py" and child.name != "__init__.py":
            return True
    return False


def _is_git_ignored(path: Path, repo: Path) -> bool:
    """True iff `path` is gitignored relative to `repo`.

    Returns False when git is unavailable or the path isn't inside a git
    repo — non-git checkouts (sdist installs, tarball extracts) still
    get full PS-202 coverage. Used to skip src subdirs that exist locally
    but won't ship in the wheel (e.g. src/<pkg>/app/ if it's listed in
    .gitignore as a developer-only scratch area).
    """
    import shutil
    import subprocess

    git = shutil.which("git")
    if git is None or not (repo / ".git").exists():
        return False
    try:
        result = subprocess.run(
            [git, "-C", str(repo), "check-ignore", "--quiet", str(path)],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    # check-ignore exits 0 when the path IS ignored, 1 when it isn't,
    # 128 on any other error. Only treat exit 0 as "ignored".
    return result.returncode == 0


def _check_loose_top_level_tests(
    tests_root: Path,
    src_pkg: Path,
    import_name: str,
    out: list[Violation],
) -> None:
    """PS-203 — loose test_*.py at tests/ root that should be under tests/<pkg>/."""
    for child in tests_root.iterdir():
        if not child.is_file() or not child.name.startswith("test_"):
            continue
        if child.name in _META_TESTS_AT_ROOT:
            continue
        # Try to find a src counterpart so we can suggest where to move it.
        suggestion = _suggest_test_location(child.name, src_pkg, import_name)
        out.append(
            Violation(
                "PS-203",
                str(child),
                suggestion or f"move under tests/{import_name}/...",
            )
        )


def _suggest_test_location(
    test_name: str, src_pkg: Path, import_name: str
) -> str | None:
    """Return a hint like 'move to tests/<pkg>/<rel>/<test>.py' if we can find
    a source counterpart, else None."""
    m = _PRIVATE_TEST_RE.match(test_name)
    if m:
        target_stem = "_" + m.group(1)
    else:
        m = _PUBLIC_TEST_RE.match(test_name)
        if not m:
            return None
        target_stem = m.group(1)
    for src_file in src_pkg.rglob(f"{target_stem}.py"):
        rel = src_file.relative_to(src_pkg).parent
        return f"move to tests/{import_name}/{rel}/{test_name}".rstrip("/")
    return None


def _test_has_src_match(test_file: Path, rel: Path, src_pkg: Path) -> bool:
    """Does the test name correspond to an existing src file under the
    same rel dir?

    Direct match: ``test__foo.py`` ↔ ``_foo.py``,
                  ``test_foo.py``  ↔  ``foo.py``.

    Descriptor suffix: ``test__foo_real.py``, ``test__foo_branches.py``,
    ``test__foo_round_trip.py`` etc. — when the literal candidate is
    missing, strip trailing ``_<descriptor>`` segments and try again so
    a single src file can host multiple themed test modules without
    tripping the orphan rule.
    """
    name = test_file.name

    def _direct(stem: str, prefix: str) -> bool:
        return (src_pkg / rel.parent / f"{prefix}{stem}.py").is_file()

    def _with_descriptor_strip(stem: str, prefix: str) -> bool:
        # Greedy strip from the right: foo_round_trip → foo_round → foo.
        parts = stem.split("_")
        while len(parts) > 1:
            parts.pop()
            if _direct("_".join(parts), prefix):
                return True
        return False

    m = _PRIVATE_TEST_RE.match(name)
    if m:
        stem = m.group(1)
        return _direct(stem, "_") or _with_descriptor_strip(stem, "_")
    m = _PUBLIC_TEST_RE.match(name)
    if m:
        stem = m.group(1)
        return _direct(stem, "") or _with_descriptor_strip(stem, "")
    return False  # malformed test name — caller may flag separately


def _check_tests_subdir_convention(
    repo: Path, distribution: str, out: list[Violation]
) -> None:
    """PS-301 / PS-302 / PS-303 — tests/ root layout."""
    # PS-301: top-level htmlcov/ should be tests/coverage/.
    if (repo / "htmlcov").is_dir():
        out.append(
            Violation(
                "PS-301",
                str(repo / "htmlcov"),
                "rename to tests/coverage/ and gitignore (replaces top-level ./htmlcov/)",
            )
        )

    tests_root = _tests_root(repo)
    if tests_root is None:
        return

    # PS-302: every subdir at tests/ root must be either tests/<pkg>/ (the
    # package mirror) or one of the known categories.
    import_name = _import_name(distribution)
    for child in tests_root.iterdir():
        if not child.is_dir():
            continue
        if child.name == import_name:
            continue
        if child.name in _KNOWN_TEST_SUBDIRS:
            continue
        if _is_blacklisted(child, tests_root):
            continue  # transient junk; ignore
        out.append(
            Violation(
                "PS-302",
                str(child),
                f"unrecognized: rename to tests/{import_name}/{child.name}/ "
                "or move to one of the known categories",
            )
        )

    # PS-303: every examples/<file> should have a matching tests/examples/test_<stem>.py.
    examples_dir = repo / "examples"
    tests_examples = tests_root / "examples"
    if examples_dir.is_dir():
        for ex in examples_dir.iterdir():
            if not ex.is_file():
                continue
            if ex.suffix not in {".py", ".sh", ".ipynb"}:
                continue
            if ex.name.startswith("00_run_all"):
                continue  # dispatcher — not a demo file
            if _is_blacklisted(ex, examples_dir):
                continue
            expected = tests_examples / f"test_{ex.stem}.py"
            if not expected.is_file():
                out.append(
                    Violation(
                        "PS-303",
                        str(ex),
                        f"missing matching tests/examples/test_{ex.stem}.py",
                    )
                )


def _check_placeholder_tests(repo: Path, out: list[Violation]) -> None:
    """PS-206 + PS-206b — placeholder-only / import-smoke-only test detection.

    PS-206 (ERROR): file has no `def test_*` / `class Test*` / `test_x = factory()`
    at all — pytest will not collect anything from it.

    PS-206b (WARN): file has a collectable test but no assertion-like call in
    the entire module. Catches the auto-generated importlib smoke pattern:

        def test_module_imports():
            importlib.import_module("scitex_db._foo")

    which passes PS-202 (mirror exists) + PS-206 (test fn present) without
    exercising any behaviour.
    """
    tests_root = _tests_root(repo)
    if tests_root is None:
        return
    has_def_or_class_re = re.compile(
        # Accept `def test_*`, `async def test_*`, or `class Test*`.
        r"^\s*(?:async\s+)?(def\s+test_|class\s+Test)",
        re.MULTILINE,
    )
    has_factory_assign_re = re.compile(r"^test_[A-Za-z0-9_]*\s*=", re.MULTILINE)
    # Any of these counts as "exercises behaviour":
    # - bare `assert ...`
    # - pytest.raises / pytest.warns
    # - unittest TestCase.assertX (assertEqual, assertTrue, etc.)
    # - mock assertions (.assert_called*, .assert_not_called)
    # - hypothesis property-test entry (`@given(...)` implies real assertions
    #   inside the function body, even when the assert keyword isn't used)
    has_assertion_re = re.compile(
        r"\bassert\b"
        r"|pytest\.raises\("
        r"|pytest\.warns\("
        r"|self\.assert[A-Z][A-Za-z]*\("
        r"|\.assert_called(_with|_once[A-Za-z_]*|_)?\("
        r"|\.assert_not_called\("
        r"|@given\("
    )
    # Opt-out marker for legitimate import-smoke tests (rare — e.g. .ipynb-only
    # examples mirrored as smoke). Place this comment anywhere in the file.
    optout_re = re.compile(r"#\s*PS-206b:\s*import-smoke-allowed", re.IGNORECASE)
    for test_file in tests_root.rglob("test_*.py"):
        if _is_blacklisted(test_file, tests_root):
            continue
        try:
            text = test_file.read_text(errors="ignore")
        except OSError:
            continue
        # Strip the legacy "source-as-comment" block so it doesn't count.
        marker = "# Start of Source Code from:"
        if marker in text:
            text = text.split(marker, 1)[0]
        has_test = has_def_or_class_re.search(text) or has_factory_assign_re.search(
            text
        )
        if not has_test:
            out.append(
                Violation(
                    "PS-206",
                    str(test_file),
                    "placeholder-only — add `def test_*`, `class Test*`, or `test_x = factory()`",
                )
            )
            continue
        # PS-206b: has a test fn, but no assertion anywhere in the module.
        if optout_re.search(text):
            continue
        if not has_assertion_re.search(text):
            out.append(
                Violation(
                    "PS-206b",
                    str(test_file),
                    (
                        "import-smoke-only — has `def test_*` but no assertion "
                        "(`assert`, `pytest.raises`, `mock.assert_*`, "
                        "`self.assertX`, `@given`). Add a real check or "
                        "delete the file. Opt-out: add a "
                        "`# PS-206b: import-smoke-allowed` comment."
                    ),
                )
            )


def _check_empty_test_dirs(repo: Path, distribution: str, out: list[Violation]) -> None:
    """PS-207 — empty test mirror directory.

    Flags a `tests/<pkg>/<sub>/` that exists but contains no `test_*.py`
    files, WHEN the corresponding `src/<pkg>/<sub>/` does have source
    files. This catches partial migrations (mirror dir created, never
    filled) without false-flagging fresh packages whose `tests/<pkg>/`
    is legitimately empty because no source has been written yet.
    """
    tests_root = repo / "tests"
    if not tests_root.is_dir():
        return

    src_pkg = _src_pkg_dir(repo, distribution)
    if src_pkg is None:
        return  # no src to mirror against

    skip = {"__pycache__", "coverage", "htmlcov", ".pytest_cache"}
    for sub in tests_root.rglob("*"):
        if not sub.is_dir():
            continue
        if any(part in skip for part in sub.parts):
            continue

        # Has any .py test file? (skip __init__.py — it's pytest infra)
        py_files = [
            p
            for p in sub.iterdir()
            if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
        ]
        if py_files:
            continue
        # Has child dirs? leaf-emptiness check propagates via recursion
        child_dirs = [c for c in sub.iterdir() if c.is_dir() and c.name not in skip]
        if child_dirs:
            continue

        # Only flag if a corresponding src/<pkg>/<sub>/ has source files.
        # Resolve sub's path relative to tests/<pkg>/.
        try:
            rel = sub.relative_to(tests_root / src_pkg.name)
        except ValueError:
            continue  # not under tests/<pkg>/, leave to other rules
        src_counterpart = src_pkg / rel
        if not src_counterpart.is_dir():
            continue
        if _is_git_ignored(src_counterpart, repo):
            continue  # src is gitignored — won't ship; no test mirror needed
        src_py = [
            p
            for p in src_counterpart.iterdir()
            if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
        ]
        if not src_py:
            continue  # nothing in src to mirror — empty test dir is fine

        out.append(
            Violation(
                "PS-207",
                str(sub),
                f"empty test directory mirrors {src_counterpart} ({len(src_py)} src "
                f"files) — move corresponding test_*.py files in or remove the dir.",
            )
        )


def _check_docs_structure(repo: Path, out: list[Violation]) -> None:
    """PS-401 / PS-402 — docs/ layout."""
    docs = repo / "docs"
    to_claude = docs / "to_claude"
    if to_claude.is_dir():
        # Tracked iff git knows about any file under it. Use a conservative
        # heuristic: if the dir exists AND .gitignore doesn't ignore it, flag.
        gitignore = repo / ".gitignore"
        ignored = False
        if gitignore.is_file():
            patterns = gitignore.read_text(errors="ignore").splitlines()
            for raw in patterns:
                pat = raw.strip()
                if not pat or pat.startswith("#"):
                    continue
                if pat in {"docs/to_claude", "docs/to_claude/", "**/to_claude/"}:
                    ignored = True
                    break
        if not ignored:
            out.append(
                Violation(
                    "PS-401",
                    str(to_claude),
                    "add `docs/to_claude/` (or `**/to_claude/`) to .gitignore",
                )
            )


def check_codecov_target(repo: Path, violation_cls: type, out: list) -> None:
    """PS-161: codecov.yml must pin a project/patch coverage target >= 90%.

    Skipped when codecov.yml is absent (separate rules cover codecov
    setup), when YAML parsing fails, or when the relevant key is missing.
    Fires once per below-threshold target ('project' and/or 'patch').
    """
    cfg = repo / "codecov.yml"
    if not cfg.is_file():
        return
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8", errors="replace"))
    except (OSError, yaml.YAMLError):
        return
    if not isinstance(data, dict):
        return
    try:
        status = data["coverage"]["status"]
    except (KeyError, TypeError):
        return
    if not isinstance(status, dict):
        return

    def _parse_target(raw):
        """Return (numeric_value, is_auto_or_unparseable)."""
        if isinstance(raw, (int, float)):
            return float(raw), False
        if isinstance(raw, str):
            s = raw.strip().rstrip("%").strip()
            if s.lower() in ("auto", "auto-target"):
                return None, True
            try:
                return float(s), False
            except ValueError:
                return None, False  # unparseable string → skip
        return None, False

    for kind in ("project", "patch"):
        block = status.get(kind)
        if not isinstance(block, dict):
            continue
        default = block.get("default")
        if not isinstance(default, dict):
            continue
        if "target" not in default:
            continue
        raw = default["target"]
        value, is_auto = _parse_target(raw)
        if is_auto:
            out.append(
                violation_cls(
                    "PS-161",
                    str(cfg),
                    (
                        f"codecov.yml {kind}/patch target is "
                        f"{raw!r} (< 90%) — set target: 90% so "
                        f"the bar is visible. See scitex-io "
                        f"codecov.yml for the canonical config."
                    ),
                )
            )
        elif value is not None and value < 90:
            out.append(
                violation_cls(
                    "PS-161",
                    str(cfg),
                    (
                        f"codecov.yml {kind}/patch target is "
                        f"{value:g} (< 90%) — set target: 90% so "
                        f"the bar is visible. See scitex-io "
                        f"codecov.yml for the canonical config."
                    ),
                )
            )

