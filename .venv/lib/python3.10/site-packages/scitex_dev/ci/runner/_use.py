"""``scitex-dev ci runner use <target>`` — flip CI_RUNS_ON."""

from __future__ import annotations

import subprocess

import click

from . import config


def register(group: click.Group) -> None:
    @group.command()
    @click.argument("target", type=click.Choice(["github", "self-hosted"], case_sensitive=False))
    def use_cmd(target: str) -> None:
        """Flip CI_RUNS_ON between hosted and self-hosted.

        Sends a PATCH to the repo Actions Variable CI_RUNS_ON.

        \b
        Examples:
          $ scitex-dev ci runner use github
          $ scitex-dev ci runner use self-hosted

        \b
        NOTE: requires a CLASSIC PAT with actions:variables:write.
        Set SCITEX_DEV_GH_PAT environment variable.
        """
        cfg = config.load_runner_config()
        var_name = cfg["github"]["variable_name"]
        repo = cfg["github"]["default_repo"]

        if target == "github":
            value = '"ubuntu-latest"'
            label = "hosted"
        else:
            value = '["self-hosted","scitex-ci"]'
            label = "self-hosted"

        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/variables/{var_name}",
                "-X",
                "PATCH",
                "-f",
                f"value={value}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise click.ClickException(
                f"Failed to flip CI_RUNS_ON to {label}: {result.stderr.strip()}"
            )

        click.echo(f"CI_RUNS_ON → {value} ({label})")
        click.secho(
            "NOTE: requires a CLASSIC PAT with actions:variables:write. "
            "Set SCITEX_DEV_GH_PAT environment variable.",
            fg="yellow",
        )
