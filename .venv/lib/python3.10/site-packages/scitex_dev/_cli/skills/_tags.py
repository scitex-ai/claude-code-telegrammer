"""Resolve a frontmatter `tags:` value to the set of skill files that carry it.

CLI: `scitex-dev skills tags-expand <tag>` walks every installed package's
`_skills/` tree, parses each `.md` file's frontmatter, and emits the absolute
path of files whose `tags:` array includes <tag>.

Designed to back CLAUDE.md shortcut syntax — a research project writes
`@scitex` at the top of its CLAUDE.md, a pre-processor runs
`scitex-dev skills tags-expand scitex-package` and replaces the line with
concrete `@<absolute-path>` include lines.

See general/06_skills_06_frontmatter-metadata.md §"CLAUDE.md tag shortcuts".
"""

from __future__ import annotations

import importlib.metadata as im
import re
from pathlib import Path

from scitex_dev import try_import_optional

yaml = try_import_optional("yaml", extra="cli-audit", pkg="scitex-dev")


def _parse_frontmatter(text: str) -> dict | None:
    if yaml is None:
        return None
    text = re.sub(r"\A<!--.*?-->\s*", "", text, count=1, flags=re.DOTALL)
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None


def _file_has_tag(path: Path, tag: str) -> bool:
    try:
        fm = _parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return False
    if not fm:
        return False
    tags = fm.get("tags") or fm.get("group") or []
    if isinstance(tags, str):
        tags = [tags]
    return tag in tags


def _iter_installed_skill_roots() -> list[Path]:
    """Find every `_skills/` directory shipped by an installed package."""
    roots: list[Path] = []
    seen: set[Path] = set()
    for dist in im.distributions():
        try:
            base = Path(dist.locate_file(""))
        except Exception:
            continue
        for pkg_info in dist.files or []:
            # Walk up to find .../_skills/ roots
            p = Path(str(pkg_info))
            parts = p.parts
            if "_skills" in parts:
                idx = parts.index("_skills")
                rel = Path(*parts[: idx + 1])
                full = (base / rel).resolve()
                if full.is_dir() and full not in seen:
                    seen.add(full)
                    roots.append(full)
    return roots


def _iter_ecosystem_source_roots() -> list[Path]:
    """Scan standard skill-root locations across the system.

    1. `~/proj/scitex-*/src/*/_skills/` — editable scitex-* sources.
    2. `~/.claude/skills/` — user-level Claude Code skills (ywatanabe,
       playwright-cli, claude-code-official, etc.).
    3. `<cwd>/.claude/skills/` — project-level skills for the active project.

    Safely handles missing directories.
    """
    out: list[Path] = []

    proj = Path.home() / "proj"
    if proj.is_dir():
        for pkg_dir in proj.iterdir():
            if not pkg_dir.is_dir():
                continue
            if not (
                pkg_dir.name.startswith("scitex-")
                or pkg_dir.name in {"figrecipe", "crossref-local", "openalex-local"}
            ):
                continue
            for sk in pkg_dir.rglob("_skills"):
                if sk.is_dir() and "/.venv/" not in str(sk):
                    out.append(sk.resolve())

    user_skills = Path.home() / ".claude" / "skills"
    if user_skills.is_dir():
        out.append(user_skills.resolve())

    project_skills = Path.cwd() / ".claude" / "skills"
    if project_skills.is_dir():
        out.append(project_skills.resolve())

    return out


def tags_expand(tag: str, include_source_tree: bool = True) -> int:
    """Print absolute paths of every skill `.md` whose `tags:` includes <tag>."""
    import click

    if yaml is None:
        click.echo(
            "pyyaml not installed. Install with: pip install 'scitex-dev[cli-audit]'",
            err=True,
        )
        return 2

    roots: list[Path] = _iter_installed_skill_roots()
    if include_source_tree:
        src_roots = _iter_ecosystem_source_roots()
        # De-dup by resolving through realpath
        all_resolved = {r.resolve() for r in roots}
        for s in src_roots:
            if s.resolve() not in all_resolved:
                roots.append(s)

    matches: set[Path] = set()
    for root in roots:
        for md in root.rglob("*.md"):
            if any(
                part.startswith(".") or part in {"GITIGNORED", ".old"}
                for part in md.parts
            ):
                continue
            if _file_has_tag(md, tag):
                matches.add(md.resolve())

    # Stable sort: by path
    for m in sorted(matches):
        click.echo(str(m))

    if not matches:
        click.echo(f"no files tagged `{tag}` found", err=True)
        return 1
    return 0
