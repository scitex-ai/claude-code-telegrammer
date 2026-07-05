"""``scitex-dev linter check-files`` command + its helpers.

Extracted from ``cli.py`` (which crossed the 512-line budget when the
``--new-only`` baseline gate landed). The command is registered onto the
root group via :func:`register`. ``_do_check`` is re-exported from
``cli`` for back-compat with callers/tests that import it from there.

The ``--new-only`` / ``--baseline`` flags are the SAFETY PAIR for the
research-mode severity promotion (#264 / #265): under ``--new-only`` only
NEWLY-introduced findings keep their promoted ``error`` severity (and so
block the post-edit hook), while PRE-EXISTING findings present at the
baseline ref are capped to ``warning`` (visible, non-blocking). See
``_new_only`` for the classification, which mirrors PR #261's diff-aware
``ecosystem audit-all`` identity (line-number-agnostic, content-keyed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .checker import lint_file
from .config import load_config
from .formatter import format_issue, format_summary, to_json
from .rules import SEVERITY_ORDER


def _collect_files(path: Path, recursive: bool = True, config=None) -> list:
    """Collect Python and Jupyter notebook files from a path."""
    from ._collect import collect_files

    return collect_files(path, recursive=recursive, config=config)


def _baseline_issues_for(filepath, baseline, config):
    """Lint the BASELINE content of ``filepath`` at git ref ``baseline``.

    Returns the issue list of the file as it existed at ``baseline``, or
    ``[]`` when the file is untracked / absent there (every current
    finding is then "new"). Routed through ``lint_source`` so the same
    rule corpus + config applies to the baseline text.
    """
    from ._new_only import baseline_source

    src = baseline_source(Path(filepath), baseline)
    if src is None:
        return []
    from .checker import lint_source

    return lint_source(src, filepath=str(filepath), config=config)


def _do_check(
    path, as_json, no_color, severity, category, new_only=False, baseline="HEAD"
):
    config = load_config(path)
    use_color = not no_color and sys.stdout.isatty()
    min_sev = SEVERITY_ORDER[severity]
    categories = set(category.split(",")) if category else None

    target = Path(path)
    if not target.exists():
        click.echo(f"Error: {path} not found", err=True)
        return 2

    files = _collect_files(target, config=config)
    if not files:
        click.echo(f"No Python files found in {path}", err=True)
        return 0

    all_results = {}
    for f in files:
        issues = lint_file(str(f), config=config)
        if new_only:
            # Cap PRE-EXISTING errors (present at the baseline ref) to
            # warnings so only NEWLY-introduced errors keep blocking. This
            # is the safety pair for the #265 severity promotion — legacy
            # debt stays visible (warn) but never wedges an edit.
            from ._new_only import apply_new_only

            baseline_issues = _baseline_issues_for(f, baseline, config)
            issues = apply_new_only(issues, baseline_issues)
        issues = [
            i
            for i in issues
            if SEVERITY_ORDER[i.rule.severity] >= min_sev
            and (categories is None or i.rule.category in categories)
        ]
        if issues:
            all_results[str(f)] = issues

    if as_json:
        combined = {fp: to_json(issues, fp) for fp, issues in all_results.items()}
        click.echo(json.dumps(combined, indent=2))
        has_errors = any(
            any(i.rule.severity == "error" for i in issues)
            for issues in all_results.values()
        )
        return 2 if has_errors else (1 if all_results else 0)

    if not all_results:
        msg = "All files clean"
        if use_color:
            click.echo(f"\033[92m{msg}\033[0m")
        else:
            click.echo(msg)
        return 0

    has_errors = False
    for filepath, issues in all_results.items():
        for issue in issues:
            click.echo(format_issue(issue, filepath, color=use_color))
            if issue.rule.severity == "error":
                has_errors = True
        click.echo(format_summary(issues, filepath, color=use_color))
        click.echo()
    return 2 if has_errors else 1


def register(main_group):
    """Attach the ``check-files`` command to ``main_group``."""

    @main_group.command("check-files")
    @click.argument("path", type=click.Path())
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    @click.option(
        "--no-color", is_flag=True, default=False, help="Disable colored output."
    )
    @click.option(
        "--severity",
        type=click.Choice(["error", "warning", "info"]),
        default="info",
        help="Minimum severity to report (default: info).",
    )
    @click.option(
        "--category",
        default=None,
        help="Filter by category (comma-separated: structure,import,io,plot,stats).",
    )
    @click.option(
        "--new-only",
        "new_only",
        is_flag=True,
        default=False,
        help=(
            "Diff-aware gate (safety pair for the research-mode severity "
            "promotion): only NEWLY-introduced findings keep their promoted "
            "error severity; PRE-EXISTING findings (present at --baseline) are "
            "capped to warning so legacy debt stays visible but never blocks. "
            "Matching is content-based (rule + normalized line text), so a "
            "finding survives unrelated line shifts."
        ),
    )
    @click.option(
        "--baseline",
        default="HEAD",
        show_default=True,
        help=(
            "Git ref whose content defines the PRE-EXISTING baseline for "
            "--new-only. Untracked files have an empty baseline (all findings "
            "are new)."
        ),
    )
    def check_files(path, as_json, no_color, severity, category, new_only, baseline):
        """Check Python files for SciTeX pattern compliance.

        \b
        Example:
            $ scitex-dev linter check-files src/
            $ scitex-dev linter check-files my_script.py --json
            $ scitex-dev linter check-files src/ --severity error --no-color
            $ scitex-dev linter check-files my_script.py --new-only --baseline HEAD
        """
        sys.exit(
            _do_check(
                path,
                as_json,
                no_color,
                severity,
                category,
                new_only=new_only,
                baseline=baseline,
            )
        )

    return check_files


# EOF
