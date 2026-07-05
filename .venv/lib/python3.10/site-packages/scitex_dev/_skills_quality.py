"""Compatibility shim — re-exports from `_ecosystem._skills.skills_quality`."""

from scitex_dev._ecosystem._skills.skills_quality import (
    SkillIssue,
    SkillReport,
    check_package,
    check_skill_dir,
    find_skill_dirs,
)

__all__ = [
    "SkillIssue",
    "SkillReport",
    "check_package",
    "check_skill_dir",
    "find_skill_dirs",
]
