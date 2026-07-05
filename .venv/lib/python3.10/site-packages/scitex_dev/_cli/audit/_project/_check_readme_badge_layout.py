"""PS-167 — README badge block uses the canonical SAC two-row layout.

Every SciTeX package README MUST wrap its badge group in the canonical
HTML-comment markers and split badges into two centered rows:

    <!-- scitex-badges:start -->
    <p align="center">
      <!-- row 1: package-metadata badges -->
      ... pypi, python, docs ...
    </p>
    <p align="center">
      <!-- row 2: CI / health badges -->
      ... tests, install-check, quality, cov ...
    </p>
    <!-- scitex-badges:end -->

Reference implementation: ``scitex-agent-container/README.md`` (see
``_skills/general/04_docs/01_readme_template.md`` and
``04_docs/01_readme.md`` for the canonicalized template + prose).

Six sub-checks (each emits a PS-167 violation):

  1. ``<!-- scitex-badges:start -->`` marker present.
  2. ``<!-- scitex-badges:end -->`` marker present (and after start).
  3. Inside the markers there are at least two ``<p align="center">``
     blocks (the metadata row + the CI row).
  4. The markers wrap (not are wrapped by) ``<p align="center">``
     blocks. A common deviation has the start marker *inside* the
     first ``<p align="center">`` — this prevents row-splitting tools
     and ecosystem sweeps from operating row-wise.
  5. Every badge ``<img src="...">`` inside the block uses an
     ``img.shields.io/...`` URL (not the raw GitHub Actions
     ``badge.svg`` form, not ``readthedocs.org/projects/.../badge``,
     not ``badge.fury.io``). shields.io is required so the badge can
     carry an explicit ``?label=...`` (PS-166).
  6. The recognised short labels (``pypi``, ``python``, ``docs``,
     ``tests``, ``install-check``, ``quality``, ``cov``) cover the
     block: at least one of the canonical metadata labels
     (``pypi``/``python``/``docs``) appears in the first ``<p>`` and
     at least one of the canonical CI labels
     (``tests``/``install-check``/``quality``/``cov``) appears in the
     second ``<p>``. Missing/empty rows are flagged.

Severity W during ecosystem adoption — promote to E once every
package is migrated.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Markers — case-insensitive, tolerant of surrounding whitespace.
_START_MARKER_RE = re.compile(r"<!--\s*scitex-badges:start\s*-->", re.IGNORECASE)
_END_MARKER_RE = re.compile(r"<!--\s*scitex-badges:end\s*-->", re.IGNORECASE)

# Centered <p> block (opening tag only — we count occurrences).
_P_CENTER_OPEN_RE = re.compile(r"<p\s+align\s*=\s*\"center\"\s*>", re.IGNORECASE)

# Any shields.io image src inside the block.
_SHIELDS_IMG_RE = re.compile(
    r"<img[^>]+src=\"https?://img\.shields\.io/[^\"]+\"",
    re.IGNORECASE,
)

# Any <img src="..."> regardless of host (to count "deviating" badges).
_ANY_IMG_RE = re.compile(r"<img[^>]+src=\"(https?://[^\"]+)\"", re.IGNORECASE)

# label=<value>
_LABEL_RE = re.compile(r"[?&]label=([^&\"'<>\s)]+)", re.IGNORECASE)

_METADATA_LABELS = frozenset({"pypi", "python", "docs"})
_CI_LABELS = frozenset({"tests", "install-check", "quality", "cov"})


def _emit(out: list[Any], violation_cls: type, where: Path, detail: str) -> None:
    out.append(violation_cls("PS-167", str(where), detail))


def check_ps167_readme_badge_layout(
    repo: Path, violation_cls: type, out: list[Any]
) -> None:
    """PS-167 — README badge block matches the canonical SAC layout."""
    readme = repo / "README.md"
    if not readme.is_file():
        return
    try:
        text = readme.read_text(errors="ignore")
    except OSError:
        return

    start_match = _START_MARKER_RE.search(text)
    end_match = _END_MARKER_RE.search(text)

    if start_match is None:
        _emit(
            out,
            violation_cls,
            readme,
            (
                "README is missing the canonical "
                "`<!-- scitex-badges:start -->` marker. Wrap the badge "
                "group in `<!-- scitex-badges:start -->...<!-- "
                "scitex-badges:end -->` (see "
                "scitex-agent-container/README.md) so ecosystem sweeps "
                "can identify and regenerate the block."
            ),
        )
        return

    if end_match is None or end_match.start() <= start_match.end():
        _emit(
            out,
            violation_cls,
            readme,
            (
                "README has `<!-- scitex-badges:start -->` but no "
                "matching `<!-- scitex-badges:end -->` after it. Close "
                "the badge block with the end marker."
            ),
        )
        return

    block = text[start_match.end() : end_match.start()]

    # Check the markers are not embedded INSIDE a <p align="center">.
    # We look at a small slice before `start` and after `end`. If the
    # markers are wrapped (instead of wrapping), they'll be flanked by
    # an open <p align="center"> on the left and a closing </p> on the
    # right OUTSIDE the block — and the block itself will contain a
    # </p> early (matching the outer open).
    pre = text[max(0, start_match.start() - 200) : start_match.start()]
    if re.search(
        r"<p\s+align\s*=\s*\"center\"\s*>\s*$",
        pre,
        re.IGNORECASE,
    ):
        _emit(
            out,
            violation_cls,
            readme,
            (
                "`<!-- scitex-badges:start -->` marker is nested INSIDE "
                'a `<p align="center">` block. The markers must WRAP '
                "the `<p>` blocks, not the other way around — see "
                "scitex-agent-container/README.md for the canonical "
                'layout (markers first, then two `<p align="center">` '
                "rows, then end marker)."
            ),
        )
        # Still continue to surface the other findings.

    # Count centered <p> blocks inside the markers.
    p_blocks = list(_P_CENTER_OPEN_RE.finditer(block))
    if len(p_blocks) < 2:
        _emit(
            out,
            violation_cls,
            readme,
            (
                f"badge block has only {len(p_blocks)} `<p "
                f'align="center">` row(s); the canonical SAC layout '
                "uses TWO rows — row 1 for package-metadata badges "
                "(pypi/python/docs) and row 2 for CI/health badges "
                "(tests/install-check/quality/cov). See "
                "scitex-agent-container/README.md."
            ),
        )

    # Every badge image inside the block must use img.shields.io.
    bad_img_hosts: set[str] = set()
    for m in _ANY_IMG_RE.finditer(block):
        url = m.group(1)
        if "img.shields.io" in url.lower():
            continue
        # Strip path, keep host.
        host_match = re.match(r"https?://([^/]+)/", url + "/")
        if host_match:
            bad_img_hosts.add(host_match.group(1).lower())
    for host in sorted(bad_img_hosts):
        _emit(
            out,
            violation_cls,
            readme,
            (
                f"badge block contains a non-shields.io image host "
                f"(`{host}`). Every badge inside `<!-- "
                f"scitex-badges:start -->...:end -->` must be served "
                f"from `img.shields.io/...` so it can carry an explicit "
                f"`?label=...` short label (see PS-166)."
            ),
        )

    # Row-wise label coverage (best-effort: split block on </p>).
    rows = re.split(r"</p\s*>", block, flags=re.IGNORECASE)
    # First row labels.
    if len(rows) >= 1:
        labels1 = {m.group(1).lower() for m in _LABEL_RE.finditer(rows[0])}
        if labels1 and labels1.isdisjoint(_METADATA_LABELS):
            _emit(
                out,
                violation_cls,
                readme,
                (
                    "first row of the badge block carries no canonical "
                    "metadata label (expected at least one of "
                    f"{sorted(_METADATA_LABELS)}). Row 1 is reserved "
                    "for package-metadata badges; move CI badges to "
                    "row 2 (see scitex-agent-container/README.md)."
                ),
            )
    # Second row labels.
    if len(rows) >= 2:
        labels2 = {m.group(1).lower() for m in _LABEL_RE.finditer(rows[1])}
        if labels2 and labels2.isdisjoint(_CI_LABELS):
            _emit(
                out,
                violation_cls,
                readme,
                (
                    "second row of the badge block carries no canonical "
                    "CI/health label (expected at least one of "
                    f"{sorted(_CI_LABELS)}). Row 2 is reserved for "
                    "CI/health badges (tests/install-check/quality/cov)."
                ),
            )
