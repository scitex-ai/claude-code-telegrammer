"""Click command: `scitex-dev lint sweep` — ecosystem-wide README + docs scan.

Read-only. Walks every package registered in
``scitex_dev._ecosystem._core.ECOSYSTEM`` (skipping ``archived`` and
``template`` categories), lints each package's README + key docs,
prints a compact summary.
"""

from __future__ import annotations

import json as _json

import click

from .cli import main_group


@main_group.command("sweep")
@click.option(
    "--package",
    "packages",
    multiple=True,
    help="Only sweep these packages (repeatable). Default: all non-archived.",
)
@click.option(
    "--json", "as_json", is_flag=True, default=False, help="Emit JSON output."
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Exit non-zero if any package has issues (CI gating).",
)
def sweep(packages, as_json, strict):
    """Lint README + docs (.md/.rst) across the SciTeX ecosystem.

    \b
    Example:
        $ scitex-dev lint sweep
        $ scitex-dev lint sweep --package figrecipe --package scitex-io
        $ scitex-dev lint sweep --json
        $ scitex-dev lint sweep --strict       # for CI
    """
    from ._ecosystem_sweep import format_summary, sweep_ecosystem

    pkgs = list(packages) if packages else None
    report = sweep_ecosystem(packages=pkgs)

    if as_json:
        out = {
            pkg: {
                "path": str(data["path"]),
                "files": {
                    rel: [
                        {
                            "rule_id": iss.rule.id,
                            "severity": iss.rule.severity,
                            "line": iss.line,
                            "col": iss.col,
                            "message": iss.rule.message,
                        }
                        for iss in issues
                    ]
                    for rel, issues in data["files"].items()
                },
            }
            for pkg, data in report.items()
        }
        click.echo(_json.dumps(out, indent=2, default=str))
    else:
        click.echo(format_summary(report))

    if strict:
        any_issues = any(data["files"] for data in report.values())
        raise SystemExit(1 if any_issues else 0)


# EOF
