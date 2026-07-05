"""Shared, side-effect-free helpers for skill-directory auditors.

Two public auditors live above this module:

* `_skills_quality` — repo-rooted, used by downstream `tests/test_skills_quality.py`.
* `_cli_audit_skills._audit` — distribution-rooted CLI auditor.

They wrap the same underlying checks in different report shapes (`SkillIssue`
vs `Violation`) and use different rule code styles (`§X.name` vs `SK<n>`),
so this core layer returns plain data (paths, ints, tuples) and lets each
adapter format its own violations.

Each adapter still owns its own thresholds (`INDEX_SIZE_MAX`, `LEAF_SIZE_MAX`,
…) so size-budget tuning stays decoupled.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_MD = "SKILL.md"
FORBIDDEN_SUBDIRS = frozenset({"legacy", ".old"})
SYSTEM_FILES = frozenset({"MANIFEST.md"})

# Filename prefix:
#   2-level: NN_kebab-name.md                       (e.g. 40_playground.md)
#   3-level: NN_<group>_NN_<leaf>.md                (e.g. 01_ecosystem/01_upstream-and-downstream.md)
PREFIX_RE = re.compile(
    r"^(\d{2})_[a-z0-9][a-z0-9-]*"
    r"(?:_(\d{2})_[a-z0-9][a-z0-9-]*)?"
    r"\.md$"
)
LEAF_PREFIX_RE = re.compile(r"^\d{2}_")
KEBAB_AFTER_PREFIX_RE = re.compile(r"^\d{2}_[a-z0-9]+(?:[-_][a-z0-9]+)*\.md$")


def parse_prefix(name: str) -> tuple[int, int | None] | None:
    """Return ``(group, leaf|None)`` for a valid skill leaf filename, else ``None``."""
    m = PREFIX_RE.match(name)
    if not m:
        return None
    group = int(m.group(1))
    leaf = int(m.group(2)) if m.group(2) else None
    return group, leaf


def has_numeric_prefix(name: str) -> bool:
    return bool(LEAF_PREFIX_RE.match(name))


def is_kebab_after_prefix(name: str) -> bool:
    return bool(KEBAB_AFTER_PREFIX_RE.match(name))


def iter_leaves(skills_dir: Path) -> list[Path]:
    """Return sorted sub-skill leaves (excludes ``SKILL.md`` and ``SYSTEM_FILES``)."""
    return sorted(
        p
        for p in skills_dir.iterdir()
        if p.is_file()
        and p.suffix == ".md"
        and p.name != SKILL_MD
        and p.name not in SYSTEM_FILES
    )


def file_size(path: Path) -> tuple[int, int]:
    """Return ``(bytes, line_count)``."""
    nbytes = path.stat().st_size
    nlines = path.read_text(errors="replace").count("\n")
    return nbytes, nlines


def find_forbidden_subdirs(skills_dir: Path) -> list[Path]:
    return [
        p for p in skills_dir.iterdir() if p.is_dir() and p.name in FORBIDDEN_SUBDIRS
    ]


def find_alias_indexes(skills_dir: Path, aliases: tuple[str, ...]) -> list[Path]:
    return [skills_dir / a for a in aliases if (skills_dir / a).is_file()]


def find_orphan_leaves(skill_md: Path, skills_dir: Path) -> list[Path]:
    """Leaves whose filename does not appear in ``SKILL.md``."""
    text = skill_md.read_text(errors="replace")
    return [leaf for leaf in iter_leaves(skills_dir) if leaf.name not in text]


def find_dead_links(skill_md: Path, skills_dir: Path) -> list[str]:
    """Markdown ``.md`` links in ``SKILL.md`` whose target sibling is missing.

    Cross-directory links (containing ``/``) are skipped — they may resolve
    to another package or a sub-folder structure handled elsewhere.
    """
    text = skill_md.read_text(errors="replace")
    missing: list[str] = []
    # Require ']' immediately before '(' so we ONLY match markdown link
    # syntax `[text](url.md)` and not arbitrary parentheticals like
    # `(see [foo.md](foo.md))` which would otherwise greedily capture
    # past the inner `]` and produce a bogus "missing" target.
    for m in re.finditer(r"\]\(([^)]+\.md)\)", text):
        target = m.group(1)
        if "/" in target:
            continue
        if not (skills_dir / target).exists():
            missing.append(target)
    return missing


def find_duplicate_prefixes(skills_dir: Path) -> list[tuple[int, int | None]]:
    """Return prefix keys that appear on more than one leaf in ``skills_dir``.

    For 2-level names the key is ``(group, None)``; for 3-level names it is
    ``(group, leaf)``. Different leaves under the same group (e.g.
    ``01_ecosystem/01_*``, ``01_ecosystem/02_*``) do not collide.
    """
    keys: list[tuple[int, int | None]] = []
    for leaf in iter_leaves(skills_dir):
        k = parse_prefix(leaf.name)
        if k is not None:
            keys.append(k)
    seen: set[tuple[int, int | None]] = set()
    dupes: list[tuple[int, int | None]] = []
    for k in keys:
        if keys.count(k) > 1 and k not in seen:
            seen.add(k)
            dupes.append(k)
    return dupes


# ---------------------------------------------------------------------------
# Spec v2 helpers — pyproject probe, source scan, frontmatter YAML
# ---------------------------------------------------------------------------


_HTTP_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(?:starlette|fastapi|uvicorn)\b|import\s+(?:starlette|fastapi|uvicorn)\b)",
    re.MULTILINE,
)
_ENVVAR_RE_TEMPLATE = r"(?:os\.environ(?:\.get)?|os\.getenv|getenv)\s*[\(\[]\s*['\"]SCITEX_{mod}_[A-Z0-9_]+"


def find_package_root(skills_dir: Path) -> Path | None:
    """Walk up from `skills_dir` looking for a directory containing pyproject.toml."""
    p = skills_dir.resolve()
    for parent in [p, *p.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def load_pyproject(pkg_root: Path) -> dict:
    """Return parsed pyproject.toml dict, or {} on failure."""
    try:
        try:
            import tomllib  # py3.11+
        except ImportError:
            import tomli as tomllib  # type: ignore
        with (pkg_root / "pyproject.toml").open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def has_public_python_api(import_name: str) -> bool | None:
    """Return True/False if determinable, else None (unknown -> skip rule)."""
    try:
        import importlib

        mod = importlib.import_module(import_name)
    except Exception:
        return None
    all_ = getattr(mod, "__all__", None)
    if isinstance(all_, (list, tuple)):
        if len(all_) > 0:
            return True
    # Fall back: any non-underscore attr at module level (excl. submodules/builtins)
    for name in dir(mod):
        if not name.startswith("_"):
            return True
    return False


def has_cli_scripts(pyproject: dict) -> bool:
    return bool(pyproject.get("project", {}).get("scripts"))


def has_mcp_entry(pyproject: dict, import_name: str) -> bool:
    eps = pyproject.get("project", {}).get("entry-points", {})
    if eps.get("mcp.servers"):
        return True
    # Fallback: try importing <pkg>._mcp_server
    try:
        import importlib

        importlib.import_module(f"{import_name}._mcp_server")
        return True
    except Exception:
        return False


def _iter_py_sources(pkg_root: Path):
    src = pkg_root / "src"
    base = src if src.is_dir() else pkg_root
    for p in base.rglob("*.py"):
        # Skip caches/legacy
        parts = set(p.parts)
        if "__pycache__" in parts or ".old" in parts:
            continue
        yield p


def has_http_imports(pkg_root: Path) -> bool:
    for p in _iter_py_sources(pkg_root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if _HTTP_IMPORT_RE.search(text):
            return True
    return False


def has_envvar_refs(pkg_root: Path, distribution: str) -> bool:
    # MOD = distribution suffix without scitex- prefix, uppercased; or whole
    # name uppercased when no prefix.
    base = (
        distribution[len("scitex-") :]
        if distribution.startswith("scitex-")
        else distribution
    )
    mod = re.escape(base.replace("-", "_").upper())
    pat = re.compile(_ENVVAR_RE_TEMPLATE.format(mod=mod))
    for p in _iter_py_sources(pkg_root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if pat.search(text):
            return True
    return False


def parse_frontmatter_yaml(path: Path) -> tuple[dict | None, str, str, str]:
    """Return (data, frontmatter_block, body, full_text).

    `data` is None when there is no `---` block at line 1, or when YAML
    parsing fails. `frontmatter_block` is the raw text between the two `---`
    fences (without the fences); empty when no block. `body` is everything
    after the closing `---\\n`.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return None, "", text, text
    block = m.group(1)
    body = text[m.end() :]
    try:
        import yaml

        data = yaml.safe_load(block)
        if not isinstance(data, dict):
            data = None
    except Exception:
        data = None
    return data, block, body, text


def normalize_ws(s: str) -> str:
    """Collapse runs of whitespace (incl. newlines) into single spaces; strip."""
    return re.sub(r"\s+", " ", s or "").strip()


def slug_from_filename(name: str) -> str:
    """`02_quick-start.md` -> `quick-start`. Strip 2-digit prefix, suffix."""
    base = name[:-3] if name.endswith(".md") else name
    return re.sub(r"^\d{2}_", "", base).lower()
