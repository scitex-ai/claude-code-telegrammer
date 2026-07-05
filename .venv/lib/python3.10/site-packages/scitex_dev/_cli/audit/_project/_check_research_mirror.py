"""RP-2xx — `scripts/` ↔ `tests/scripts/` mirror for research projects.

A SciTeX *research* project (declared via `project-type: research` in
`.scitex/dev/config.yaml`) has no `src/<pkg>/` package — its primary code
lives in `./scripts/`. The mirror discipline that PS-201/PS-202/PS-204/
PS-205 enforce for packages (`src/<pkg>/` ↔ `tests/<pkg>/`) therefore
applies with `scripts/` substituted for `src/<pkg>/` and `tests/scripts/`
for `tests/<pkg>/`.

These RP rules are the research-flavoured siblings of the PS mirror rules:

| RP code | PS analogue | What it checks |
| :--- | :--- | :--- |
| RP-201 | PS-201 | `tests/scripts/` parent exists (mandatory mirror root) |
| RP-202 | PS-202 | every `scripts/<sub>/` with `.py` files has a `tests/scripts/<sub>/` |
| RP-204 | PS-204 | every `test_*.py` under `tests/scripts/` has a `scripts/` counterpart |
| RP-205 | PS-205 | public/private prefix consistency (`_foo.py` → `test__foo.py`) |

The auditor only runs these when `research` is in the project's
project-types (see `applies()` in `_config/_loader.py` — RP rules route
to research). They are independent of the PS package-publish rules,
which drop for a pure-research project (no `pip` ⇒ no `PS-*`).

Severity is W during ecosystem adoption — matches the PS-211/PS-212
warn-first precedent. Promote to E once the research repos have been
brought into compliance.
"""

from __future__ import annotations

from pathlib import Path

# Reuse the package-mirror primitives so the research mirror stays in
# lockstep with the canonical logic (the descriptor-strip orphan
# tolerance, the gitignore-aware src-dir walk).
from ._audit import (
    Violation,
    _has_py,
    _is_git_ignored,
    _test_has_src_match,
)


def check_research_mirror(repo: Path, out: list[Violation]) -> None:
    """RP-201 / RP-202 / RP-204 / RP-205 — scripts ↔ tests/scripts mirror.

    No-op when the repo has no `scripts/` directory (a research project
    without scripts has nothing to mirror; PS/other rules cover the rest).
    """
    scripts = repo / "scripts"
    tests_root = repo / "tests"
    if not scripts.is_dir():
        return

    tests_scripts = tests_root / "scripts"

    # RP-201: tests/scripts/ must exist as the mandatory mirror parent.
    if not tests_scripts.is_dir():
        out.append(
            Violation(
                "RP-201",
                str(tests_root) if tests_root.is_dir() else str(repo),
                "missing `tests/scripts/` parent — mandatory mirror of "
                "`./scripts/` for research projects",
            )
        )
        # Without the parent the deeper mirror checks can't run meaningfully.
        return

    # RP-202: every scripts/<sub>/ holding .py files needs a mirror dir.
    # Skip gitignored subdirs (local-only scratch) and the makefile dir
    # (`scripts/makefile/` holds dispatch shell scripts, not testable code).
    for src_dir in [d for d in scripts.rglob("*") if d.is_dir() and _has_py(d)]:
        if _is_git_ignored(src_dir, repo):
            continue
        rel = src_dir.relative_to(scripts)
        if rel.parts and rel.parts[0] == "makefile":
            continue
        mirror_dir = tests_scripts / rel
        if not mirror_dir.is_dir():
            out.append(
                Violation(
                    "RP-202",
                    str(src_dir),
                    f"no matching tests/scripts/{rel}/",
                )
            )

    # RP-204: orphan test files — every test_*.py under tests/scripts/
    # should have a matching scripts/ counterpart (descriptor-suffix
    # tolerant, same as PS-204).
    for test_file in tests_scripts.rglob("test_*.py"):
        rel = test_file.relative_to(tests_scripts)
        if not _test_has_src_match(test_file, rel, scripts):
            out.append(
                Violation(
                    "RP-204",
                    str(test_file),
                    f"no matching scripts/{rel.parent}/ counterpart".replace(
                        "scripts/./", "scripts/"
                    ),
                )
            )

    # RP-205: public/private prefix consistency.
    # `_foo.py` (private) → `test__foo.py`; `foo.py` (public) → `test_foo.py`.
    # When both a public `foo.py` and a private `_foo.py` live in the same
    # dir, the "wrong" name is actually the other's legitimate test — skip.
    for src_file in scripts.rglob("*.py"):
        if src_file.name == "__init__.py":
            continue
        rel = src_file.relative_to(scripts)
        if rel.parts and rel.parts[0] == "makefile":
            continue
        is_private = src_file.name.startswith("_")
        stem = src_file.stem
        expected_name = f"test_{stem}.py"
        wrong_name = f"test_{stem.lstrip('_')}.py" if is_private else f"test__{stem}.py"
        target_dir = tests_scripts / rel.parent
        if not target_dir.is_dir():
            continue  # RP-202 already flagged this
        if is_private:
            other_src = src_file.with_name(src_file.name[1:])
        else:
            other_src = src_file.with_name(f"_{src_file.name}")
        if other_src.is_file():
            continue
        wrong_path = target_dir / wrong_name
        if wrong_path.is_file():
            out.append(
                Violation(
                    "RP-205",
                    str(wrong_path),
                    (
                        f"private `{rel.name}` should be tested by "
                        f"`{expected_name}` (double underscore), not "
                        f"`{wrong_name}`"
                        if is_private
                        else f"public `{rel.name}` should be `{expected_name}` "
                        f"(single underscore), not `{wrong_name}`"
                    ),
                )
            )


__all__ = ["check_research_mirror"]
