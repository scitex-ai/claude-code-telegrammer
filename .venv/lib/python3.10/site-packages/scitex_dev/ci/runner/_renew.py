"""``scitex-dev ci runner renew`` — renew the SLURM CI lease job."""

from __future__ import annotations

import re
import subprocess

import click

from . import config


def register(group: click.Group) -> None:
    @group.command()
    def renew_cmd() -> None:
        """Renew the SLURM CI lease job.

        \b
        Steps:
          1. Query squeue for the current CI lease job.
          2. If no RUNNING job exists, submit a new one.
          3. If a RUNNING job exists with time_left < threshold, submit a
             successor (brief overlap — the runner stays attached via
             srun --overlap).

        \b
        This command is the manual counterpart of the auto-renew cron.
        The lease job name is hard-pinned in config; this NEVER touches
        research lease jobs.

        \b
        Example:
          $ scitex-dev ci runner renew

        \b
        NOTE: when the config names a scitex-hpc `reservation`, lease renewal
        is owned by scitex-hpc (the persistent reservation's SIGUSR1
        auto-resubmit + `reservations refresh`). `renew` then delegates to the
        same book/refresh path as `ensure` — prefer `scitex-dev ci runner
        ensure` (it also restarts offline runners).
        """
        cfg = config.load_runner_config()

        # Unified lease backend: delegate to scitex-hpc when configured.
        if (cfg.get("reservation") or {}).get("name"):
            from ._ensure import ensure_lease

            action, node = ensure_lease(cfg)
            click.echo(
                f"[renew] scitex-hpc reservation lease: {action} "
                f"(node={node or '-'}). Tip: `ci runner ensure` also restarts "
                "offline runners."
            )
            return

        target = config._ssh_target(cfg)
        user = cfg["hpc"]["user"]
        jobname = cfg["ci_lease"]["jobname"]
        threshold_min = cfg["ci_lease"]["renew_threshold_min"]

        # Query squeue
        squeue_cmd = (
            f"ssh {config.SSH_MUX_OPTS_STR} "
            f"{target} "
            f"/apps/slurm/latest/bin/squeue -u {user} "
            f"--name={jobname} --noheader -o '%i %T %M'"
        )
        sq_result = subprocess.run(
            squeue_cmd, capture_output=True, text=True, timeout=30
        )
        if sq_result.returncode != 0:
            raise click.ClickException(f"squeue failed: {sq_result.stderr.strip()}")

        running = []
        for line in sq_result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            running.append(
                {"jobid": parts[0], "state": parts[1], "time_used": parts[2]}
            )

        running_jobs = [r for r in running if r["state"] == "RUNNING"]
        pending_jobs = [r for r in running if r["state"] == "PENDING"]

        if not running_jobs:
            click.echo("[renew] No RUNNING CI lease; submitting new job")
            _submit_lease(cfg, target)
            return

        # Parse time_left (squeue doesn't show it directly via %M,
        # but we can check if the job is still running)
        # For a full threshold check, we'd need %T (time_left) format
        # Fall back: if any are RUNNING and >0, we're fine for now
        click.echo(f"[renew] {len(running_jobs)} RUNNING, {len(pending_jobs)} PENDING")

        if pending_jobs:
            click.echo("[renew] Successor already PENDING; nothing to do")
            return

        # Check if we need to resubmit based on time_left
        # squeue %M gives time_used; we need %T for time_left
        squeue_tl = (
            f"ssh {config.SSH_MUX_OPTS_STR} "
            f"{target} "
            f"/apps/slurm/latest/bin/squeue -u {user} "
            f"--name={jobname} --noheader -o '%i %T %M %T'"
        )
        tl_result = subprocess.run(
            squeue_tl, capture_output=True, text=True, timeout=30
        )
        if tl_result.returncode == 0:
            for line in tl_result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[1] == "RUNNING":
                    tl_str = parts[3]
                    left_min = _parse_slurm_time(tl_str)
                    if left_min <= threshold_min:
                        click.echo(
                            f"[renew] Job {parts[0]} time_left={tl_str} "
                            f"(≤{threshold_min} min threshold); submitting successor"
                        )
                        _submit_lease(cfg, target)
                        return

        click.echo("[renew] No action needed; lease is healthy")


def _parse_slurm_time(s: str) -> int:
    """Parse SLURM [D-]HH:MM:SS to total minutes.

    Handles: ``HH:MM:SS``, ``MM:SS``, single digit minutes, multi-day
    formats like ``1-05:30:00``.  Malformed input returns zero.
    """
    s = s.strip()
    if not s:
        return 0
    days = 0
    if "-" in s:
        try:
            d, s = s.split("-", 1)
            days = int(d)
        except ValueError:
            return 0
    try:
        parts = list(map(int, s.split(":")))
    except ValueError:
        return 0
    if len(parts) == 3:
        h, m, _sec = parts
    elif len(parts) == 2:
        h, m = 0, parts[0]
    elif len(parts) == 1:
        h, m = 0, parts[0]
    else:
        return 0
    return days * 24 * 60 + h * 60 + m


def _submit_lease(cfg: dict, target: str) -> str:
    """Submit a new CI lease job. Returns the new jobid."""
    sbatch_script = cfg["ci_lease"]["sbatch_script"]
    cmd = (
        f"ssh {config.SSH_MUX_OPTS_STR} "
        f"{target} "
        f"cd ~ && /apps/slurm/latest/bin/sbatch "
        f"--output=./slurm_logs/%j.out --error=./slurm_logs/%j.err "
        f"{sbatch_script}"
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=True)
    if result.returncode != 0:
        raise click.ClickException(f"sbatch failed: {result.stderr.strip()}")

    m = re.search(r"Submitted batch job (\d+)", result.stdout)
    if not m:
        raise click.ClickException(f"sbatch: unexpected output: {result.stdout!r}")

    jobid = m.group(1)
    click.echo(f"[renew] Submitted new CI lease job {jobid}")
    return jobid


# EOF
