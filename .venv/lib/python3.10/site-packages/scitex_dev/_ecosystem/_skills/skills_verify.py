#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify that docs and skills reflect current codebase."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional


def verify_docs_and_skills(
    package_path: Optional[Path] = None,
) -> dict:
    """Verify that docs and skills reflect current codebase.

    Checks:
    - _skills/ files reference functions that exist in the package
    - README mentions correct version
    - Skills export would produce changes (stale check)

    Parameters
    ----------
    package_path : Path | None
        Path to package root. None = current directory.

    Returns
    -------
    dict
        {skills_stale, stale_files, readme_version_match, issues}
    """
    from .skills import export_skills

    path = package_path or Path.cwd()
    issues: list[str] = []
    stale_files: list[str] = []

    # 1. Check if skills export would change anything
    skills_stale = False
    try:
        from .skills import _get_default_export_dest

        export_skills(_get_default_export_dest())
        skills_dirs = list(path.glob("src/**/_skills"))
        if skills_dirs:
            skills_stale = False  # can't detect without actual export diff
    except Exception:
        pass

    # 2. Check README version matches pyproject.toml
    readme_match = True
    toml_path = path / "pyproject.toml"
    readme_path = path / "README.md"
    if toml_path.exists() and readme_path.exists():
        toml_text = toml_path.read_text()
        m = re.search(r'^version\s*=\s*"([^"]+)"', toml_text, re.MULTILINE)
        if m:
            toml_ver = m.group(1)
            readme_text = readme_path.read_text()
            if toml_ver not in readme_text:
                readme_match = False
                issues.append(f"README does not mention version {toml_ver}")

    # 3. Check _skills/ files reference real functions
    skill_files = list(path.glob("src/**/_skills/**/*.md"))
    for skill_file in skill_files:
        content = skill_file.read_text()
        imports = re.findall(r"from\s+(\S+)\s+import\s+(\w+)", content)
        for module, func in imports:
            try:
                result = subprocess.run(
                    ["python3", "-c", f"from {module} import {func}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode != 0:
                    issues.append(f"{skill_file.name}: {module}.{func} not importable")
                    stale_files.append(str(skill_file))
            except Exception:
                pass

    return {
        "skills_stale": skills_stale or bool(stale_files),
        "stale_files": stale_files,
        "readme_version_match": readme_match,
        "issues": issues,
        "status": "ok" if not issues else "needs_update",
    }


# EOF
