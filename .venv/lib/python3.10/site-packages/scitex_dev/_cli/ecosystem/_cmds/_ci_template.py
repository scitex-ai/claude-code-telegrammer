#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem ci-template apply`` — Click wiring.

Thin shim over ``scitex_dev.ecosystem.ci_template.apply``. All policy
(template content, gate, delete-prefix list) lives in the core module so
the CLI surface is just argument parsing + human-friendly rendering.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import click

from ...._ecosystem.ci_template import (
    ApplyError,
    BranchProtectionGateError,
    apply as _apply,
)


def register(ecosystem) -> None:
    @ecosystem.group(
        "ci-template",
        invoke_without_command=True,
    )
    @click.pass_context
    def ci_template(ctx):
        """Roll canonical CI-speedup workflows to a scitex-* repo.

        \b
        Verbs:
          apply  — write pr-ci.yml + release-ci.yml; delete consolidated
                   standalone workflows; enforce branch-protection gate.
        """
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @ci_template.command(
        "apply",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem ci-template apply ../scitex-io --dry-run\n"
            "  $ scitex-dev ecosystem ci-template apply ../scitex-io --yes\n"
            "  $ scitex-dev ecosystem ci-template apply ../scitex-io \\\n"
            "        --python-versions '[\"3.12\",\"3.13\"]' --yes\n"
            "\n"
            "Mutating verb: pass --yes/-y to actually write. Without it the\n"
            "command behaves like --dry-run (no FS mutation, prints intended\n"
            "diff). §2 audit-cli requires explicit confirmation for mutating\n"
            "ecosystem subcommands.\n"
        ),
    )
    @click.argument(
        "repo_dir",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print intended diff; do not write or delete files. Default "
        "behaviour when neither --dry-run nor --yes is given.",
    )
    @click.option(
        "--yes",
        "-y",
        "yes",
        is_flag=True,
        help="Actually write pr-ci.yml + release-ci.yml and delete "
        "consolidated standalone workflows. Required for mutating apply "
        "(§2 audit-cli convention).",
    )
    @click.option(
        "--branch",
        default="chore/ci-speedup",
        show_default=True,
        help="Reserved: branch name for the future PR-flow extension.",
    )
    @click.option(
        "--python-versions",
        "python_versions_json",
        default=None,
        help='Override matrix as JSON list, e.g. \'["3.11","3.12","3.13"]\'.',
    )
    @click.option(
        "--skip-required-check-gate",
        is_flag=True,
        help="DANGEROUS — bypass branch-protection compatibility gate. "
        "Debugging only; never use in batch.",
    )
    def ci_template_apply(
        repo_dir,
        dry_run,
        yes,
        branch,
        python_versions_json,
        skip_required_check_gate,
    ):
        """Apply the CI templates to REPO_DIR.

        Mutating verb: defaults to dry-run unless --yes is passed. This
        keeps the §2 audit-cli convention that every ecosystem mutator
        needs an explicit confirmation flag.
        """
        if dry_run and yes:
            click.echo(
                "error: --dry-run and --yes are mutually exclusive",
                err=True,
            )
            raise SystemExit(2)
        # Without --yes, behave as dry-run (no FS mutation).
        effective_dry_run = dry_run or not yes
        python_versions = None
        if python_versions_json:
            try:
                python_versions = json.loads(python_versions_json)
            except json.JSONDecodeError as exc:
                click.echo(
                    f"error: --python-versions is not valid JSON: {exc}",
                    err=True,
                )
                raise SystemExit(2)
            if not isinstance(python_versions, list) or not all(
                isinstance(x, str) for x in python_versions
            ):
                click.echo(
                    "error: --python-versions must be a JSON list of strings",
                    err=True,
                )
                raise SystemExit(2)

        try:
            result = _apply(
                repo_dir,
                dry_run=effective_dry_run,
                branch=branch,
                python_versions=python_versions,
                skip_required_check_gate=skip_required_check_gate,
            )
        except BranchProtectionGateError as exc:
            click.echo(str(exc), err=True)
            raise SystemExit(3)
        except ApplyError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(2)

        _render_result(result, dry_run=effective_dry_run)

    return ci_template


def _render_result(result, *, dry_run: bool) -> None:
    """Human-readable summary. ``--dry-run`` adds unified diffs for changed
    files so the operator can eyeball the substitution.
    """
    tag = "DRY-RUN" if dry_run else "APPLIED"
    click.secho(
        f"[{tag}] {result.pkg_name} ({result.pkg_module}) — {result.repo_dir}",
        fg="cyan", bold=True,
    )
    click.echo(f"  python-versions : {result.python_versions}")
    click.echo(f"  emitted-jobs    : {result.emitted_jobs}")
    if result.required_contexts:
        click.echo(f"  required-contexts (live):")
        for br, ctxs in sorted(result.required_contexts.items()):
            click.echo(f"    {br}: {ctxs}")
    else:
        click.echo("  required-contexts (live): (none / no protection)")
    if result.gate_skipped:
        click.secho("  gate           : SKIPPED (--skip-required-check-gate)", fg="yellow")

    if result.written_paths:
        click.echo("  Would write:" if dry_run else "  Wrote:")
        for p in result.written_paths:
            click.echo(f"    + {p}")
    if result.deleted_paths:
        click.echo("  Would delete:" if dry_run else "  Deleted:")
        for p in result.deleted_paths:
            click.echo(f"    - {p}")
    if result.skipped_delete_paths:
        click.echo("  Kept (not eligible for delete):")
        for p in result.skipped_delete_paths:
            click.echo(f"    = {p}")

    if dry_run:
        # Per-file unified diff against on-disk content (if any).
        for rel, new_content in result.rendered.items():
            target = result.repo_dir / rel
            old_content = target.read_text(encoding="utf-8") if target.is_file() else ""
            diff = list(
                difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    fromfile=str(target) + " (current)",
                    tofile=str(target) + " (new)",
                )
            )
            if not diff:
                continue
            click.echo("")
            click.echo("".join(diff))
