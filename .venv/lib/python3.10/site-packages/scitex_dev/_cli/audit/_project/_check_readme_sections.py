"""README convention checks — PS-107 / PS-109 / PS-110 / PS-111 / PS-112.

Codifies the SciTeX README template (see
``_skills/general/04_docs/01_readme.md`` and the literal template at
``_skills/general/04_docs/01_readme_template.md``). Detection mirrors
PS-106 (``_check_readme_badges.py``): cheap substring/regex scans on the
first ~16 KB of README.md, warn-only.

False-positive guards:
- Skip every check when README is missing (PS-101 covers that) or
  shorter than ``_MIN_README_BYTES`` (placeholder/scaffold READMEs).
- PS-109/PS-110/PS-112 only scan the first 4 KB / 16 KB respectively, so
  late-document boilerplate doesn't get mis-detected as compliant.

Section names match the most common pattern across 8 surveyed READMEs
(scitex-python, scitex-io, scitex-stats, scitex-dev, figrecipe,
scitex-writer, scitex-scholar, scitex-git). See ``/tmp/readme_survey.md``
for the underlying analysis.
"""

from __future__ import annotations

import re
from pathlib import Path


_MIN_README_BYTES = 200
_HEAD_BYTES_BADGES = 4096
# Read the whole README for section-presence checks. Section H2s like
# `## Part of SciTeX` legitimately live near the end of a long README;
# the previous 16 KiB head-slice produced PS-107 false-positives on
# packages whose READMEs grew past that byte budget (e.g. scitex-io at
# 20 KB). 1 MiB is plenty — every SciTeX README is well under that.
_HEAD_BYTES_SECTIONS = 1024 * 1024


# PS-107 — required H2 sections.
# Acceptable variants for "Quick Start" — both `## Quick Start` and
# `## Quickstart` are common in the wild.
_RE_INSTALLATION = re.compile(r"^##\s+Installation\b", re.MULTILINE | re.IGNORECASE)
_RE_QUICKSTART = re.compile(
    r"^##\s+(Quick\s*Start|Quickstart)\b", re.MULTILINE | re.IGNORECASE
)
_RE_PART_OF_SCITEX = re.compile(
    r"^##\s+Part\s+of\s+SciTeX\b", re.MULTILINE | re.IGNORECASE
)
# Accept "## Three Interfaces", "## Four Interfaces", "## Five Interfaces",
# "## Six Interfaces" — the count varies (Python+CLI+MCP+Skills+HTTP, with
# HTTP optional). Number-word OR plain digit accepted.
_RE_INTERFACES = re.compile(
    r"^##\s+(Three|Four|Five|Six|\d+)\s+Interfaces\b",
    re.MULTILINE | re.IGNORECASE,
)


# PS-109 — PyPI version badge. Accepts badge.fury.io OR shields.io/pypi.
_RE_PYPI_BADGE = re.compile(
    r"(badge\.fury\.io/py/|img\.shields\.io/pypi/v/)", re.IGNORECASE
)


# PS-110 — Four Freedoms blockquote. Header detection.
_RE_FOUR_FREEDOMS = re.compile(
    r">\s*Four\s+Freedoms(?:\s+for\s+Research)?", re.IGNORECASE
)

