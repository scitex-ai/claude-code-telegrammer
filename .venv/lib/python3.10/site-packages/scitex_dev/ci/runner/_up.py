"""``scitex-dev ci runner up`` — start the persistent runner on HPC.

SSH-vector fix (2026-06-17 admin incident, ~20 srun/login-node ceiling): the
runner is launched by ssh'ing STRAIGHT to the lease's compute node (ProxyJump
through a login node) and detaching there with ``setsid nohup``. The ssh exits
immediately, so provisioning a runner leaves NO persistent login-node ``srun``
client (the old path ran ``setsid nohup srun --overlap`` on a login node, whose
``srun`` CLIENT lingered for the runner's whole life as a stdio tether — one per
runner, ~76 across the fleet). The runner's run.sh / Runner.Listener run on the
compute node either way; only the tether is removed.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import click

from . import config

# Absolute SLURM paths: the lease query runs in a NON-interactive login shell
# where SLURM is not on PATH (so a bare `squeue` fails). Match this.
_SQUEUE = "/apps/slurm/latest/bin/squeue"


def _staging_paths(runner_home: str) -> tuple[str, str, str]:
    """Return (stage_dir, wrapper_remote, launcher_remote) on the SHARED FS.

    Staging MUST be on a shared filesystem, never /tmp: Spartan has multiple
    round-robin login nodes and each ssh WITHOUT connection-sharing can land
    on a different node, whose /tmp is node-local; and the launcher is staged on
    a login node but EXECUTED on the compute node, which shares the project FS
    but not /tmp. runner_home is a punim0264 project dir (mounted on every
    node), so stage under its parent.
    """
    stage_dir = os.path.join(os.path.dirname(runner_home), "run")
    return (
        stage_dir,
        os.path.join(stage_dir, "scitex_ci_wrapper.sh"),
        os.path.join(stage_dir, "scitex_ci_launcher.sh"),
    )


def _build_launcher_stage_script(
    *,
    runner_home: str,
    launcher_content: str,
) -> str:
    """Build the LOGIN-NODE staging script (pure — no I/O).

    Runs on a login node via the multiplexed ssh and does ONLY cheap shared-FS
    file work — write the launcher to the shared staging dir, chmod it. It starts
    NO long-lived process, so this ssh leaves nothing behind on the login node
    (no ``srun`` client, no lingering shell). The launch itself happens in a
    SEPARATE ssh straight to the compute node (see ``_build_compute_run_script``)
    — that is what eliminates the per-runner persistent login-node ``srun``.

    /tmp would be node-local on multi-login-node Spartan and invisible to the
    compute node; the shared project FS (``runner_home``'s parent) is mounted on
    every node, so the launcher staged here is the same file the compute node
    runs.
    """
    stage_dir, _wrapper_remote, launcher_remote = _staging_paths(runner_home)
    return f"""#!/bin/bash
set -euo pipefail
mkdir -p '{stage_dir}'
cat > '{launcher_remote}' << 'LAUNCHER_EOF'
{launcher_content}
LAUNCHER_EOF
chmod +x '{launcher_remote}'
echo "LAUNCHER_STAGED:{launcher_remote}"
"""


def _build_compute_run_script(
    *,
    runner_home: str,
    gh_token: str,
    gh_repo: str,
    runner_name: str,
    runner_labels: str,
    apptainer: str,
    sif: str,
    wrap_log: str,
) -> str:
    """Build the COMPUTE-NODE run script (pure — no I/O).

    This is the body run via ``ssh -J <login> <compute-node>``. It exports the
    runner env and starts the staged launcher with ``setsid nohup … &`` so the
    runner (run.sh → Runner.Listener) is fully detached ON the compute node and
    the ssh connection returns IMMEDIATELY. No ``srun`` is involved: we are
    already on the lease's node (reached via ProxyJump), so there is no
    login-node ``srun`` client tethering the runner — the whole point of the
    SSH-vector fix.

    The launcher itself no longer wraps ``run.sh`` in ``srun --overlap`` — it
    runs run.sh directly, because this script already placed it on the node.
    """
    _stage_dir, _wrapper_remote, launcher_remote = _staging_paths(runner_home)
    return f"""#!/bin/bash
set -euo pipefail

export GH_TOKEN='{gh_token}'
export GH_REPO='{gh_repo}'
export RUNNER_NAME='{runner_name}'
export RUNNER_LABELS='{runner_labels}'
export RUNNER_HOME='{runner_home}'
export APPTAINER='{apptainer}'
export SIF='{sif}'
export RUNNER_VERSION='2.328.0'

# Detach the runner on THIS (compute) node. setsid+nohup orphan it to init so it
# survives this ssh closing; the ssh exits the instant this returns, leaving NO
# persistent login-node srun/ssh client behind.
setsid nohup bash '{launcher_remote}' </dev/null >'{wrap_log}' 2>&1 &
disown
echo "RUNNER_STARTED:$!"
"""


def _resolve_lease_node(cfg: dict, target: str) -> tuple[str, str]:
    """Resolve the lease's ``(jobid, node)`` for ``up``/``down``.

    Unified lease management (operator: "regarding lease, use scitex-hpc"):
    when the config names a scitex-hpc reservation (``reservation.name``), the
    lease IS that persistent reservation — ``ensure_lease`` books/refreshes it
    through scitex-hpc, which owns the 7-day-walltime auto-resubmit. This
    replaces the standalone ``ci_lease`` hold-job so renewal lives in one place.

    Back-compat: a config WITHOUT a ``reservation`` block falls back to the
    legacy name-filtered squeue query (``_resolve_lease``) so existing operator
    setups keep working until they migrate.

    Returns ``(jobid, node)``; ``jobid`` may be empty under the reservation path
    (scitex-hpc tracks it internally and we only need the node to ssh to).
    """
    res_name = (cfg.get("reservation") or {}).get("name")
    if res_name:
        # Local import to avoid a module import cycle (_ensure imports _up).
        from . import _ensure

        _action, node = _ensure.ensure_lease(cfg)
        if not node:
            raise click.ClickException(
                f"scitex-hpc reservation {res_name!r} has no allocated node yet "
                "(freshly booked / still PENDING). Re-run once SLURM schedules "
                "it (or check `scitex-hpc reservations get/refresh`)."
            )
        return "", node
    return _resolve_lease(target, cfg["hpc"]["user"], cfg["ci_lease"]["jobname"])


def _resolve_lease(target: str, user: str, jobname: str) -> tuple[str, str]:
    """Return ``(jobid, node)`` of the RUNNING lease, or raise ClickException.

    Queries the login node (via the multiplexed ssh) for the lease job's id AND
    its allocated node (``%N``) — we need the node to ssh straight to it. A
    PENDING lease has no node and never allocates, so only RUNNING rows count.
    """
    lease_info = subprocess.run(
        [
            "ssh",
            *config.SSH_MUX_OPTS,
            target,
            f"{_SQUEUE} -u {user} --name={jobname} --noheader -o '%i %T %N'",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if lease_info.returncode != 0 or not lease_info.stdout.strip():
        raise click.ClickException(
            f"No RUNNING CI lease job found for name={jobname}. "
            f"Run 'scitex-dev ci runner renew' first to submit a lease job."
        )
    for line in lease_info.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "RUNNING" and parts[2]:
            return parts[0], parts[2]
    raise click.ClickException(
        f"No RUNNING CI lease job with an allocated node for name={jobname}. "
        f"squeue output: {lease_info.stdout.strip()!r}"
    )


def register(group: click.Group) -> None:
    @group.command()
    @click.option(
        "--launcher",
        default=None,
        help="Path to launcher.sh on the HPC host. Default: shipped copy.",
    )
    @click.option(
        "--replace-runner",
        is_flag=True,
        default=False,
        help="Replace any existing runner with the same name.",
    )
    @click.option(
        "--name",
        "name_override",
        default=None,
        help="Override runner.name from config — provision a SECOND/THIRD "
        "executor (e.g. spartan-cpu-runner-02) for a parallel matrix. "
        "Pair with --home so each runner has its own work/install dir.",
    )
    @click.option(
        "--home",
        "home_override",
        default=None,
        help="Override runner.home — REQUIRED to differ per runner when "
        "running multiple executors (each needs its own _work/install dir).",
    )
    @click.option(
        "--repo",
        "repo_override",
        default=None,
        help="Override github.default_repo — provision a runner for ANOTHER "
        "ecosystem repo (e.g. ywatanabe1989/scitex-todo) on the SAME shared "
        "Spartan lease. This is the ecosystem-rollout path: ywatanabe1989 is a "
        "User (no org runner pool), so each repo needs its own registration, "
        "but they all overlap one lease/node. Pair with --name + --home.",
    )
    @click.option(
        "--labels",
        "labels_override",
        default=None,
        help="Override runner.labels (comma list) for this runner, e.g. "
        "'self-hosted,spartan-cpu,scitex-ci' to also match a repo whose "
        "workflow still targets the legacy label. Default: runner.labels from config.",
    )
    def up_cmd(
        launcher: str | None,
        replace_runner: bool,
        name_override: str | None,
        home_override: str | None,
        repo_override: str | None,
        labels_override: str | None,
    ) -> None:
        """Start the persistent GitHub Actions runner on the HPC compute node.

        \b
        How it works (SSH-vector-safe — no per-runner login-node srun client):
          1. Resolve the RUNNING CI lease's jobid AND allocated compute node.
          2. Stage launcher.sh on the shared FS via a login-node ssh that does
             ONLY file I/O (no long-lived process — leaves nothing behind).
          3. SSH STRAIGHT to the compute node (ProxyJump through a login node)
             and `setsid nohup bash launcher.sh &` — the ssh returns at once,
             so the runner runs ON the lease's node with ZERO persistent
             login-node srun/ssh client.
          4. The launcher downloads + caches the GitHub runner tarball,
             registers the runner, and runs a persistent run.sh loop on the node.

        \b
        The GH_TOKEN is passed via env (never in argv) to avoid leaking it.

        \b
        Examples:
          $ scitex-dev ci runner up
          $ scitex-dev ci runner up --replace-runner
          # add a second executor (home-clean parallel matrix):
          $ scitex-dev ci runner up --name spartan-cpu-runner-02 \\
              --home /data/.../punim0264/.../ci/actions-runner-02
          # ecosystem rollout: a runner for ANOTHER repo on the SAME lease
          $ scitex-dev ci runner up --repo ywatanabe1989/scitex-todo \\
              --name spartan-cpu-todo-01 \\
              --home /data/.../punim0264/.../ci/actions-runner-todo \\
              --labels self-hosted,spartan-cpu,scitex-ci
        """
        cfg = config.load_runner_config()
        target = config._ssh_target(cfg)
        gh_token = config.get_gh_token(cfg)
        runner_home = home_override or cfg["runner"]["home"]
        wrap_log = cfg["runner"]["wrap_log"]
        runner_name = name_override or cfg["runner"]["name"]
        runner_labels = labels_override or ",".join(cfg["runner"]["labels"])
        gh_repo = repo_override or cfg["github"]["default_repo"]
        apptainer = cfg["hpc"]["apptainer"]
        sif = cfg["hpc"]["sif"]

        # Determine launcher path — shipped copy in the package
        pkg_launcher = os.path.join(os.path.dirname(__file__), "launcher.sh")
        if launcher:
            launcher_path = launcher
        elif os.path.exists(pkg_launcher):
            launcher_path = pkg_launcher
        else:
            raise click.ClickException(
                "launcher.sh not found. "
                "Check the scitex-dev package or pass --launcher PATH."
            )

        # Read launcher.sh content (staged onto the shared FS below).
        with open(launcher_path, "r") as f:
            launcher_content = f.read()

        # Resolve the RUNNING lease's jobid + allocated compute node — we ssh
        # straight to that node so the runner runs there with no login srun.
        # Prefers the scitex-hpc persistent reservation when configured
        # (unified lease mgmt — scitex-hpc owns the 7-day-walltime renewal);
        # falls back to the legacy name-filtered squeue query otherwise.
        jobid, node = _resolve_lease_node(cfg, target)

        # --- step 1: stage the launcher on the shared FS (login-node ssh; only
        #     cheap file I/O, no lingering process) ----------------------------
        stage_dir, wrapper_remote, _launcher_remote = _staging_paths(runner_home)
        stage_script = _build_launcher_stage_script(
            runner_home=runner_home,
            launcher_content=launcher_content,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as tmp:
            tmp.write(stage_script)
            tmp_path = tmp.name

        ssh_opts = config.SSH_MUX_OPTS

        mkdir_result = subprocess.run(
            ["ssh", *ssh_opts, target, f"mkdir -p '{stage_dir}'"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if mkdir_result.returncode != 0:
            os.unlink(tmp_path)
            raise click.ClickException(
                f"Failed to create staging dir {stage_dir}: {mkdir_result.stderr.strip()}"
            )

        scp_cmd = ["scp", *ssh_opts, tmp_path, f"{target}:{wrapper_remote}"]
        scp_result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
        if scp_result.returncode != 0:
            os.unlink(tmp_path)
            raise click.ClickException(f"SCP failed: {scp_result.stderr.strip()}")
        os.unlink(tmp_path)

        stage_result = subprocess.run(
            ["ssh", *ssh_opts, target, f"bash '{wrapper_remote}'"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if stage_result.returncode != 0:
            raise click.ClickException(
                f"Failed to stage launcher: {stage_result.stderr.strip()}"
            )

        # --- step 2: launch ON the compute node via ProxyJump; the ssh exits
        #     immediately, leaving NO persistent login-node srun/ssh client ----
        run_script = _build_compute_run_script(
            runner_home=runner_home,
            gh_token=gh_token,
            gh_repo=gh_repo,
            runner_name=runner_name,
            runner_labels=runner_labels,
            apptainer=apptainer,
            sif=sif,
            wrap_log=wrap_log,
        )
        compute_cmd = config.compute_ssh_cmd(target, node)
        run_result = subprocess.run(
            [*compute_cmd, "bash -s"],
            input=run_script,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if run_result.returncode != 0:
            raise click.ClickException(
                f"Failed to start runner on compute node {node}: "
                f"{run_result.stderr.strip()}"
            )

        click.echo(run_result.stdout.strip())
        click.echo(
            f"Runner {runner_name} started on compute node {node} "
            f"(lease job {jobid}); no login-node srun client created."
        )


# EOF
