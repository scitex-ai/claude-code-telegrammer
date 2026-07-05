"""PS-129 / PS-130 — env-var convention via `.env.example`.

Single source of truth for per-package environment variables: a top-level
`.env.example` with commented entries. The README references it from the
`## Installation` section instead of duplicating a table.

PS-129 — package source references `SCITEX_<MODULE>_*` but no `.env.example`
PS-130 — README still has a standalone `## Environment Variables` H2

Both warn-only.
"""

from __future__ import annotations

import re
from pathlib import Path

# `SCITEX_<MODULE>_<NAME>` — anchored to ALL-CAPS identifier.
_RE_SCITEX_ENV = re.compile(r"\bSCITEX_[A-Z][A-Z0-9_]*[A-Z0-9]\b")
_RE_README_ENV_H2 = re.compile(
    r"^##\s+Environment\s+Variables?\b", re.MULTILINE | re.IGNORECASE
)


def _src_uses_scitex_env(repo: Path) -> bool:
    """True iff any .py file under `src/` references a SCITEX_<MODULE>_<NAME>."""
    src = repo / "src"
    if not src.is_dir():
        return False
    for py in src.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _RE_SCITEX_ENV.search(text):
            return True
    return False


def check_env_example(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS-129 / PS-130 violations.

    Both styles are acceptable:
      - README ``## Environment Variables`` H2 with a table (fine for
        small lists, ~5 vars or fewer)
      - Top-level ``.env.example`` (cleaner for many vars; user can
        ``cp`` and edit)

    PS-129 fires when the package uses SCITEX_<MODULE>_* in source but
    documents them in NEITHER place — undocumented env vars are the
    real failure mode.

    PS-130 fires when BOTH styles are present: the table and the
    ``.env.example`` will drift. Pick one.
    """
    env_example = repo / ".env.example"
    readme = repo / "README.md"
    has_env_example = env_example.is_file()
    readme_has_env_h2 = False
    if readme.is_file():
        try:
            readme_has_env_h2 = bool(
                _RE_README_ENV_H2.search(
                    readme.read_text(encoding="utf-8", errors="replace")
                )
            )
        except OSError:
            pass

    # PS-129 — source uses SCITEX_<MODULE>_* but documented in NEITHER place.
    if _src_uses_scitex_env(repo) and not has_env_example and not readme_has_env_h2:
        out.append(
            violation_cls(
                "PS-129",
                str(env_example),
                (
                    "package source references SCITEX_<MODULE>_* env vars "
                    "but documents them in neither `.env.example` nor a "
                    "README `## Environment Variables` section. Add one "
                    "(see _skills/general/04_docs/03_env-vars-and-state.md "
                    "for both acceptable patterns)."
                ),
            )
        )

    # PS-130 — BOTH a README env H2 AND a `.env.example` exist.
    if has_env_example and readme_has_env_h2:
        out.append(
            violation_cls(
                "PS-130",
                str(readme),
                (
                    "README has '## Environment Variables' AND `.env.example` "
                    "exists at repo root — the two will drift. Pick one: "
                    "inline the small list in README, OR keep `.env.example` "
                    "and reference it from `## Installation > ### "
                    "Configuration`."
                ),
            )
        )
