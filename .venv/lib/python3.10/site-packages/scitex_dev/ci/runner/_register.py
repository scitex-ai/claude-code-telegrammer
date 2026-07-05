"""``scitex-dev ci runner register <repo>`` — copy CI template + set vars."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from . import config


def register(group: click.Group) -> None:
    @group.command("register")
    @click.argument(
        "repo_path",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
    )
    @click.option(
        "--workflow-name",
        default="ci.yml",
        help="Workflow filename. Default: ci.yml",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print what would be done without making changes.",
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Skip the confirmation prompt (required for non-interactive use).",
    )
    def register_cmd(
        repo_path: str, workflow_name: str, dry_run: bool, yes: bool
    ) -> None:
        """Register a repo with the scitex-ci workflow.

        \b
        Copies the ci.yml template into the repo + sets 3 Actions Variables.

        \b
        Steps:
          1. Copy .github/workflows/ci.yml from the shipped template.
          2. Set Actions Variable CI_RUNS_ON to '["self-hosted","scitex-ci"]'.
          3. Set Actions Variable SCITEX_CI_APPTAINER to the configured apptainer path.
          4. Set Actions Variable SCITEX_CI_SIF to the configured SIF path.
          5. Print the fork-PR approval reminder (no repo settings are mutated).

        \b
        Example:
          $ scitex-dev ci runner register ../scitex-stats --yes
          $ scitex-dev ci runner register ../figrecipe --dry-run
        """
        cfg = config.load_runner_config()
        config.get_gh_token(cfg)

        # Determine the repo owner/name from the local git remote
        repo_result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if repo_result.returncode != 0:
            raise click.ClickException(
                f"Not a git repo (or no 'origin' remote): {repo_path}"
            )

        remote_url = repo_result.stdout.strip()
        # Parse owner/repo from git URL
        # (SSH: git@github.com:owner/repo.git, HTTPS: https://github.com/owner/repo.git)
        import re as _re

        m = _re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote_url)
        if not m:
            raise click.ClickException(
                f"Could not parse owner/repo from remote: {remote_url}"
            )
        owner, repo = m.group(1), m.group(2)

        template_path = Path(__file__).parent / "templates" / "ci.yml.template"
        if not template_path.exists():
            raise click.ClickException(f"Template not found: {template_path}")

        workflow_dir = Path(repo_path) / ".github" / "workflows"
        workflow_file = workflow_dir / workflow_name

        if dry_run:
            click.echo(f"[dry-run] Would copy template to {workflow_file}")
            click.echo(f"[dry-run] Would set Actions Variables on {owner}/{repo}:")
            click.echo('  CI_RUNS_ON = \'["self-hosted","scitex-ci"]\'')
            click.echo(f"  SCITEX_CI_APPTAINER = {cfg['hpc']['apptainer']}")
            click.echo(f"  SCITEX_CI_SIF = {cfg['hpc']['sif']}")
            return

        # Mutating from here on — refuse without --yes (no interactive prompt).
        if not yes:
            raise click.ClickException(
                f"Refusing to register {owner}/{repo} without --yes/-y "
                f"(writes {workflow_name} + sets 3 Actions Variables). "
                "Re-run with --yes to confirm, or --dry-run to preview."
            )

        # Step 1: Copy template
        workflow_dir.mkdir(parents=True, exist_ok=True)
        workflow_file.write_text(template_path.read_text())
        click.echo(f"Copied ci.yml.template → {workflow_file}")

        # Step 2: Set Actions Variables via gh api
        def _set_var(name: str, value: str) -> None:
            click.echo(f"Setting Actions Variable {name} on {owner}/{repo}...")
            result = subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{owner}/{repo}/actions/variables/{name}",
                    "-X",
                    "POST",
                    "-f",
                    f"value={value}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                click.echo(
                    f"  Warning: {result.stderr.strip()[:100]}",
                )

        _set_var("CI_RUNS_ON", '["self-hosted","scitex-ci"]')
        _set_var("SCITEX_CI_APPTAINER", cfg["hpc"]["apptainer"])
        _set_var("SCITEX_CI_SIF", cfg["hpc"]["sif"])

        # Step 3: Fork-PR approval is a manual repo setting — do NOT mutate the
        # repo's default branch (an earlier version PATCHed default_branch=main,
        # which is destructive and unrelated to fork-PR approval).
        click.echo(
            "  (Set fork-PR approval manually: repo Settings → Actions → "
            "Require approval for all outside collaborators)"
        )

        click.echo(f"\n✓ {owner}/{repo} registered with scitex-ci.")
        click.echo(f"  Review: {workflow_file}")
        click.echo("  Variables: CI_RUNS_ON, SCITEX_CI_APPTAINER, SCITEX_CI_SIF")


# EOF
