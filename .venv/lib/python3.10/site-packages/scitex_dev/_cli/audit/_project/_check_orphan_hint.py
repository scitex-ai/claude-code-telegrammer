"""PS-204 enrichment — derive an actionable hint when a test is orphaned.

Strategy (no git, no history walking):

1. **Same-basename match.** Refactors usually preserve the leaf filename
   (`_cli_audit.py` → `_cli/audit.py` keeps `audit`). If exactly one src
   file under `src/<pkg>/` matches the test's expected basename, suggest
   moving the test to mirror it.

2. **Sibling listing (fallback).** If no unique basename match, list the
   `.py` files that *do* live under `src/<pkg>/<test's-mirror-dir>/` so
   the agent can correlate manually. An empty mirror dir is itself a
   useful signal.

Pure stdlib, deterministic, works on uncommitted file moves.

File discovery is `fd`-preferred (fast) but degrades loudly to a stdlib
walk when `fd` is absent (see `.._fd.fd_find_files`). A repo may opt into
strict-fd via `.scitex/dev/config.yaml` `audit.require-fd: true` or
pyproject `[tool.scitex_dev] audit.require_fd` — then fd-absence raises
`FdNotFoundError` instead of falling back. The resolver mirrors
`_summary._mcp_parity.is_mcp_parity_exempt`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .._fd import fd_find_files


_DEFAULT_DETAIL = "no matching src file (orphan test)"
_MAX_SIBLINGS = 6


# --------------------------------------------------------------------- #
# require-fd strict knob — per-repo opt-in (mirrors is_mcp_parity_exempt) #
# --------------------------------------------------------------------- #

_TOOL_BLOCK_RE = re.compile(
    r"^\[tool\.scitex[_-]dev\](.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
# pyproject: [tool.scitex_dev] with `require_fd = true` (flat) or
# `audit.require_fd = true` (dotted) — accept both spellings.
_REQUIRE_FD_RE = re.compile(
    r"^\s*(?:audit\.)?require_fd\s*=\s*true\s*$",
    re.MULTILINE | re.IGNORECASE,
)
# .scitex/dev/config.yaml: audit.require-fd: true
_YAML_REQUIRE_FD_RE = re.compile(
    r"^\s*require-fd\s*:\s*true\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def is_require_fd(repo: Path | None) -> bool:
    """Return True when `repo` opts into strict-fd (fail loud when fd absent).

    pyproject.toml ``[tool.scitex_dev] audit.require_fd = true`` is the
    primary; ``.scitex/dev/config.yaml`` ``audit.require-fd: true`` is
    honored for convention parity. Either form makes the orphan-hinter's
    file discovery raise `FdNotFoundError` instead of warning + falling
    back to the stdlib walk.

    Parameters
    ----------
    repo
        Repo root being audited. When None, returns False (no opt-in).
    """
    if repo is None:
        return False

    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        try:
            txt = pyproject.read_text(errors="ignore")
        except OSError:
            txt = ""
        m = _TOOL_BLOCK_RE.search(txt)
        if m is not None and _REQUIRE_FD_RE.search(m.group(1)):
            return True

    cfg = repo / ".scitex" / "dev" / "config.yaml"
    if cfg.is_file():
        try:
            cfg_txt = cfg.read_text(errors="ignore")
        except OSError:
            cfg_txt = ""
        if _YAML_REQUIRE_FD_RE.search(cfg_txt):
            return True

    return False


def _expected_src_basename(test_filename: str) -> str | None:
    """test_foo.py → foo.py; test__foo.py → _foo.py; else None."""
    if not test_filename.startswith("test_") or not test_filename.endswith(".py"):
        return None
    return test_filename[len("test_") :]  # keeps the leading "_" for private tests


def _index_src_basenames(src_pkg: Path, *, require_fd: bool) -> dict[str, list[Path]]:
    """{basename: [absolute paths]} for every .py under src_pkg (excl. __init__).

    `src_pkg` is resolved to an absolute path up front so the index keys
    anchor to the same root as the discovered files — `fd_find_files`
    always yields absolute paths, so a *relative* `src_pkg` would make
    downstream ``Path.relative_to(src_pkg)`` mix relative-vs-absolute
    bases and raise ``ValueError``.
    """
    src_pkg = src_pkg.resolve()
    index: dict[str, list[Path]] = defaultdict(list)
    for p in fd_find_files(src_pkg, glob="*.py", require_fd=require_fd):
        if p.name == "__init__.py":
            continue
        index[p.name].append(p)
    return index


def build_orphan_hinter(src_pkg: Path, repo: Path):
    """Return a `hint(test_file, test_relpath) -> str` closure.

    Indexing happens once per audit so the per-orphan call is O(1).
    File discovery is `fd`-preferred; absence warns + falls back to the
    stdlib walk unless this `repo` opts into strict-fd (`audit.require-fd`),
    in which case fd-absence raises `FdNotFoundError`.

    `src_pkg` and `repo` are normalized to absolute paths up front so every
    ``Path.relative_to(...)`` below operates on consistently-absolute bases.
    `fd_find_files` (and its stdlib fallback) always yields absolute paths,
    so when the caller passed a *relative* ``--path`` the indexed src files
    would be absolute while ``src_pkg``/``repo`` stayed relative — and
    ``relative_to`` then raises ``ValueError`` (one path relative, the other
    absolute). The emitted hint strings keep the nice relative
    ``src/<pkg>/...`` form: they are derived from the resolved-*relative*
    results (``pkg_rel`` / ``new_src_rel``), never the absolute paths.
    """
    repo = repo.resolve()
    src_pkg = src_pkg.resolve()
    index = _index_src_basenames(src_pkg, require_fd=is_require_fd(repo))
    pkg_rel = src_pkg.relative_to(repo)

    def hint(test_relpath: Path) -> str:
        expected_basename = _expected_src_basename(test_relpath.name)
        if expected_basename is None:
            return _DEFAULT_DETAIL

        matches = index.get(expected_basename, [])
        if len(matches) == 1:
            new_src = matches[0]
            new_src_rel = new_src.relative_to(src_pkg)
            suggested_test = (
                Path("tests") / src_pkg.name / new_src_rel.parent / test_relpath.name
            )
            return (
                f"src likely moved to `{pkg_rel / new_src_rel}` "
                f"(same basename); move this test to `{suggested_test}`"
            )

        if len(matches) > 1:
            sample = ", ".join(
                str(m.relative_to(src_pkg)) for m in sorted(matches)[:_MAX_SIBLINGS]
            )
            return (
                f"no exact src match; {len(matches)} files share basename "
                f"`{expected_basename}` ({sample}) — pick the right one and "
                "relocate this test to mirror its directory"
            )

        # No basename match → list what *is* in the mirror directory.
        mirror_dir = src_pkg / test_relpath.parent
        if mirror_dir.is_dir():
            siblings = sorted(
                p.name
                for p in mirror_dir.iterdir()
                if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
            )
            if siblings:
                shown = ", ".join(siblings[:_MAX_SIBLINGS])
                more = (
                    ""
                    if len(siblings) <= _MAX_SIBLINGS
                    else f", +{len(siblings) - _MAX_SIBLINGS} more"
                )
                return (
                    f"{_DEFAULT_DETAIL}; mirror dir `{pkg_rel / test_relpath.parent}` "
                    f"contains: {shown}{more} — none match expected `{expected_basename}`"
                )
            return (
                f"{_DEFAULT_DETAIL}; mirror dir `{pkg_rel / test_relpath.parent}` "
                "exists but is empty (src may have been deleted or moved away)"
            )
        return f"{_DEFAULT_DETAIL}; mirror dir `{pkg_rel / test_relpath.parent}` does not exist"

    return hint
