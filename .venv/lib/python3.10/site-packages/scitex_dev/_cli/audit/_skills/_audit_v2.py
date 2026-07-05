"""Spec-v2 rules: SK-105–SK-111 (file presence, conditional) and SK-705–SK-711
(frontmatter shape, partially auto-fixable).

Kept separate from `_audit.py` so the legacy file stays close to its size
budget. Imported and orchestrated by `_audit.audit_skills`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ...._ecosystem._skills import skills_audit_core as _core


@dataclass(frozen=True)
class V2Rule:
    code: str
    section: str
    message: str


V2_RULES: dict[str, V2Rule] = {
    r.code: r
    for r in [
        # §1 — File presence (conditional)
        V2Rule("SK-105", "§1", "missing mandatory `01_installation.md`"),
        V2Rule("SK-106", "§1", "missing mandatory `02_quick-start.md`"),
        V2Rule(
            "SK-107", "§1", "missing `03_python-api.md` (package exposes public API)"
        ),
        V2Rule(
            "SK-108", "§1", "missing `04_cli-reference.md` ([project.scripts] non-empty)"
        ),
        V2Rule("SK-109", "§1", "missing `05_mcp-tools.md` (MCP entry-point present)"),
        V2Rule("SK-110", "§1", "missing `06_http-api.md` (HTTP framework imported)"),
        V2Rule(
            "SK-111",
            "§1",
            "missing `20_env-vars.md` (SCITEX_<MOD>_* env vars referenced)",
        ),
        # §FM — Frontmatter shape
        V2Rule(
            "SK-705", "§FM", "leaf MUST NOT carry `name:` field (filename = identity)"
        ),
        V2Rule(
            "SK-706",
            "§FM",
            "SKILL.md `description:` must contain inline markers `[WHAT]`, `[WHEN]`, `[HOW]`",
        ),
        V2Rule("SK-708", "§FM", "SKILL.md `name:` does not equal pip-name"),
        V2Rule("SK-709", "§FM", "SKILL.md `tags:` must equal exactly `[scitex-<pkg>]`"),
        V2Rule(
            "SK-710", "§FM", "leaf `tags[0]` must equal canonical `scitex-<pkg>-<slug>`"
        ),
        V2Rule(
            "SK-711",
            "§FM",
            "leaf `description:` must contain inline markers `[TOPIC]` and `[DETAILS]`",
        ),
    ]
}


# ---------------------------------------------------------------------------
# Helpers shared with _audit.Violation by duck-typing — caller wraps results.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Rule checks. Each returns a list of (code, where, detail) tuples.
# ---------------------------------------------------------------------------


def check_file_presence(
    skills_dir: Path,
    distribution: str,
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    import_name = distribution.replace("-", "_")
    pkg_root = _core.find_package_root(skills_dir)

    def _missing(code: str, fname: str) -> None:
        out.append((code, str(skills_dir), f"expected `{fname}`"))

    if not (skills_dir / "01_installation.md").is_file():
        _missing("SK-105", "01_installation.md")
    if not (skills_dir / "02_quick-start.md").is_file():
        _missing("SK-106", "02_quick-start.md")

    pyproject = _core.load_pyproject(pkg_root) if pkg_root else {}

    # SK-107 — public API
    api = _core.has_public_python_api(import_name)
    if api is True and not (skills_dir / "03_python-api.md").is_file():
        _missing("SK-107", "03_python-api.md")

    # SK-108 — CLI scripts
    if pkg_root and _core.has_cli_scripts(pyproject):
        if not (skills_dir / "04_cli-reference.md").is_file():
            _missing("SK-108", "04_cli-reference.md")

    # SK-109 — MCP
    if pkg_root and _core.has_mcp_entry(pyproject, import_name):
        if not (skills_dir / "05_mcp-tools.md").is_file():
            _missing("SK-109", "05_mcp-tools.md")

    # SK-110 — HTTP
    if pkg_root and _core.has_http_imports(pkg_root):
        if not (skills_dir / "06_http-api.md").is_file():
            _missing("SK-110", "06_http-api.md")

    # SK-111 — env vars
    if pkg_root and _core.has_envvar_refs(pkg_root, distribution):
        if not (skills_dir / "20_env-vars.md").is_file():
            _missing("SK-111", "20_env-vars.md")

    return out


def _normalize_tags_field(tags) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        return [tags]
    if isinstance(tags, (list, tuple)):
        return [str(t) for t in tags]
    return []


def check_skill_md_frontmatter(
    skill_md: Path, distribution: str
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    data, _block, _body, _text = _core.parse_frontmatter_yaml(skill_md)
    if data is None:
        return out  # SK-701 covers missing/unparseable

    # SK-706 — description contains [WHAT]/[WHEN]/[HOW] markers
    desc = str(data.get("description") or "")
    missing_markers = [m for m in ("[WHAT]", "[WHEN]", "[HOW]") if m not in desc]
    if missing_markers:
        out.append(
            (
                "SK-706",
                str(skill_md),
                f"description missing markers: {', '.join(missing_markers)}",
            )
        )

    # SK-708 — name == pip-name
    name = data.get("name")
    if name != distribution:
        out.append(("SK-708", str(skill_md), f"name={name!r} != {distribution!r}"))

    # SK-709 — tags equals exactly [scitex-<pkg>]
    tags = _normalize_tags_field(data.get("tags"))
    if tags != [distribution]:
        out.append(
            (
                "SK-709",
                str(skill_md),
                f"tags={tags!r}, expected [{distribution!r}]",
            )
        )

    return out


def check_leaf_frontmatter(leaf: Path, distribution: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    data, _block, _body, _text = _core.parse_frontmatter_yaml(leaf)
    if data is None:
        return out

    # SK-705 — leaf must NOT have `name:`
    if "name" in data:
        out.append(("SK-705", str(leaf), "leaf carries forbidden `name:` field"))

    # SK-711 — description contains [TOPIC] and [DETAILS] markers
    desc = str(data.get("description") or "")
    missing_markers = [m for m in ("[TOPIC]", "[DETAILS]") if m not in desc]
    if missing_markers:
        out.append(
            (
                "SK-711",
                str(leaf),
                f"description missing markers: {', '.join(missing_markers)}",
            )
        )

    # SK-710 — tags[0] equals scitex-<pkg>-<slug>
    tags = _normalize_tags_field(data.get("tags"))
    expected_tag = f"{distribution}-{_core.slug_from_filename(leaf.name)}"
    if not tags or tags[0] != expected_tag:
        out.append(
            (
                "SK-710",
                str(leaf),
                f"tags[0]={tags[0] if tags else None!r}, expected {expected_tag!r}",
            )
        )

    return out


# ---------------------------------------------------------------------------
# --fix mode
# ---------------------------------------------------------------------------


_BLOCK_LITERAL_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*[|>][+-]?\s*$")
_SCALAR_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:")


def _fm_lines(block: str) -> list[str]:
    return block.split("\n")


def _find_key_span(lines: list[str], key: str) -> tuple[int, int] | None:
    """Return (start_idx, end_idx_exclusive) of a key's lines in frontmatter.

    Handles both scalar (`key: value`) and block-literal (`key: |\\n  ...`).
    """
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _SCALAR_KEY_RE.match(line)
        if m and m.group(1) == key:
            # Block scalar?
            if _BLOCK_LITERAL_KEY_RE.match(line):
                end = i + 1
                while end < len(lines):
                    nxt = lines[end]
                    if nxt.strip() == "":
                        end += 1
                        continue
                    # Continuation if indented; key starts at col 0 for top-level
                    if re.match(r"^\s+\S", nxt):
                        end += 1
                        continue
                    break
                return i, end
            return i, i + 1
        i += 1
    return None


def _replace_key_value(block: str, key: str, value: str) -> str:
    """Replace key's value (single-line scalar form). Append if absent.

    `value` is written as a JSON-safe double-quoted string when it contains
    YAML-tricky chars (`:`, `#`, `[`, `{`, leading whitespace, quotes), else
    bare. For descriptions we always quote to be safe.
    """
    lines = _fm_lines(block)
    span = _find_key_span(lines, key)
    quoted = _yaml_quote(value)
    new_line = f"{key}: {quoted}"
    if span is None:
        # Append to the end of the block
        return block.rstrip("\n") + "\n" + new_line
    start, end = span
    return "\n".join(lines[:start] + [new_line] + lines[end:])


def _yaml_quote(value: str) -> str:
    """Always double-quote with backslash-escapes for safety in single-line FM."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _delete_key(block: str, key: str) -> str:
    lines = _fm_lines(block)
    span = _find_key_span(lines, key)
    if span is None:
        return block
    start, end = span
    return "\n".join(lines[:start] + lines[end:])


