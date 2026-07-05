"""Export dashboard state to JSON / CSV / Markdown / Org / PDF.

The org + pdf exports follow the ywatanabe "usual PDF" convention:
write the report as ``.org``, then convert via pandoc or
``emacs --batch``. ``to_pdf`` always writes the ``.org`` sidecar; if
no converter is on PATH it returns ``status="org_only"`` so the
operator can finish the conversion on a host that has one.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
from pathlib import Path

from ._state import PackageState


def to_json(states: list[PackageState], *, indent: int = 2) -> str:
    return json.dumps([s.to_dict() for s in states], indent=indent, default=str)


def to_csv(states: list[PackageState]) -> str:
    if not states:
        return ""
    rows = [s.to_dict() for s in states]
    # Stable column order: dataclass field order from the first row.
    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        # CSV can't carry lists — join skip_rules with ';'.
        safe = {k: (";".join(v) if isinstance(v, list) else v) for k, v in row.items()}
        writer.writerow(safe)
    return buf.getvalue()


def _format_release_cell(s: PackageState) -> str:
    """Mirror the renderer's MISSING logic for non-coloured outputs.

    The Rich renderer paints ``MISSING`` red when there's a local tag
    but no GH Release; in plain text we use the same word so the
    column reads identically across surfaces (md/org/csv → pdf).
    """
    if s.gh_release_latest:
        return s.gh_release_latest
    if getattr(s, "gh_release_lookup_done", False):
        return "MISSING" if s.tag_latest else "-"
    return "N/C"


# Column tuple shared by `to_markdown` and `to_org`. Keep these two
# emitters fed from the same source-of-truth so a column added here
# shows up in both surfaces. `RELEASE` is the GH-Release column added
# 2026-05-27 — the 0.7.4/0.7.6 wave shipped to PyPI without a matching
# GH Release; surfacing it next to TAG/PYPI makes that gap visible at
# a glance.
def _report_columns() -> list[tuple[str, "object"]]:
    return [
        ("PKG", lambda s: s.pkg),
        ("VER", lambda s: s.version_pyproject or "-"),
        ("TAG", lambda s: s.tag_latest or "-"),
        ("RELEASE", _format_release_cell),
        ("PYPI", lambda s: s.pypi_latest or "-"),
        ("DRIFT", lambda s: s.drift_local or "-"),
        ("BRANCH", lambda s: s.branch or "-"),
        ("AHEAD", lambda s: str(s.ahead)),
        ("SKIP", lambda s: str(len(s.skip_rules))),
    ]


def to_markdown(states: list[PackageState]) -> str:
    """Compact MD table — pick the columns reviewers usually want."""
    cols = _report_columns()
    out: list[str] = []
    out.append("| " + " | ".join(c[0] for c in cols) + " |")
    out.append("| " + " | ".join("---" for _ in cols) + " |")
    for s in sorted(states, key=lambda x: x.pkg):
        out.append("| " + " | ".join(c[1](s) for c in cols) + " |")
    return "\n".join(out) + "\n"


def to_org(
    states: list[PackageState],
    *,
    title: str = "scitex ecosystem dashboard",
    author: str = "scitex-dev",
) -> str:
    """Org-mode report — the ywatanabe "usual PDF" source format.

    Emits an Org buffer with a header table that mirrors `to_markdown`
    plus a per-package details section. Pandoc and `emacs --batch`
    both round-trip this shape to PDF; see ``to_pdf`` for the
    convert-and-emit pipeline.
    """
    from datetime import datetime

    cols = _report_columns()
    sorted_states = sorted(states, key=lambda x: x.pkg)

    lines: list[str] = []
    lines.append(f"#+TITLE: {title}")
    lines.append(f"#+AUTHOR: {author}")
    lines.append(f"#+DATE: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("#+OPTIONS: toc:nil num:nil")
    lines.append("")
    lines.append(f"* Summary ({len(sorted_states)} packages)")
    lines.append("")
    # Org table: same shape as the markdown one. Org and pandoc both
    # accept `| header | header |` then a horizontal-rule row then the
    # data rows.
    lines.append("| " + " | ".join(c[0] for c in cols) + " |")
    lines.append("|" + "+".join("---" for _ in cols) + "|")
    for s in sorted_states:
        lines.append("| " + " | ".join(c[1](s) for c in cols) + " |")
    lines.append("")
    # GH-Release-gap section — packages where a local tag exists but
    # no matching GitHub Release does. This is the 2026-05-27 footgun
    # made visible at the top of the report.
    missing: list[PackageState] = [
        s
        for s in sorted_states
        if s.tag_latest
        and not s.gh_release_latest
        and getattr(s, "gh_release_lookup_done", False)
    ]
    if missing:
        lines.append("* GH-Release gaps")
        lines.append("")
        lines.append(
            "Packages with a local tag but NO matching GitHub Release "
            "(PyPI may have published; release-notes step likely failed):"
        )
        lines.append("")
        for s in missing:
            lines.append(
                f"- *{s.pkg}* — tag={s.tag_latest}, pypi={s.pypi_latest or '-'}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def to_pdf(
    states: list[PackageState],
    output_path: "str | Path",
    *,
    title: str = "scitex ecosystem dashboard",
) -> dict:
    """Convert the org report to PDF via pandoc or emacs.

    Always writes the ``.org`` sidecar next to ``output_path`` so the
    intermediate report is preserved regardless of conversion
    success. Returns a dict describing what happened:

      {"status": "ok",        "tool": "pandoc"|"emacs",
       "pdf": "/abs/path.pdf", "org": "/abs/path.org"}
      {"status": "org_only",  "tool": None,
       "pdf": None,           "org": "/abs/path.org",
       "reason": "<why>"}
      {"status": "error",     "tool": "pandoc"|"emacs",
       "pdf": None,           "org": "/abs/path.org",
       "error": "<stderr>"}

    Container environments often lack both pandoc AND emacs; in that
    case we still write the .org file and return a clear message so
    the operator can run the conversion on the host. Never raises.
    """
    output_path = Path(output_path).expanduser().resolve()

    # The .org sidecar always lands next to the requested PDF target,
    # named with the same stem. Operators reasonably expect both.
    org_path = output_path.with_suffix(".org")
    org_text = to_org(states, title=title)
    org_path.parent.mkdir(parents=True, exist_ok=True)
    org_path.write_text(org_text, encoding="utf-8")

    pandoc = shutil.which("pandoc")
    emacs = shutil.which("emacs")

    if pandoc:
        # `pandoc <file>.org -o <file>.pdf` shells out to LaTeX
        # (xelatex / pdflatex / etc.). It picks whichever engine is
        # installed; if none is, pandoc itself fails with a clear
        # message we relay verbatim.
        try:
            proc = subprocess.run(
                [pandoc, str(org_path), "-o", str(output_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "tool": "pandoc",
                "pdf": None,
                "org": str(org_path),
                "error": "pandoc timed out after 120s",
            }
        if proc.returncode == 0:
            return {
                "status": "ok",
                "tool": "pandoc",
                "pdf": str(output_path),
                "org": str(org_path),
            }
        return {
            "status": "error",
            "tool": "pandoc",
            "pdf": None,
            "org": str(org_path),
            "error": (proc.stderr or proc.stdout or "")[:2000],
        }

    if emacs:
        # `emacs --batch <file>.org -f org-latex-export-to-pdf` is the
        # canonical ywatanabe org→PDF pipeline. Same LaTeX dep as
        # pandoc; emacs is the fallback when pandoc isn't around.
        try:
            proc = subprocess.run(
                [
                    emacs,
                    "--batch",
                    str(org_path),
                    "-f",
                    "org-latex-export-to-pdf",
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "tool": "emacs",
                "pdf": None,
                "org": str(org_path),
                "error": "emacs timed out after 180s",
            }
        # Emacs writes PDF next to the .org file under the same stem;
        # move it to the requested output_path if different.
        produced = org_path.with_suffix(".pdf")
        if produced.is_file():
            if produced != output_path:
                produced.replace(output_path)
            return {
                "status": "ok",
                "tool": "emacs",
                "pdf": str(output_path),
                "org": str(org_path),
            }
        return {
            "status": "error",
            "tool": "emacs",
            "pdf": None,
            "org": str(org_path),
            "error": (proc.stderr or proc.stdout or "")[:2000],
        }

    # Neither converter available — emit the .org and tell the caller.
    return {
        "status": "org_only",
        "tool": None,
        "pdf": None,
        "org": str(org_path),
        "reason": (
            "neither `pandoc` nor `emacs` found on PATH; .org written, "
            "convert to PDF on a host that has one (e.g. "
            "`pandoc report.org -o report.pdf` or "
            "`emacs --batch report.org -f org-latex-export-to-pdf`)"
        ),
    }