# PS-110b — Each line of the canonical block, in order. Drift detection:
# packages have hand-edited single freedoms (e.g. `--` instead of `—`,
# rephrased verbs, missing AGPL closer). The blockquote should be
# CANONICAL — copy-paste from 04_docs/01_readme_template.md, not paraphrased.
# Each pattern is anchored on the leading `>` (with or without a space).
_RE_FOUR_FREEDOMS_LINES = [
    re.compile(
        r">\s*0\.\s+The\s+freedom\s+to\s+\*\*run\*\*\s+your\s+research\s+anywhere\s+[—-]+\s+your\s+machine,\s+your\s+terms\.",
    ),
    re.compile(
        r">\s*1\.\s+The\s+freedom\s+to\s+\*\*study\*\*\s+how\s+every\s+step\s+works\s+[—-]+\s+from\s+raw\s+data\s+to\s+final\s+manuscript\.",
    ),
    re.compile(
        r">\s*2\.\s+The\s+freedom\s+to\s+\*\*redistribute\*\*\s+your\s+workflows,\s+not\s+just\s+your\s+papers\.",
    ),
    re.compile(
        r">\s*3\.\s+The\s+freedom\s+to\s+\*\*modify\*\*\s+any\s+module\s+and\s+share\s+improvements\s+with\s+the\s+community\.",
    ),
    re.compile(
        r">\s*AGPL-3\.0\s+[—-]+\s+because\s+we\s+believe\s+research\s+infrastructure\s+deserves\s+the\s+same\s+freedoms\s+as\s+the\s+software\s+it\s+runs\s+on\.",
        re.IGNORECASE,
    ),
]


# PS-111 — banned personal email. The convention says READMEs should
# point at the community project, not a single maintainer's address.
_BANNED_EMAIL = "ywatanabe@scitex.ai"


# PS-112 — SciTeX logo at top. Accepted forms (any one is enough):
#   - <img src=".../scitex-logo*.png" ...>
#   - <img src=".../scitex-logo-*.png" ...>
# inside the first 4 KB. We're permissive on path so both
# docs/assets/images/scitex-logo-*.png and docs/scitex-logo-*.png
# variants pass — both occur in the surveyed READMEs.
_RE_SCITEX_LOGO = re.compile(
    r"<img[^>]+src=[\"'][^\"']*scitex-logo[^\"']*\.(?:png|svg|jpg|jpeg)[\"']",
    re.IGNORECASE,
)


# PS-113 — SciTeX icon footer. Centered icon-link at the very bottom of
# the README per the canonical template, e.g.
#   <p align="center">
#     <a href="https://scitex.ai" target="_blank">
#       <img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40"/>
#     </a>
#   </p>
# Detection: scitex-icon-* image referenced anywhere in the LAST ~2 KB
# (the footer area), permissive on path / variant just like PS-112.
_RE_SCITEX_ICON = re.compile(
    r"<img[^>]+src=[\"'][^\"']*scitex-icon[^\"']*\.(?:png|svg|jpg|jpeg)[\"']",
    re.IGNORECASE,
)
_TAIL_BYTES_FOOTER = 2048


# PS-114 — "Problem and Solution" must be presented as a table, not prose.
# Detection: an `## Problem` (or `## Problem and Solution`) heading must
# be followed within ~3 KB by a markdown table separator row
# (`| --- | --- |` style). Misses pure-prose treatments of the section.
_RE_PROBLEM_HEADING = re.compile(
    r"^##\s+Problem(\s+and\s+Solution)?\b", re.MULTILINE | re.IGNORECASE
)
_RE_TABLE_SEPARATOR = re.compile(
    r"^\s*\|\s*[-:]+\s*(\|\s*[-:]+\s*)+\|\s*$", re.MULTILINE
)
_TABLE_LOOKAHEAD_BYTES = 3072


# PS-115 — `## Part of SciTeX` must open with the canonical "is part of
# [SciTeX]" sentence. Format: `\`<pkg>\` is part of [SciTeX](https://scitex.ai)`.
# Tolerant: allows the package name in backticks or plain, allows the
# SciTeX link to be either the canonical URL or the **bold** form.
_RE_PART_OF_OPENER = re.compile(
    r"is\s+part\s+of\s+\[\*{0,2}SciTeX\*{0,2}\]\(https?://scitex\.ai/?\)",
    re.IGNORECASE,
)
_PART_OF_LOOKAHEAD_BYTES = 1024


# PS-116 — deprecated `> **Interfaces:**` callout (replaced 2026-05 by
# per-section star ratings).
_RE_INTERFACES_CALLOUT = re.compile(
    r"^>\s*\*\*\s*Interfaces\s*:\s*\*\*", re.MULTILINE | re.IGNORECASE
)


