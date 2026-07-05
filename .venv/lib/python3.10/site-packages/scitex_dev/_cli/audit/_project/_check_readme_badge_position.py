"""PS-133 — README badges placed below the Full-Documentation line, in the
centered figrecipe-style ``<p align="center">`` form.

Convention (see ``_skills/general/04_docs/01_readme_template.md``):

    # <PACKAGE>
    <centered logo>
    <centered tagline>
    <centered Full Documentation · pip install>
    <centered badges>          ← right here, below Full-Doc
    [optional > blockquote disclaimer]
    ---
    ## Problem and Solution

The badges block must:

1. Live BELOW the ``Full Documentation`` line (not above the logo, not
   between logo and tagline, etc.).
2. Use the centered HTML form (``<p align="center">`` containing
   ``<a href=...><img src=...></a>`` rows), NOT the left-aligned
   ``[![label](badge)](link)`` markdown form.

Both checks scan the first ~6 KB of README.md. Misplaced or missing
badges trigger PS-133; this is independent of PS-106 / PS-109 / PS-112
which check that *some* form of each badge exists at all.
"""

from __future__ import annotations

import re
from pathlib import Path

_HEAD_BYTES = 6144

_FULL_DOC_RE = re.compile(r"Full\s+Documentation", re.IGNORECASE)
_BADGES_HTML_RE = re.compile(
    r"<p\s+align=[\"']center[\"']>\s*(?:<!--[^-]*-->\s*)*<a[^>]*href=[\"']?(?:[^\"'>]*pypi|[^\"'>]*shields\.io|[^\"'>]*codecov|[^\"'>]*readthedocs|[^\"'>]*github\.com[^\"'>]*actions)",
    re.IGNORECASE | re.DOTALL,
)
_BADGES_MD_RE = re.compile(
    r"\[\!\[(?:PyPI|Python|Tests?|Coverage|Docs?|License)",
    re.IGNORECASE,
)


def check_badge_position(repo: Path, violation_cls: type, out: list) -> None:
    """Append a PS-133 violation if badges are missing, mis-placed, or in
    the wrong (markdown) form.
    """
    readme = repo / "README.md"
    if not readme.is_file():
        return
    try:
        head = readme.read_text(encoding="utf-8", errors="replace")[:_HEAD_BYTES]
    except OSError:
        return

    full_doc = _FULL_DOC_RE.search(head)
    if not full_doc:
        # PS-107 catches missing required sections; don't double-flag.
        return

    full_doc_end = full_doc.end()
    after = head[full_doc_end:]

    html_badges = _BADGES_HTML_RE.search(after)
    md_badges_anywhere = _BADGES_MD_RE.search(head)
    md_badges_after = _BADGES_MD_RE.search(after)

    if html_badges:
        return  # canonical form, correct position

    if md_badges_after:
        out.append(
            violation_cls(
                "PS-133",
                str(readme),
                (
                    "badges block uses the left-aligned ``[![…]]()`` "
                    "markdown form. Convert to the centered figrecipe "
                    'form: a ``<p align="center">`` containing one '
                    "``<a href=…><img src=…></a>`` per badge. See "
                    "_skills/general/04_docs/01_readme_template.md."
                ),
            )
        )
        return

    if md_badges_anywhere:
        out.append(
            violation_cls(
                "PS-133",
                str(readme),
                (
                    "badges block appears BEFORE the Full-Documentation "
                    "line; canonical position is just below it. Also "
                    'convert to the centered figrecipe ``<p align="center">`` '
                    "form. See _skills/general/04_docs/01_readme_template.md."
                ),
            )
        )
        return

    # No badges block found at all — PS-106 / PS-109 / PS-112 already
    # cover the per-badge presence; don't double-flag here.
