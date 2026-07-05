"""Audit YAML frontmatter in SciTeX skill files against the metadata convention.

See general/06_skills_06_frontmatter-metadata.md. Warn-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from scitex_dev import try_import_optional

yaml = try_import_optional("yaml", extra="cli-audit", pkg="scitex-dev")


KNOWN_TAGS = {
    # Ecosystem-level tags
    "scitex-package",  # rules that apply to every scitex-* repo
    "scitex-general",  # general/ category in scitex-python
    "scitex-python",  # specific to the scitex-python umbrella
    "scitex-scientific",  # scientific/ category (figures, stats, reproducibility)
    # Scope tags
    "research",
    "paper",
    "infra",
    "meta",
    "scientific",
    # External reference material
    "claude-code",
}


@dataclass
class FrontmatterWarning:
    path: str
    rule: str
    message: str


def _parse_frontmatter(text: str) -> dict | None:
    """Extract the first YAML frontmatter block from a markdown file."""
    if yaml is None:
        return None
    # Skip optional HTML-comment timestamp block
    text = re.sub(r"\A<!--.*?-->\s*", "", text, count=1, flags=re.DOTALL)
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None


def _estimate_context_tokens(size_bytes: int) -> int:
    """Round((size_bytes / 4) / 100) * 100, min 100."""
    if size_bytes < 400:
        return 100
    return round(size_bytes / 4 / 100) * 100


def _audit_file(path: Path, out: list[FrontmatterWarning]) -> None:
    if path.name.startswith("."):
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    fm = _parse_frontmatter(text)
    if fm is None:
        out.append(FrontmatterWarning(str(path), "FM-0", "no YAML frontmatter found"))
        return

    # name
    if "name" not in fm:
        out.append(FrontmatterWarning(str(path), "FM-1", "missing `name` field"))

    # description
    desc = fm.get("description", "")
    if not desc:
        out.append(FrontmatterWarning(str(path), "FM-2", "missing `description` field"))
    elif len(desc) < 200:
        out.append(
            FrontmatterWarning(
                str(path),
                "FM-2",
                f"description is weak ({len(desc)} chars) — aim for ≥ 200",
            )
        )

    # canonical-location
    canon = fm.get("canonical-location")
    expected = str(path).split("/proj/", 1)[-1] if "/proj/" in str(path) else None
    if expected and canon != expected:
        out.append(
            FrontmatterWarning(
                str(path),
                "FM-3",
                f"canonical-location `{canon}` != actual `{expected}`",
            )
        )

    # context_tokens drift — per-file only
    size = path.stat().st_size
    expected_tokens = _estimate_context_tokens(size)
    declared = fm.get("context_tokens")
    if declared is not None:
        drift = abs(declared - expected_tokens) / max(expected_tokens, 1)
        if drift > 0.20:
            out.append(
                FrontmatterWarning(
                    str(path),
                    "FM-4",
                    f"context_tokens declared {declared} but estimate is {expected_tokens} (drift {drift:.0%})",
                )
            )

    # context_tokens_total — applies only to SKILL.md indexes; sums every sibling .md
    total = fm.get("context_tokens_total")
    if total is not None and path.name == "SKILL.md":
        bundle_bytes = sum(
            p.stat().st_size for p in path.parent.rglob("*.md") if p.is_file()
        )
        expected_total = _estimate_context_tokens(bundle_bytes)
        drift = abs(total - expected_total) / max(expected_total, 1)
        if drift > 0.20:
            out.append(
                FrontmatterWarning(
                    str(path),
                    "FM-4",
                    f"context_tokens_total declared {total} but bundle estimate is {expected_total} (drift {drift:.0%})",
                )
            )

    # tags sanity (legacy `group:` also accepted during migration)
    tags = fm.get("tags") or fm.get("group") or []
    if isinstance(tags, str):
        tags = [tags]
    for t in tags:
        if t not in KNOWN_TAGS:
            out.append(
                FrontmatterWarning(
                    str(path),
                    "FM-5",
                    f"tag `{t}` not in KNOWN_TAGS — either document it in "
                    f"06_skills_06_frontmatter-metadata.md or rename",
                )
            )
    if fm.get("group") is not None and fm.get("tags") is None:
        out.append(
            FrontmatterWarning(
                str(path),
                "FM-6",
                "legacy `group:` field — rename to `tags:` (YAML-frontmatter convention)",
            )
        )


def audit_frontmatter(root: Path | str) -> int:
    """Walk `root` and audit every `.md` file's frontmatter."""
    import click

    if yaml is None:
        click.echo(
            "pyyaml not installed. Install with: pip install 'scitex-dev[cli-audit]'",
            err=True,
        )
        return 2

    root = Path(root).resolve()
    if not root.is_dir():
        click.echo(f"not a directory: {root}", err=True)
        return 2

    out: list[FrontmatterWarning] = []
    for md in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in md.parts):
            continue
        if any(part in {"GITIGNORED", "_archive", ".old"} for part in md.parts):
            continue
        _audit_file(md, out)

    if not out:
        click.echo(f"ok  {root}: no frontmatter violations")
        return 0

    click.echo(f"warn  {root}: {len(out)} warning(s)")
    for w in out:
        rel = Path(w.path).relative_to(root) if w.path.startswith(str(root)) else w.path
        click.echo(f"  [{w.rule}] {rel}: {w.message}")
    return 0
