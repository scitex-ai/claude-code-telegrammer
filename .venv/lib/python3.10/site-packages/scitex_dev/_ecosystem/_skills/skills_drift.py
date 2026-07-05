"""Version-drift detection for cached skills.

Compares the version stamp written into exported skill files against the
currently installed ``importlib.metadata.version()`` and reports staleness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ._frontmatter import _parse_frontmatter


def _get_default_export_dest() -> Path:
    """Get the default export destination from env or fallback."""
    import os

    env_val = os.environ.get("SCITEX_DEV_SKILLS_DEFAULT_EXPORT_DIR")
    if env_val:
        return Path(env_val)
    return Path.home() / ".claude" / "skills" / "scitex"


def cached_skill_version(package: str) -> Optional[str]:
    """Read the version stamp from the cached SKILL.md of ``package``.

    Returns the value of the ``version:`` frontmatter field of
    ``~/.claude/skills/scitex/<package>/SKILL.md`` (the location used by
    ``export_skills``), or None if the cache, file, or stamp is absent.
    """
    cache_root = _get_default_export_dest()
    skill_md = cache_root / package / "SKILL.md"
    if not skill_md.is_file():
        return None
    fm = _parse_frontmatter(skill_md)
    v = fm.get("version", "").strip()
    return v or None


def installed_version(package: str) -> Optional[str]:
    """Return ``importlib.metadata.version(package)`` or None if missing."""
    try:
        from importlib.metadata import version

        return version(package)
    except Exception:
        return None


def _is_older(cached: str, installed: str) -> bool:
    """Best-effort cached < installed comparison.

    Uses ``packaging.version.Version`` when available; falls back to a
    naive lexicographic compare. False means "not strictly older" — we
    only warn on confirmed staleness.
    """
    try:
        from packaging.version import Version

        return Version(cached) < Version(installed)
    except Exception:
        return cached != installed and cached < installed


def drift_warning(package: str) -> Optional[str]:
    """Return a one-line non-blocking drift warning for ``package``, or None.

    Emitted from ``skills get`` / ``skills list`` to stderr without
    prompting the user (prompts would hang automated agents). The
    cached copy is the user's working set; this function compares it
    to the live ``importlib.metadata.version()`` and reports staleness.
    """
    cached = cached_skill_version(package)
    inst = installed_version(package)
    if not cached or not inst or cached == inst:
        return None
    if not _is_older(cached, inst):
        return None
    return (
        f"warn: cached skills for {package} are from v{cached}; "
        f"installed v{inst}. Run ``scitex-dev skills install --force`` to refresh."
    )
