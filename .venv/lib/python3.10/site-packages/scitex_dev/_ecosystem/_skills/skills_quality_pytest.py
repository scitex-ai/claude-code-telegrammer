"""Drop-in pytest harness for per-package skill-quality tests.

Usage in a package's tests/test_skills_quality.py:

    from scitex_dev._ecosystem._skills.skills_quality_pytest import make_skill_quality_tests
    test_skills_quality = make_skill_quality_tests(package_root="..")
"""

from __future__ import annotations
from pathlib import Path
import pytest
from .skills_quality import check_package, SkillReport


def make_skill_quality_tests(package_root: str | Path):
    pkg = Path(package_root).resolve()
    reports = check_package(pkg)
    if not reports:

        def _no_skills():
            pytest.skip(f"no _skills/ under {pkg}")

        return _no_skills

    @pytest.mark.parametrize("report", reports, ids=lambda r: str(r.skill_dir.name))
    def _test(report: SkillReport):
        assert report.ok, (
            f"Skill quality violations in {report.skill_dir}:\n  - "
            + "\n  - ".join(
                f"[{i.rule}] {i.path.name}: {i.message}" for i in report.issues
            )
        )

    return _test