# PS-117 — duplicate badge block. The canonical block is wrapped by
# `<!-- scitex-badges:start --> ... <!-- scitex-badges:end -->`. A second
# `<p align="center">` block whose body contains badge URLs (shields.io,
# badge.fury.io, readthedocs.org) is the duplicate we want to flag.
_RE_CANONICAL_BADGES_BLOCK = re.compile(
    r"<!--\s*scitex-badges:start\s*-->.*?<!--\s*scitex-badges:end\s*-->",
    re.DOTALL | re.IGNORECASE,
)
_RE_CENTERED_BADGE_ROW = re.compile(
    r"<p\s+align=[\"']center[\"']>\s*"
    r"(?:[^<]*<a[^>]*>\s*)?"
    r"<img[^>]+src=[\"'][^\"']*"
    r"(?:img\.shields\.io|badge\.fury\.io|readthedocs\.org)",
    re.IGNORECASE,
)


# PS-118 — banned descriptors in interface section headers.
# Targets `<summary>` or `##`-style headings carrying parenthetical
# expansions like `(Application Programming Interface)` and trailing
# role descriptors like `-- for AI Agents`, `— for AI Agents`,
# `— for AI Agent Discovery`.
_BANNED_HEADER_PHRASES = [
    re.compile(
        r"<summary>[^<]*\((?:Application Programming Interface|"
        r"Command[\s-]?Line Interface|Model Context Protocol)[^<]*\)",
        re.IGNORECASE,
    ),
    re.compile(
        r"<summary>[^<]*(?:--|—|-)\s*for\s+AI\s+Agent",
        re.IGNORECASE,
    ),
    re.compile(
        r"^##\s+[^\n]*\((?:Application Programming Interface|"
        r"Command[\s-]?Line Interface|Model Context Protocol)[^\n]*\)",
        re.MULTILINE | re.IGNORECASE,
    ),
    re.compile(
        r"^##\s+[^\n]*(?:--|—|-)\s*for\s+AI\s+Agent",
        re.MULTILINE | re.IGNORECASE,
    ),
]


# PS-119 — banned `> **SciTeX users**: pip install scitex` blockquote.
_RE_SCITEX_USERS_HINT = re.compile(
    r"^>\s*\*\*\s*SciTeX\s+users?\s*\*\*\s*:\s*[^\n]*pip\s+install\s+scitex",
    re.MULTILINE | re.IGNORECASE,
)


# PS-120 retired 2026-05-18 — see the section-presence-only check below;
# the umbrella one-liner content rule (pip install scitex[…] +
# scitex.<module> + scitex <subcommand> tokens) was too strict and
# clashed with the `uv pip install` recommendation. PS-116 already
# guards the section's existence.


# PS-123 — `Full X` link must deep-link, not bare RTD root.
_RE_FULL_X_LINK = re.compile(
    r"\[\s*Full\s+[\w\s]+?\s*\]\((?P<url>[^\)]+)\)", re.IGNORECASE
)
_RE_BARE_RTD_ROOT = re.compile(
    r"^https?://[\w-]+\.readthedocs\.io/?(?:en/[\w.-]+/?)?$", re.IGNORECASE
)


# PS-132 — banned standalone `## Modules` H2 (drift; duplicate of autoapi).
_RE_MODULES_H2 = re.compile(r"^##\s+Modules\b", re.MULTILINE | re.IGNORECASE)


# PS-131 — exactly one interface `<details>` block must be `<details open>`
# (the primary). Counted only inside the `## <N> Interfaces` section.
_RE_INTERFACES_HEADING = re.compile(
    r"^##\s+(Three|Four|Five|Six|\d+)\s+Interfaces\b",
    re.MULTILINE | re.IGNORECASE,
)
_RE_DETAILS_OPEN_TAG = re.compile(r"<details\s+open\b", re.IGNORECASE)
_RE_NEXT_H2 = re.compile(r"^##\s+", re.MULTILINE)


