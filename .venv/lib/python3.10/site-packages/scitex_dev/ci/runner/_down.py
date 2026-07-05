"""``scitex-dev ci runner down`` — deregister the runner + stop it."""

from __future__ import annotations

import subprocess

import click

from . import config
from ._up import _resolve_lease


def register(group: click.Group) -> None:
    @group.command()
    @click.option(
        "--runner-name",
        default=None,
        help="Runner name to remove. Default: from config.",
    )
    def down_cmd(runner_name: str | None) -> None:
        """Deregister the self-hosted runner and stop it.

        \b
        Steps:
          1. Get remove-token from GitHub API.
          2. Run config.sh remove --token on the runner.
          3. Delete the runner from GitHub.
          4. Kill the wrapper process on the HPC host.

        \b
        NOTE: This NEVER cancels the SLURM lease job — only removes the
        runner from GitHub and kills the runner process.

        \b
        Example:
          $ scitex-dev ci runner down
        """
        cfg = config.load_runner_config()
        target = config._ssh_target(cfg)
        # Fail loud early if the PAT env var is unset (the gh CLI calls below
        # rely on it being present); the value itself is unused here.
        config.get_gh_token(cfg)
        repo = cfg["github"]["default_repo"]
        rname = runner_name or cfg["runner"]["name"]
        runner_home = cfg["runner"]["home"]

        # Step 1: Find the runner and get remove-token. The list-runners
        # endpoint returns an OBJECT {total_count, runners: [...]}, so iterate
        # `.runners[]` — a bare `.[]` walks the object's VALUES (the count int +
        # the array) and select() then errors ("expected an object but got:
        # array"), which is exactly the failure _status.py already guards against.
        find_cmd = [
            "gh",
            "api",
            f"repos/{repo}/actions/runners",
            "--jq",
            f'[.runners[] | select(.name == "{rname}") | {{"id": .id}}]',
        ]
        find_result = subprocess.run(
            find_cmd, capture_output=True, text=True, timeout=30
        )
        if find_result.returncode != 0:
            raise click.ClickException(
                f"Failed to find runner: {find_result.stderr.strip()}"
            )

        import json

        runners = json.loads(find_result.stdout.strip())
        if not runners:
            raise click.ClickException(f"Runner {rname!r} not found on {repo}")

        runner_id = runners[0]["id"]

        # Step 2: Get remove-token
        remove_token_cmd = [
            "gh",
            "api",
            f"repos/{repo}/actions/runners/{runner_id}/remove-token",
            "-X",
            "POST",
            "--jq",
            ".token",
        ]
        remove_result = subprocess.run(
            remove_token_cmd, capture_output=True, text=True, timeout=30
        )
        if remove_result.returncode != 0:
            raise click.ClickException(
                f"Failed to get remove-token: {remove_result.stderr.strip()}"
            )

        remove_token = remove_result.stdout.strip().strip('"')
        if not remove_token:
            raise click.ClickException("Empty remove-token from GitHub API")

        # Step 3: Run config.sh remove --token on HPC
        ssh_remove = (
            f"ssh {config.SSH_MUX_OPTS_STR} "
            f"{target} "
            f'"cd {cfg["runner"]["home"]} && ./config.sh remove --token {remove_token}"'
        )
        rm_result = subprocess.run(
            ssh_remove, capture_output=True, text=True, timeout=30, shell=True
        )
        if rm_result.returncode != 0:
            # Non-fatal — the runner might already be deregistered
            click.echo(
                f"  (runner remove returned {rm_result.returncode}, continuing)",
                fg="yellow",
            )

        # Step 4: Delete the runner from GitHub
        delete_cmd = [
            "gh",
            "api",
            f"repos/{repo}/actions/runners/{runner_id}",
            "-X",
            "DELETE",
        ]
        delete_result = subprocess.run(
            delete_cmd, capture_output=True, text=True, timeout=30
        )
        if delete_result.returncode != 0:
            raise click.ClickException(
                f"Failed to delete runner: {delete_result.stderr.strip()}"
            )

        # Step 5: Kill the runner process ON THE COMPUTE NODE (the SSH-vector
        # fix moved run.sh/launcher off the login node, so a login-node pkill
        # would no longer find it). Resolve the lease node, ssh straight to it,
        # and pkill ONLY this runner's launcher — matched by its unique
        # RUNNER_HOME path, NOT the generic "scitex_ci_launcher" name, so peer
        # runners sharing the node are never disturbed.
        # Prefer the scitex-hpc reservation's node when configured (unified
        # lease mgmt). `down` must NEVER book/cancel — it only needs the live
        # node to kill the runner — so we use scitex-hpc's read-only `refresh`
        # (re-discovers job_id/node via squeue), not `ensure_lease`. Legacy
        # configs fall back to the name-filtered squeue query.
        res_name = (cfg.get("reservation") or {}).get("name")
        try:
            if res_name:
                from . import _reservation

                res_cfg = cfg.get("reservation") or {}
                state = _reservation.refresh_state(
                    res_name,
                    host=res_cfg.get("host") or cfg["hpc"].get("ssh_host"),
                    cli=res_cfg.get("cli", "scitex-hpc"),
                )
                node = state.node or None
            else:
                _jobid, node = _resolve_lease(
                    target, cfg["hpc"]["user"], cfg["ci_lease"]["jobname"]
                )
        except (click.ClickException, RuntimeError):
            node = None
        if node:
            compute_cmd = config.compute_ssh_cmd(target, node)
            # pgrep -f matches the full command line; RUNNER_HOME appears in the
            # launcher's argv (bash '<stage>/scitex_ci_launcher.sh') only via the
            # exported env, so match on run.sh's cwd + the home in the wrap-log
            # path instead: pkill the launcher whose RUNNER_HOME env equals ours.
            kill_remote = (
                f"for pid in $(pgrep -u {cfg['hpc']['user']} -f scitex_ci_launcher); do "
                f"  if tr '\\0' ' ' < /proc/$pid/environ 2>/dev/null "
                f"     | grep -q 'RUNNER_HOME={runner_home} '; then "
                f"    pkill -TERM -P $pid 2>/dev/null; kill -TERM $pid 2>/dev/null; "
                f"  fi; "
                f"done; true"
            )
            subprocess.run(
                [*compute_cmd, kill_remote],
                capture_output=True,
                text=True,
                timeout=30,
            )
        else:
            click.echo(
                "  (no RUNNING lease node resolved — skipped compute-node kill; "
                "runner deregistered on GitHub)",
            )

        click.echo(f"Runner {rname} (id={runner_id}) deregistered and stopped.")


# EOF
