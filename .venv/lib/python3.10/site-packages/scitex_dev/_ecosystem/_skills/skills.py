#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skills aggregation across the SciTeX ecosystem.

Each package places skills as markdown files inside its source tree::

    # New layout (preferred):
    src/<import_name>/_skills/<pip-name>/SKILL.md
    src/<import_name>/_skills/<pip-name>/sub-skill.md

    # Legacy layout (still supported):
    src/<import_name>/skills/SKILL.md
    src/<import_name>/skills/references/*.md

Export target (scitex namespace)::

    ~/.claude/skills/scitex/<pip-name>/SKILL.md
    ~/.claude/skills/scitex/<pip-name>/sub-skill.md

Usage::

    from scitex_dev import list_skills, get_skill, export_skills

    list_skills()
    list_skills(package="scitex-stats")
    get_skill(package="scitex-stats")
    get_skill(package="scitex-stats", name="test-selection")
    export_skills(Path.home() / ".claude/skills/scitex")
    export_skills(Path("skills"), source="pypi", clean=True)
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from ..._core.discovery import discover_packages, get_package_root
from ._frontmatter import _parse_frontmatter, _stamp_frontmatter_field  # noqa: F811

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "scitex_dev.skills"

_DEFAULT_EXPORT_DIR_ENV = "SCITEX_DEV_SKILLS_DEFAULT_EXPORT_DIR"


def _get_default_export_dest() -> Path:
    """Get the default export destination from env or fallback."""
    env_val = os.environ.get(_DEFAULT_EXPORT_DIR_ENV)
    if env_val:
        return Path(env_val)
    return Path.home() / ".claude" / "skills" / "scitex"


def _find_skills_dir(
    module_name: str,
    pip_name: str,
    *,
    _root_fn=None,
) -> Optional[Path]:
    """Find the skills directory for a package.

    Resolution chain:
        1. New layout: <pkg_root>/_skills/<pip-name>/
        2. Legacy layout: <pkg_root>/skills/  (has SKILL.md)
        3. Legacy docs: <pkg_root>/docs/MASTER/skills/
    """
    root_lookup = _root_fn if _root_fn is not None else get_package_root
    root = root_lookup(module_name)
    if root is None:
        return None

    # 1. New layout: _skills/<pip-name>/
    new_dir = root / "_skills" / pip_name
    if new_dir.is_dir() and (new_dir / "SKILL.md").exists():
        return new_dir

    # 2. DEPRECATED: skills/ (flat, no package-name subdir)
    legacy_dir = root / "skills"
    if legacy_dir.is_dir() and (legacy_dir / "SKILL.md").exists():
        logger.warning(
            "Package '%s' uses deprecated skills/ layout — "
            "migrate to _skills/%s/SKILL.md",
            pip_name,
            pip_name,
        )
        return legacy_dir

    # 3. DEPRECATED: docs/MASTER/skills/
    docs_dir = root / "docs" / "MASTER" / "skills"
    if docs_dir.is_dir():
        logger.warning(
            "Package '%s' uses deprecated docs/MASTER/skills/ layout — "
            "migrate to _skills/%s/SKILL.md",
            pip_name,
            pip_name,
        )
        return docs_dir

    return None


def _get_package_version(pip_name: str) -> str:
    """Get installed version for a package."""
    try:
        from importlib.metadata import version

        return version(pip_name)
    except Exception:
        return "unknown"


_SKIP_DIRS = {"__pycache__", "GITIGNORED", ".git"}


def _collect_skills_from_dir(
    skills_dir: Path,
    version: str,
) -> list[dict[str, str]]:
    """Collect skill entries recursively, preserving relative paths.

    Walks `skills_dir` recursively and records every `*.md` file. Each entry
    carries `rel_path` (relative to `skills_dir`), so the exporter can
    reproduce the directory structure under the destination.

    For the canonical `_skills/general/` use case this means the nested
    `03_interface/04_skills/00_index.md` etc. files survive the round-trip.
    Legacy flat layouts (top-level `*.md` only) keep working unchanged.
    """
    skills: list[dict[str, str]] = []
    for md_file in sorted(skills_dir.rglob("*.md")):
        # Skip hidden / generated subtrees.
        if any(
            part in _SKIP_DIRS or part.startswith(".")
            for part in md_file.relative_to(skills_dir).parts[:-1]
        ):
            continue
        rel = md_file.relative_to(skills_dir)
        rel_str = str(rel)
        # `name` keeps backward-compat semantics for top-level files; nested
        # files get their full relative path (without `.md`) as the name so
        # downstream `list_skills` / `get_skill` callers can still address them.
        if rel_str == "SKILL.md":
            name = "SKILL"
        elif "/" in rel_str:
            name = rel_str[:-3]  # strip trailing .md
        else:
            name = md_file.stem
        meta = _parse_frontmatter(md_file)
        desc = meta.get("description", "")
        if not desc and md_file.name != "SKILL.md":
            try:
                first_line = md_file.read_text().split("\n", 1)[0].strip()
                if first_line.startswith("#"):
                    desc = first_line.lstrip("#").strip()
            except Exception:
                pass
        skills.append(
            {
                "name": name,
                "path": str(md_file),
                "rel_path": rel_str,
                "description": desc,
                "version": version,
            }
        )
    return skills


def list_skills(
    package: Optional[str] = None,
    *,
    _discover_fn=None,
    _root_fn=None,
    _version_fn=None,
) -> dict[str, list[dict[str, str]]]:
    """List all skills across the ecosystem or for a specific package.

    Returns:
        Dict mapping package name -> list of skill info dicts.
        Each dict has: name, path, description, version.
    """
    discover = _discover_fn if _discover_fn is not None else discover_packages
    root_lookup = _root_fn if _root_fn is not None else get_package_root
    version_lookup = _version_fn if _version_fn is not None else _get_package_version

    packages = discover()

    if package:
        if package not in packages:
            return {}
        packages = {package: packages[package]}

    result: dict[str, list[dict[str, str]]] = {}

    for pkg_name, module_name in packages.items():
        # 1. Standard per-package skills
        skills_dir = _find_skills_dir(module_name, pkg_name, _root_fn=root_lookup)
        if skills_dir is not None:
            version = version_lookup(pkg_name)
            skills = _collect_skills_from_dir(skills_dir, version)
            if skills:
                result[pkg_name] = skills

        # 2. Extra skill namespaces (e.g., _skills/general/ in scitex-python)
        root = root_lookup(module_name)
        if root is not None:
            extra_skills_root = root / "_skills"
            if extra_skills_root.is_dir():
                version = version_lookup(pkg_name)
                for sub_dir in sorted(extra_skills_root.iterdir()):
                    if not sub_dir.is_dir():
                        continue
                    ns_name = sub_dir.name
                    # Skip the package's own name (already handled above)
                    if ns_name == pkg_name:
                        continue
                    if (sub_dir / "SKILL.md").exists():
                        extra = _collect_skills_from_dir(sub_dir, version)
                        if extra:
                            result[ns_name] = extra

    return result


def get_skill(
    package: str,
    name: Optional[str] = None,
) -> Optional[str]:
    """Get the content of a skill file.

    Args:
        package: Package name (e.g. "scitex-stats")
        name: Skill name (e.g. "test-selection"). If None, returns SKILL.md.

    Returns:
        Skill content as string, or None if not found.
    """
    packages = discover_packages()
    module_name = packages.get(package)
    if module_name is None:
        return None

    skills_dir = _find_skills_dir(module_name, package)
    if skills_dir is None:
        return None

    if name is None:
        skill_file = skills_dir / "SKILL.md"
    else:
        # Flat lookup first (new layout)
        skill_file = skills_dir / f"{name}.md"
        if not skill_file.exists():
            # Legacy: references/ subdir
            skill_file = skills_dir / "references" / f"{name}.md"

    if not skill_file.exists():
        # Fuzzy match across all locations
        search_dirs = [skills_dir]
        refs_dir = skills_dir / "references"
        if refs_dir.is_dir():
            search_dirs.append(refs_dir)
        for d in search_dirs:
            candidates = list(d.glob(f"*{name}*"))
            if candidates:
                skill_file = candidates[0]
                break
        else:
            return None

    try:
        return skill_file.read_text()
    except Exception as e:
        logger.warning("Failed to read skill %s/%s: %s", package, name, e)
        return None


def get_skill_dir(package: str) -> Optional[Path]:
    """Get the skills directory path for a package."""
    packages = discover_packages()
    module_name = packages.get(package)
    if module_name is None:
        return None
    return _find_skills_dir(module_name, package)


def export_skills(
    dest: Path,
    *,
    package: Optional[str] = None,
    clean: bool = False,
    source: str = "installed",
    link: bool = False,
    _discover_fn=None,
    _root_fn=None,
    _version_fn=None,
) -> dict[str, list[Path]]:
    """Export skills to dest. Files are written as ``<dest>/<pkg-name>/SKILL.md``.

    Args:
        dest: Exact target directory. Required, no default.
        package: Export only this package. None exports all.
        clean: If True, delete each package subdirectory in dest before
               exporting. Default False (overwrite in place).
        source: "installed" (from locally installed packages) or "pypi"
                (download wheels from PyPI and extract _skills/).
        link: If True, symlink each skill file to its editable source
              (only valid with ``source="installed"``). Edits to the
              package source are then reflected in ``dest`` immediately
              without re-running export. Incompatible with ``source="pypi"``
              since PyPI wheels are extracted to a temp dir.

    Returns:
        Dict mapping package name -> list of exported file paths.
    """
    if link and source != "installed":
        raise ValueError("link=True requires source='installed'")

    if source == "pypi":
        from .skills_pypi import export_from_pypi

        return export_from_pypi(dest=dest, package=package)

    # Clean stale dist-info to prevent importlib.metadata confusion
    from ..._core.dist_info import clean_stale_dist_info

    clean_stale_dist_info()

    all_skills = list_skills(
        package=package,
        _discover_fn=_discover_fn,
        _root_fn=_root_fn,
        _version_fn=_version_fn,
    )

    # Auto-detect editable installs: when source="installed" and --link
    # was not explicitly passed, check whether any discovered package is
    # installed in editable mode (pip install -e). If so, enable link
    # so source changes propagate immediately without re-export.
    if source == "installed" and not link:
        from ..._release.check_editable_drift import _editable_source_dir

        for pkg_name in all_skills:
            if _editable_source_dir(pkg_name) is not None:
                link = True
                break

    if clean:
        for pkg_name in all_skills:
            pkg_dir = dest / pkg_name
            # is_dir() follows symlinks; check is_symlink() first to
            # avoid rmtree-on-symlink errors when re-running with --link.
            if pkg_dir.is_symlink():
                pkg_dir.unlink()
            elif pkg_dir.is_dir():
                shutil.rmtree(pkg_dir)

    exported: dict[str, list[Path]] = {}

    for pkg_name, entries in all_skills.items():
        pkg_dest = dest / pkg_name

        # --link mode: symlink the entire package _skills/<pkg_name>/
        # directory (including nested subdirs) so any add/rename/delete
        # in source propagates immediately. Per-file symlinks (legacy)
        # miss new files until re-install.
        if link and entries:
            src_paths = [Path(e["path"]) for e in entries if Path(e["path"]).exists()]
            if src_paths:
                # Find canonical skill-tree root: walk up from any leaf
                # until we hit an ancestor named pkg_name. Handles both
                # flat layouts (one parent dir) and nested layouts like
                # general/03_interface/04_skills/12_quality-checklist.md.
                src_root = None
                for ancestor in [src_paths[0].parent, *src_paths[0].parents]:
                    if ancestor.name == pkg_name:
                        src_root = ancestor.resolve()
                        break
                if src_root and src_root.is_dir():
                    if pkg_dest.is_symlink() or pkg_dest.is_file():
                        pkg_dest.unlink()
                    elif pkg_dest.is_dir():
                        shutil.rmtree(pkg_dest)
                    pkg_dest.parent.mkdir(parents=True, exist_ok=True)
                    pkg_dest.symlink_to(src_root, target_is_directory=True)
                    exported[pkg_name] = [pkg_dest / p.name for p in src_paths]
                    continue
                # Could not resolve canonical root — fall through.

        pkg_dest.mkdir(parents=True, exist_ok=True)

        pkg_files: list[Path] = []
        for entry in entries:
            src_path = Path(entry["path"])
            if not src_path.exists():
                continue

            name = entry["name"]
            # Prefer `rel_path` (preserves nested subdirs like
            # `03_interface/04_skills/00_index.md`); fall back to flat
            # `<name>.md` for legacy entries that predate rel_path.
            rel_path = entry.get("rel_path")
            if rel_path:
                out_file = pkg_dest / rel_path
                out_file.parent.mkdir(parents=True, exist_ok=True)
            else:
                out_file = pkg_dest / ("SKILL.md" if name == "SKILL" else f"{name}.md")

            # Copy and flatten references/ paths in content
            content = src_path.read_text(encoding="utf-8")
            if name == "SKILL" and "references/" in content:
                import re

                content = re.sub(r"references/", "", content)

            # Stamp every leaf's frontmatter with the exporting package's
            # version + source. The cached copy is the single drift signal:
            # `skills get` / `skills list` compare these stamps to the
            # currently installed `importlib.metadata.version()` and warn
            # when the cache is older than what's installed.
            #
            # MANIFEST.md is forbidden by the SK-105 audit rule and is no
            # longer emitted; the per-leaf stamp replaces it.
            version = entry.get("version", "unknown")
            content = _stamp_frontmatter_field(content, "version", version)
            content = _stamp_frontmatter_field(content, "exported_via", source)

            if out_file.exists() or out_file.is_symlink():
                if out_file.is_symlink():
                    out_file.unlink()
                else:
                    out_file.chmod(0o644)

            if link:
                # Symlinking would defeat the per-leaf version stamp (the
                # source has no version field). Always write a stamped
                # copy when --link is requested AND a version stamp lands
                # in the content.
                out_file.write_text(content, encoding="utf-8")
            else:
                out_file.write_text(content, encoding="utf-8")
            pkg_files.append(out_file)

        if pkg_files:
            exported[pkg_name] = pkg_files

    # Generate root SKILL.md index
    _generate_root_skill_md(dest, exported)

    return exported


def _generate_root_skill_md(dest: Path, exported: dict[str, list[Path]]) -> None:
    """Generate a categorized SKILL.md at the scitex/ root.

    Delegated to :mod:`_skills_categories` so the long category map and
    renderer live in their own module — keeps ``skills.py`` focused on
    discovery/export and within the project's per-file line budget.
    """
    from .skills_categories import render_root_skill_md

    render_root_skill_md(dest, exported)


# Re-export from refactored modules for backward compatibility
from .skills_drift import cached_skill_version, drift_warning, installed_version  # noqa: F401
from .skills_verify import verify_docs_and_skills  # noqa: F401