def _read_head(readme: Path, n: int) -> str | None:
    """Return the first `n` bytes of `readme` as text, or None on error/missing."""
    if not readme.is_file():
        return None
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text[:n]


def _readme_is_substantive(readme: Path) -> bool:
    """True iff README exists and is at least ``_MIN_README_BYTES`` bytes."""
    if not readme.is_file():
        return False
    try:
        return readme.stat().st_size >= _MIN_README_BYTES
    except OSError:
        return False


def check_readme_sections(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS-107 / PS-109 / PS-110 / PS-111 / PS-112 violations.

    Each rule is independent; a missing README short-circuits all five
    (PS-101 already flags missing pyproject and a future check could flag
    missing README — we don't double-flag here).
    """
    readme = repo / "README.md"
    if not _readme_is_substantive(readme):
        return

    head_sections = _read_head(readme, _HEAD_BYTES_SECTIONS)
    head_badges = _read_head(readme, _HEAD_BYTES_BADGES)
    if head_sections is None or head_badges is None:
        return

    # PS-107 — required sections. NOTE (2026-05): `## Quick Start` is no
    # longer required — the primary `<details open>` interface block
    # doubles as the quick-start (PS-131). If a Quick Start H2 is present,
    # it's tolerated but PS-107 doesn't enforce it anymore.
    missing: list[str] = []
    if not _RE_INSTALLATION.search(head_sections):
        missing.append("## Installation")
    if not _RE_INTERFACES.search(head_sections):
        missing.append("## <N> Interfaces")
    if not _RE_PART_OF_SCITEX.search(head_sections):
        missing.append("## Part of SciTeX")
    if missing:
        out.append(
            violation_cls(
                "PS-107",
                str(readme),
                (
                    "README.md is missing required H2 section(s): "
                    + ", ".join(missing)
                    + ". See _skills/general/04_docs/01_readme_template.md "
                    "for the canonical layout."
                ),
            )
        )

    # PS-109 — PyPI version badge
    if not _RE_PYPI_BADGE.search(head_badges):
        out.append(
            violation_cls(
                "PS-109",
                str(readme),
                (
                    "README.md is missing a PyPI version badge in the first ~4 KB. "
                    "Add a `[![PyPI](https://badge.fury.io/py/<pkg>.svg)]"
                    "(https://pypi.org/project/<pkg>/)` or "
                    "`[![PyPI](https://img.shields.io/pypi/v/<pkg>.svg)](...)` line "
                    "near the title."
                ),
            )
        )

    # PS-110 — Four Freedoms footer (search the whole readable text for the
    # blockquote line — it lives near the bottom of the file).
    full = readme.read_text(encoding="utf-8", errors="replace")
    if not _RE_FOUR_FREEDOMS.search(full):
        out.append(
            violation_cls(
                "PS-110",
                str(readme),
                (
                    "README.md does not contain the Four Freedoms for Research "
                    "blockquote. Append the canonical block under "
                    "`## Part of SciTeX` (see _skills/general/"
                    "04_docs/01_readme_template.md)."
                ),
            )
        )
    else:
        # PS-110b — canonical drift. Each numbered freedom + the AGPL line
        # must match the canonical phrasing exactly (the only allowed
        # variation is em-dash vs hyphen-double).
        missing = [
            i for i, pat in enumerate(_RE_FOUR_FREEDOMS_LINES) if not pat.search(full)
        ]
        if missing:
            labels = [
                "freedom 0 (run)",
                "freedom 1 (study)",
                "freedom 2 (redistribute)",
                "freedom 3 (modify)",
                "AGPL-3.0 closer",
            ]
            named = ", ".join(labels[i] for i in missing)
            out.append(
                violation_cls(
                    "PS-110b",
                    str(readme),
                    (
                        f"Four Freedoms blockquote drifted from canonical text — "
                        f"missing/rephrased: {named}. Copy-paste verbatim from "
                        f"_skills/general/04_docs/01_readme_template.md (do not paraphrase)."
                    ),
                )
            )

    # PS-111 — banned personal email
    if _BANNED_EMAIL in full:
        out.append(
            violation_cls(
                "PS-111",
                str(readme),
                (
                    f"README.md contains the banned personal email "
                    f"`{_BANNED_EMAIL}`. SciTeX is a community project; "
                    "remove the address (use the project URL or GitHub "
                    "issues for contact)."
                ),
            )
        )

    # PS-112 — SciTeX logo at top
    if not _RE_SCITEX_LOGO.search(head_badges):
        out.append(
            violation_cls(
                "PS-112",
                str(readme),
                (
                    "README.md is missing a SciTeX logo image in the first ~4 KB. "
                    'Add a centered `<img src="docs/scitex-logo-blue-cropped.png" '
                    "...>` (or `docs/assets/images/scitex-logo-blue-cropped.png`) "
                    "near the title."
                ),
            )
        )

    # PS-113 — SciTeX icon footer (centered link at the very bottom).
    tail = full[-_TAIL_BYTES_FOOTER:] if len(full) > _TAIL_BYTES_FOOTER else full
    if not _RE_SCITEX_ICON.search(tail):
        out.append(
            violation_cls(
                "PS-113",
                str(readme),
                (
                    "README.md is missing a SciTeX icon footer (centered "
                    "scitex-icon image in the last ~2 KB). Add the canonical "
                    "footer block — see _skills/general/04_docs/01_readme_template.md."
                ),
            )
        )

    # PS-115 — "## Part of SciTeX" must open with the canonical
    # "is part of [SciTeX](https://scitex.ai)" sentence. The synergy
    # code block under it is OPTIONAL — standalone packages can skip
    # the example as long as the opener is present.
    pos_part = _RE_PART_OF_SCITEX.search(full)
    if pos_part is not None:
        window = full[pos_part.end() : pos_part.end() + _PART_OF_LOOKAHEAD_BYTES]
        if not _RE_PART_OF_OPENER.search(window):
            out.append(
                violation_cls(
                    "PS-115",
                    str(readme),
                    (
                        "README.md '## Part of SciTeX' section does not open "
                        "with the canonical '<pkg> is part of "
                        "[SciTeX](https://scitex.ai)' sentence. The synergy "
                        "code block is optional for standalone packages, but "
                        "the opener is required so consumers know how the "
                        "package fits into the ecosystem."
                    ),
                )
            )

    # PS-114 — "Problem and Solution" must be presented as a markdown table.
    # When the heading is present but no table separator follows within
    # ~3 KB, the section is prose-only — flag it.
    m = _RE_PROBLEM_HEADING.search(full)
    if m is not None:
        window = full[m.end() : m.end() + _TABLE_LOOKAHEAD_BYTES]
        if not _RE_TABLE_SEPARATOR.search(window):
            out.append(
                violation_cls(
                    "PS-114",
                    str(readme),
                    (
                        "README.md '## Problem and Solution' (or '## Problem') "
                        "section is prose-only. SciTeX convention is a "
                        "markdown table with columns | # | Problem | Solution | "
                        "— see _skills/general/04_docs/01_readme_template.md."
                    ),
                )
            )

    # PS-116 — deprecated `> **Interfaces:**` summary callout.
    if _RE_INTERFACES_CALLOUT.search(full):
        out.append(
            violation_cls(
                "PS-116",
                str(readme),
                (
                    "README.md uses the deprecated '> **Interfaces:** ...' "
                    "summary callout. Per 2026-05 convention, drop this "
                    "line and put star ratings on each interface section "
                    "header instead (e.g. '## Python API ⭐⭐⭐'). See "
                    "_skills/general/09_quality/02_checklist.md §6."
                ),
            )
        )

    # PS-117 — duplicate badge block. The canonical
    # `<!-- scitex-badges:start --> ... :end -->` block lives at the top;
    # any extra `<p align="center">` row containing badge URLs is the
    # duplicate flagged here.
    canonical_match = _RE_CANONICAL_BADGES_BLOCK.search(full)
    if canonical_match is not None:
        # Search the area AFTER the canonical block for a centered badge row.
        after = full[canonical_match.end() :]
        if _RE_CENTERED_BADGE_ROW.search(after):
            out.append(
                violation_cls(
                    "PS-117",
                    str(readme),
                    (
                        "README.md has a duplicate badge row "
                        '(`<p align="center">` with shields.io / '
                        "badge.fury / readthedocs badges) below the canonical "
                        "`<!-- scitex-badges:* -->` block. Keep only the "
                        "canonical block."
                    ),
                )
            )

    # PS-118 — banned descriptors in interface section headers.
    for pat in _BANNED_HEADER_PHRASES:
        if pat.search(full):
            out.append(
                violation_cls(
                    "PS-118",
                    str(readme),
                    (
                        "README.md interface section header carries a banned "
                        "descriptor — e.g. '(Application Programming "
                        "Interface)', '-- for AI Agents', or '— for AI Agent "
                        "Discovery'. Strip the prose; the section name itself "
                        "carries meaning."
                    ),
                )
            )
            break  # one violation per file is enough

    # PS-119 — banned `> **SciTeX users**: pip install scitex ...` hint.
    if _RE_SCITEX_USERS_HINT.search(full):
        out.append(
            violation_cls(
                "PS-119",
                str(readme),
                (
                    "README.md contains a `> **SciTeX users**: pip install "
                    "scitex ...` install hint. These belong in the umbrella "
                    "`scitex` README, not in sub-package READMEs. Remove the "
                    "line; if the umbrella relationship needs surfacing, the "
                    "standardized 'Part of SciTeX' one-liner already covers it."
                ),
            )
        )

    # PS-132 — `## Modules` H2 (hand-curated function table) is banned.
    if _RE_MODULES_H2.search(full):
        out.append(
            violation_cls(
                "PS-132",
                str(readme),
                (
                    "README.md has a standalone '## Modules' H2 — a "
                    "hand-curated table of Python modules + functions. "
                    "This duplicates the Python API <details> block and "
                    "the autoapi page; it drifts as the package evolves. "
                    "Drop the section — the Python API block + Full API "
                    "reference deep-link cover this."
                ),
            )
        )

    # PS-131 — `<details open>` inside `## <N> Interfaces` is OPTIONAL.
    # The original rule required at least one expanded block (the
    # primary interface, doubling as the quick-start). Since the README
    # template now ships a top-of-file `## Quick Start` section that
    # carries that role, no interface needs to be expanded by default —
    # all four can be collapsed. This block is kept as documentation;
    # remove it entirely when the historical reference is no longer
    # needed.

    # PS-123 — `Full X reference` links must deep-link, not bare RTD root.
    bad_links: list[str] = []
    for m in _RE_FULL_X_LINK.finditer(full):
        url = m.group("url").strip()
        if _RE_BARE_RTD_ROOT.match(url):
            bad_links.append(url)
    if bad_links:
        out.append(
            violation_cls(
                "PS-123",
                str(readme),
                (
                    "README.md interface section has 'Full X reference' "
                    "link(s) pointing at bare RTD root: "
                    + ", ".join(sorted(set(bad_links))[:3])
                    + ". Use a deep-link to the relevant anchor page (e.g. "
                    "`/en/latest/api/<import>.html`) — see _skills/general/"
                    "04_docs/01_readme.md 'Canonical Full X reference "
                    "deep-link patterns'."
                ),
            )
        )

    # PS-120 — retired 2026-05-18 (was: standardized "Part of SciTeX"
    # umbrella one-liner). Section existence is already covered by
    # PS-116; demanding three specific tokens (`pip install scitex[…]`,
    # `scitex.<module>`, `scitex <subcommand>`) inside the section was
    # too strict and forced `pip install` wording even where the
    # ecosystem rule is to recommend `uv pip`. The user retired the
    # rule; the section-presence check above is the canonical guard.
