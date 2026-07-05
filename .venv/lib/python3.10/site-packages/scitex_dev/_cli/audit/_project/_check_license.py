"""PS-138 / PS-138b — LICENSE file checks.

PS-138  — file present at repo root (LICENSE / LICENSE.md / LICENSE.txt).
PS-138b — file content matches the SPDX declaration in pyproject.toml.

PS-138b was added after a 20-line copyright stub passed PS-138 (which
only checked presence). The fix verifies the on-disk text contains the
unmistakable AGPL-3.0 signature lines, including Section 13 ("Remote
Network Interaction") that's nearly always missing from stubs.

Only AGPL-3.0-only is enforced today — that's the ecosystem-mandated
license per `01_ecosystem/07_license-and-cla.md`. If a package
declares a different SPDX expression, PS-138b skips it (presence-only
check via PS-138 still applies).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    import tomllib as _tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as _tomllib  # type: ignore[no-redef]


# Unmistakable AGPL-3.0 signature lines. Stubs almost never include
# Section 13 ("Remote Network Interaction") because it's the longest
# section and the only material distinction from GPL.
_AGPL_SIGNATURES = (
    "GNU AFFERO GENERAL PUBLIC LICENSE",
    "Version 3, 19 November 2007",
    "Remote Network Interaction",
)

_LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt")


def spdx_from_pyproject(repo: Path) -> Optional[str]:
    """Return the SPDX `license = "..."` string from *repo*/pyproject.toml.

    Returns None if pyproject.toml is missing, unparseable, lacks a
    `[project].license` key, or sets it to a non-string (e.g. the legacy
    table form `{text = "..."}` or `{file = "..."}`). PS-138b treats a
    None return as "can't validate, skip content check".
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        data = _tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, _tomllib.TOMLDecodeError):
        return None
    lic = data.get("project", {}).get("license")
    if isinstance(lic, str):
        return lic.strip() or None
    return None


def find_license(repo: Path) -> Optional[Path]:
    """Return the first existing LICENSE file at *repo* root, or None."""
    for cand in _LICENSE_FILES:
        path = repo / cand
        if path.is_file():
            return path
    return None


def check_license_content(license_path: Path, spdx: Optional[str]) -> Optional[str]:
    """Verify *license_path* contains text matching *spdx*.

    Returns a violation message (str) if the file is a stub, or None if
    the content matches (or the SPDX is non-AGPL and we can't validate).
    """
    if spdx != "AGPL-3.0-only":
        return None

    try:
        text = license_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""

    missing = [s for s in _AGPL_SIGNATURES if s not in text]
    if missing:
        return (
            f"LICENSE file exists but content does not match SPDX "
            f"declaration `AGPL-3.0-only` — missing {missing!r}. "
            f"The on-disk license must contain the full AGPL-3.0 text, "
            f"not a copyright stub. See "
            f"`_skills/general/01_ecosystem/07_license-and-cla.md`."
        )
    return None


# EOF
