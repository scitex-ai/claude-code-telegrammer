"""Ecosystem-wide read-only sweep: lint each package's README + docs/.

Produces a summary report per package + total counts. Does not mutate
state. Useful as a one-shot diagnostic before deciding whether to
gate CI on doc-block correctness.
"""

from __future__ import annotations

from pathlib import Path

# Files to lint per package — relative to the package's local_path.
# These are the surfaces a new user reads first. Limit scope so this
# stays a "first impression" audit, not a full doc-tree scan.
_TARGETS = (
    "README.md",
    "README.rst",
    "docs/sphinx/index.rst",
    "docs/sphinx/quickstart.rst",
    "docs/index.md",
    "docs/index.rst",
)


def sweep_ecosystem(packages: list = None, config=None) -> dict:
    """Lint README + key docs across the SciTeX ecosystem.

    Returns
    -------
    dict
        ``{package_name: {"path": Path, "files": {file_rel: [Issue]}}}``
        Packages with no targets / no issues are still included (with
        empty ``files``) so callers can distinguish "scanned-clean"
        from "not-scanned".
    """
    from .._ecosystem._core import ECOSYSTEM, get_local_path
    from .checker import lint_file

    if packages is None:
        packages = [
            name
            for name, meta in ECOSYSTEM.items()
            if meta.get("category") not in {"archived", "template"}
        ]

    report: dict = {}
    for pkg in packages:
        local = get_local_path(pkg)
        if local is None or not Path(local).is_dir():
            continue
        files: dict = {}
        for rel in _TARGETS:
            target = Path(local) / rel
            if not target.is_file():
                continue
            issues = lint_file(str(target), config=config)
            if issues:
                files[rel] = issues
        report[pkg] = {"path": local, "files": files}
    return report


def format_summary(report: dict) -> str:
    """Render a compact human-readable summary of a sweep report."""
    lines: list = []
    pkgs_total = len(report)
    pkgs_dirty = sum(1 for r in report.values() if r["files"])
    issue_total = sum(
        len(issues) for r in report.values() for issues in r["files"].values()
    )

    lines.append(
        f"Scanned {pkgs_total} package(s); {pkgs_dirty} have doc-block issues; "
        f"{issue_total} issues total."
    )
    if pkgs_dirty == 0:
        return "\n".join(lines)

    lines.append("")
    for pkg, data in sorted(report.items()):
        files = data["files"]
        if not files:
            continue
        n = sum(len(v) for v in files.values())
        lines.append(f"{pkg}  ({n} issue{'s' if n != 1 else ''})")
        for rel, issues in sorted(files.items()):
            lines.append(f"  {rel}")
            for iss in issues[:5]:
                lines.append(f"    L{iss.line:>4}  {iss.rule.id}  {iss.rule.message}")
            if len(issues) > 5:
                lines.append(f"    ... and {len(issues) - 5} more")
    return "\n".join(lines)


# EOF
