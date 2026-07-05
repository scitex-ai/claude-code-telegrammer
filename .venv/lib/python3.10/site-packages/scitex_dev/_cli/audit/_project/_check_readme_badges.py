"""PS-106 — README must surface a coverage badge.

Detects either:
- shields.io coverage badge (`img.shields.io/codecov/...` or
  `img.shields.io/coveralls/...` or `img.shields.io/<...>/coverage`)
- Codecov direct badge (`codecov.io/.../graph/badge.svg`)
- Coveralls direct badge (`coveralls.io/...badge.svg`)
- shields.io custom-endpoint badges that include the literal
  word `coverage` in the label segment

Searches the FIRST KB of README.md only — coverage badges belong at
the top with the other status badges. A badge buried at the bottom
is invisible and doesn't satisfy the rule.
"""

from __future__ import annotations

import re
from pathlib import Path


_BADGE_HEAD_BYTES = 4096

_BADGE_PATTERNS = [
    re.compile(r"img\.shields\.io/codecov/", re.IGNORECASE),
    re.compile(r"img\.shields\.io/coveralls/", re.IGNORECASE),
    re.compile(r"img\.shields\.io/[^)\s]*coverage", re.IGNORECASE),
    re.compile(r"codecov\.io/[^)\s]*badge\.svg", re.IGNORECASE),
    re.compile(r"coveralls\.io/[^)\s]*badge\.svg", re.IGNORECASE),
]


def has_coverage_badge(readme: Path) -> bool:
    """Return True iff a recognized coverage badge appears in the
    first ~4 KB of `readme`. False if file missing or unreadable."""
    if not readme.is_file():
        return False
    try:
        head = readme.read_text(encoding="utf-8", errors="replace")[:_BADGE_HEAD_BYTES]
    except OSError:
        return False
    return any(pat.search(head) for pat in _BADGE_PATTERNS)


def check_coverage_badge(repo: Path, violation_cls: type, out: list) -> None:
    """Append a PS-106 violation if README has no coverage badge."""
    readme = repo / "README.md"
    if not readme.is_file():
        # PS-101 / a future PS-107 will catch missing README; don't double-flag.
        return
    if has_coverage_badge(readme):
        return
    out.append(
        violation_cls(
            "PS-106",
            str(readme),
            (
                "no coverage badge in the first ~4 KB of README.md. "
                "Add a line like `[![coverage]"
                "(https://img.shields.io/codecov/c/github/<owner>/<repo>)]"
                "(https://codecov.io/gh/<owner>/<repo>)` near the title. "
                "If the project doesn't yet upload coverage, set up "
                "`codecov/codecov-action` in test.yml first."
            ),
        )
    )
