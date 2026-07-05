"""PS-173 — Architecture Decision Record (ADR) format.

ADRs are a recommended (not mandated) ecosystem convention. They live at
`docs/adr/NNNN-<kebab-slug>.md` — 4-digit zero-padded sequential prefix,
kebab-case slug. The body follows a LEAN template with exactly five
sections: a title (H1 or `## Title`), `## Status`, `## Context`,
`## Decision`, `## Consequences`.

Presence is recommended-not-mandated: a repo with NO `docs/adr/` directory
gets no finding. But once `docs/adr/` exists, the FORMAT is enforced —
misnamed files and ADRs missing a required section warn.

Section detection is deliberately tolerant of the proven exemplar shapes
in `scitex-agent-container/docs/adr/`:

- Each section name is accepted as an H2 (`## Status`) OR a bold-prefixed
  line (`**Status:**`) — both forms appear in the wild.
- **Context** also accepts the very common synonym **Problem**
  (`## Problem`) — most agent-container ADRs name the context section
  "Problem".
- **Decision** accepts the plural **Decisions** (`## Decisions`).

Severity W during ecosystem adoption (matches the PS-211/212 / PS-165
warn-first precedent). Promote to E once the ecosystem's ADR dirs comply.
"""

from __future__ import annotations

import re
from pathlib import Path

# docs/adr/NNNN-kebab-slug.md  — 4-digit prefix, lowercase kebab slug, .md
_ADR_NAME_RE = re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")

# Section detectors. Each maps a canonical required section to the set of
# heading texts (lowercased, no surrounding punctuation) that satisfy it.
_SECTION_SYNONYMS: dict[str, frozenset[str]] = {
    "Status": frozenset({"status"}),
    "Context": frozenset({"context", "problem"}),
    "Decision": frozenset({"decision", "decisions"}),
    "Consequences": frozenset({"consequences"}),
}

# `## Heading` (any level ≥2) — capture the heading text.
_H2_RE = re.compile(r"^#{2,}\s+(.+?)\s*$")
# `**Status:** ...` or `**Status**: ...` — capture the bold label. The
# colon may sit INSIDE the asterisks (`**Status:**`, the common ADR form)
# or just after (`**Status**:`); allow either.
_BOLD_LABEL_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z ]*?):?\*\*\s*:?\s")
# A non-empty top-level H1 title (`# ...`), excluding a bare `#`.
_H1_RE = re.compile(r"^#\s+\S")


def _headings(text: str) -> set[str]:
    """Return lowercased heading/label tokens found in `text`.

    Picks up both `## Heading` lines and `**Label:** ...` bold-prefixed
    lines, since real ADRs use Status/Context as bold lines and the rest
    as H2 sections.
    """
    found: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        m = _H2_RE.match(line)
        if m:
            found.add(m.group(1).strip().rstrip(":").lower())
            continue
        m = _BOLD_LABEL_RE.match(line)
        if m:
            found.add(m.group(1).strip().lower())
    return found


def _has_title(text: str) -> bool:
    for raw in text.splitlines():
        if _H1_RE.match(raw.strip()):
            return True
    return False


def check_ps173_adr_format(repo: Path, out: list) -> None:
    """PS-173 — ADR filename + section format (only when docs/adr/ exists)."""
    from ._audit import Violation

    adr_dir = repo / "docs" / "adr"
    if not adr_dir.is_dir():
        return  # presence is recommended, not mandated — no dir, no finding.

    for adr in sorted(adr_dir.glob("*.md")):
        # (a) filename format
        if not _ADR_NAME_RE.match(adr.name):
            out.append(
                Violation(
                    "PS-173",
                    str(adr),
                    "ADR filename must be `NNNN-<kebab-slug>.md` "
                    "(4-digit zero-padded sequential prefix, kebab-case slug)",
                )
            )
            # Keep checking sections too — a misnamed ADR can also be
            # missing sections; report both so one pass fixes everything.

        text = adr.read_text(encoding="utf-8", errors="replace")
        headings = _headings(text)

        # title (H1 or any H2 the file opens with — H1 is canonical)
        if not _has_title(text):
            out.append(
                Violation(
                    "PS-173",
                    str(adr),
                    "ADR missing a title (H1 `# <Title>` at the top)",
                )
            )

        missing = [
            name for name, syns in _SECTION_SYNONYMS.items() if not (headings & syns)
        ]
        if missing:
            out.append(
                Violation(
                    "PS-173",
                    str(adr),
                    "ADR missing required section(s): "
                    + ", ".join(missing)
                    + " (lean template = Title / Status / Context / "
                    "Decision / Consequences; `## Problem` counts as "
                    "Context, `## Decisions` as Decision, `**Status:**` "
                    "bold-line as Status)",
                )
            )


__all__ = ["check_ps173_adr_format"]
