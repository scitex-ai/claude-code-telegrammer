"""Programmatic checks for the SciTeX skills quality checklist.

Canonical rules: _skills/general/03_interface/04_skills/12_quality-checklist.md

Shared check helpers live in ``scitex_dev._skills_audit_core``; this module
keeps the repo-rooted SkillIssue/SkillReport API used by downstream package
CIs (``make_skill_quality_tests``).
"""

from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, field

from . import skills_audit_core as _core
from .skills_audit_core import SKILL_MD

LEAF_SIZE_MAX = 16 * 1024  # §4 — dense reference leaves can run ~12-15KB
STUB_SIZE_MIN = 300  # §4
INDEX_SIZE_MAX = 8 * 1024  # §3 — accommodates ~25 entries with descriptions
ALIAS_INDEX_NAMES = ("SKILL_INDEX.md", "INDEX.md")


@dataclass
class SkillIssue:
    rule: str  # e.g. "§2.prefix"
    path: Path
    message: str


@dataclass
class SkillReport:
    skill_dir: Path
    issues: list[SkillIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def check_skill_dir(skill_dir: Path) -> SkillReport:
    """Validate one sub-skill directory (contains SKILL.md + leaves)."""
    report = SkillReport(skill_dir=skill_dir)
    add = lambda rule, p, msg: report.issues.append(SkillIssue(rule, p, msg))

    # §1 exactly one SKILL.md
    skill_md = skill_dir / SKILL_MD
    if not skill_md.is_file():
        add("§1.index", skill_dir, "missing SKILL.md")
        return report

    # §1 no alias index
    for p in _core.find_alias_indexes(skill_dir, ALIAS_INDEX_NAMES):
        add("§1.dual-index", p, "forbidden alias index")

    # §1 no legacy / .old
    for sub in _core.find_forbidden_subdirs(skill_dir):
        add("§1.legacy-dir", sub, "forbidden legacy/.old directory shipped")

    # §3 SKILL.md size
    idx_bytes, _ = _core.file_size(skill_md)
    if idx_bytes > INDEX_SIZE_MAX:
        add("§3.index-monolith", skill_md, f"{idx_bytes}B > {INDEX_SIZE_MAX}B")

    leaves = _core.iter_leaves(skill_dir)

    # §2 prefix format
    for leaf in leaves:
        if _core.parse_prefix(leaf.name) is None:
            add("§2.prefix", leaf, "filename must match NN_kebab-name.md")

    # §2 duplicate prefixes (group-aware via core)
    for group_p, leaf_p in _core.find_duplicate_prefixes(skill_dir):
        label = f"{group_p:02d}" if leaf_p is None else f"{group_p:02d}_*_{leaf_p:02d}"
        add("§2.duplicate-prefix", skill_dir, f"prefix {label} used more than once")

    # §4 leaf size
    for leaf in leaves:
        size, _ = _core.file_size(leaf)
        if size > LEAF_SIZE_MAX:
            add("§4.monolith", leaf, f"{size}B > {LEAF_SIZE_MAX}B")
        elif size < STUB_SIZE_MIN and "TODO" not in leaf.read_text(errors="ignore"):
            add("§4.stub", leaf, f"{size}B < {STUB_SIZE_MIN}B without TODO marker")

    # §3 every leaf listed in SKILL.md
    for leaf in _core.find_orphan_leaves(skill_md, skill_dir):
        add("§3.missing-in-index", leaf, "leaf not referenced from SKILL.md")

    # §3 no dead links
    for target in _core.find_dead_links(skill_md, skill_dir):
        add("§3.dead-link", skill_md, f"SKILL.md references missing {target}")

    return report


def find_skill_dirs(package_root: Path) -> list[Path]:
    """Locate every sub-skill dir under ``<package>/src/*/_skills/*/``."""
    results: list[Path] = []
    for skills_root in (package_root / "src").glob("*/_skills"):
        for sub in skills_root.iterdir():
            if sub.is_dir() and (sub / SKILL_MD).is_file():
                results.append(sub)
    return results


def check_package(package_root: Path) -> list[SkillReport]:
    return [check_skill_dir(d) for d in find_skill_dirs(package_root)]