def _replace_tags(block: str, tag_list: list[str]) -> str:
    rendered = "[" + ", ".join(tag_list) + "]"
    lines = _fm_lines(block)
    span = _find_key_span(lines, "tags")
    new_line = f"tags: {rendered}"
    if span is None:
        return block.rstrip("\n") + "\n" + new_line
    start, end = span
    return "\n".join(lines[:start] + [new_line] + lines[end:])


def _write_with_block(path: Path, new_block: str, body: str) -> None:
    path.write_text(f"---\n{new_block}\n---\n{body}", encoding="utf-8")


def fix_skill_md(skill_md: Path, distribution: str, codes: set[str]) -> set[str]:
    """Apply auto-fixable rules. Returns the set of codes actually fixed."""
    data, block, body, _ = _core.parse_frontmatter_yaml(skill_md)
    if data is None:
        return set()
    fixed: set[str] = set()
    new_block = block

    if "SK-709" in codes:
        new_block = _replace_tags(new_block, [distribution])
        fixed.add("SK-709")

    if new_block != block:
        _write_with_block(skill_md, new_block, body)
    return fixed


def fix_leaf(leaf: Path, distribution: str, codes: set[str]) -> set[str]:
    data, block, body, _ = _core.parse_frontmatter_yaml(leaf)
    if data is None:
        return set()
    fixed: set[str] = set()
    new_block = block

    if "SK-705" in codes and "name" in data:
        new_block = _delete_key(new_block, "name")
        fixed.add("SK-705")

    if "SK-710" in codes:
        existing = _normalize_tags_field(data.get("tags"))
        canonical = f"{distribution}-{_core.slug_from_filename(leaf.name)}"
        # Strip any prior occurrences of canonical, then prepend
        rest = [t for t in existing if t != canonical]
        new_tags = [canonical, *rest]
        new_block = _replace_tags(new_block, new_tags)
        fixed.add("SK-710")

    if new_block != block:
        _write_with_block(leaf, new_block, body)
    return fixed
