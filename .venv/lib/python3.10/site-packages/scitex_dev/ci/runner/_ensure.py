"""``scitex-dev ci runner ensure`` — the CI-runner-lifecycle SOLVER.

Problem it solves
-----------------
Spartan SLURM jobs max out at a **7-day walltime**. The CI lease used to be an
ad-hoc hold-job submitted by ``ci runner up`` / ``renew``; when its walltime
expired the runners died and CI broke fleet-wide. scitex-hpc already solves
persistent allocations (``reservations book --persistent`` installs a SIGUSR1
auto-resubmit trap; ``reservations refresh`` re-discovers the new ``job_id``
after the walltime re-key). ``ensure`` rides on that instead of re-inventing
lease renewal.

What ``ensure`` does (idempotent, cron-safe — run it every ~30 min)
-------------------------------------------------------------------
1. **Lease**: make sure a scitex-hpc reservation backs CI.
     * no lease file              → ``reservations book --persistent``
     * lease present but not live  → re-book (``cancel`` the stale file first,
       then ``book``) — covers a truly-dead allocation or a walltime gap the
       auto-resubmit has not yet bridged.
     * lease present + ``refresh`` re-keyed it to a live RUNNING node → healthy,
       no booking. (``refresh`` already handled the 7-day boundary.)
2. **Runners**: ``gh api repos/<owner>/<repo>/actions/runners`` → for each
   desired runner that is offline/missing, restart it on the reservation's node
   via the existing launcher (the same SSH-vector-safe path ``up`` uses).
3. **No-op** when the reservation is healthy and every desired runner is online.

Fail-loud on real errors (booking/exec failures raise); decisions are pure and
unit-tested. The decision functions take plain data so tests exercise the
"re-book when absent/expired", "restart when offline", "no-op when healthy"
logic without any SLURM or GitHub access.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Callable

import click

from . import _fleet, _reservation, config

GhRunner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


# ---------------------------------------------------------------------------
# Desired runner pool
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DesiredRunner:
    """One executor the pool wants online.

    Mirrors the override surface of ``ci runner up`` (``--name`` / ``--home`` /
    ``--repo`` / ``--labels``) so ``ensure`` can restart any pool member by
    reusing the launcher exactly as ``up`` would.
    """

    name: str
    home: str
    repo: str
    labels: str  # comma-joined, as the launcher expects


def desired_runners(cfg: dict) -> list[DesiredRunner]:
    """Resolve the desired runner pool from config.

    Source of truth, in order:
      * ``reservation.runners`` — an explicit list of executors (the
        parallelism knob). Each entry may set ``name`` / ``home`` / ``repo`` /
        ``labels``; anything omitted falls back to the top-level ``runner.*`` /
        ``github.default_repo`` defaults.
      * absent / empty           → a single executor from ``runner.*`` (count 1).

    Keeping the count here (not as a bare integer) means ``ensure`` knows each
    member's NAME, so it can ask GitHub per-name whether that specific executor
    is online — robust when peers share a node.
    """
    default_repo = cfg["github"]["default_repo"]
    default_name = cfg["runner"]["name"]
    default_home = cfg["runner"]["home"]
    default_labels = ",".join(str(x) for x in cfg["runner"]["labels"])

    entries = (cfg.get("reservation") or {}).get("runners") or []
    if not entries:
        return [
            DesiredRunner(
                name=default_name,
                home=default_home,
                repo=default_repo,
                labels=default_labels,
            )
        ]

    pool: list[DesiredRunner] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise click.ClickException(
                "reservation.runners entries must be mappings with at least "
                "a 'name' and 'home'."
            )
        name = entry.get("name") or default_name
        home = entry.get("home")
        if not home:
            raise click.ClickException(
                f"reservation.runners entry {name!r} is missing required 'home' "
                "(each executor needs its own _work/install dir)."
            )
        repo = entry.get("repo") or default_repo
        labels_val = entry.get("labels")
        if labels_val is None:
            labels = default_labels
        elif isinstance(labels_val, (list, tuple)):
            labels = ",".join(str(x) for x in labels_val)
        else:
            labels = str(labels_val)
        pool.append(DesiredRunner(name=name, home=home, repo=repo, labels=labels))
    return pool


# ---------------------------------------------------------------------------
# Pure decision logic (unit-tested)
# ---------------------------------------------------------------------------


def decide_lease_action(
    get_state: _reservation.ReservationState,
    refreshed_state: _reservation.ReservationState | None,
) -> str:
    """Decide what to do with the lease. Pure — drives :func:`ensure_lease`.

    ``get_state`` is the cheap file-only probe (``reservations get``).
    ``refreshed_state`` is the squeue-validated probe (``reservations
    refresh``), or ``None`` when we skipped refresh because the lease file was
    absent.

    Returns one of:
      * ``"book"``     — no lease file at all → book a fresh persistent lease.
      * ``"rebook"``   — lease file present but not backed by a live RUNNING
        node even after refresh → cancel the stale file, then book.
      * ``"noop"``     — lease is live (refresh re-keyed it if needed).
    """
    if not get_state.present:
        return "book"
    # Lease file exists; trust the squeue-validated refresh for liveness.
    if refreshed_state is not None and refreshed_state.live:
        return "noop"
    return "rebook"


def offline_runner_names(
    desired: list[DesiredRunner],
    runners_by_repo: dict[str, list[dict]],
) -> list[str]:
    """Return the names of desired runners that are NOT online. Pure.

    ``runners_by_repo`` maps ``"<owner>/<repo>"`` → the parsed
    ``actions/runners`` list (each item ``{"name", "status", ...}``). A desired
    runner is "offline" if its repo has no runner with a matching name, or that
    runner's ``status`` is not ``"online"`` (covers both offline and missing —
    exactly the task's "offline/missing" set).
    """
    offline: list[str] = []
    for d in desired:
        runners = runners_by_repo.get(d.repo, [])
        match = next((r for r in runners if r.get("name") == d.name), None)
        if match is None or match.get("status") != "online":
            offline.append(d.name)
    return offline


# ---------------------------------------------------------------------------
# gh layer
# ---------------------------------------------------------------------------


def _default_gh_runner(args: list[str]) -> "subprocess.CompletedProcess[str]":
    """Real ``gh`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def fetch_runners(
    repo: str,
    *,
    gh_runner: GhRunner | None = None,
) -> list[dict]:
    """Return the parsed ``actions/runners`` list for ``repo``.

    The list endpoint returns an OBJECT ``{total_count, runners: [...]}``; we
    ``--jq`` the ``.runners[]`` array (the same guard ``_status.py`` documents:
    a bare ``.[]`` walks the object's values and errors). Raises on gh failure
    — a CI lease with no GitHub visibility is a real error, not a no-op.
    """
    run = gh_runner or _default_gh_runner
    r = run(
        [
            "api",
            f"repos/{repo}/actions/runners",
            "--jq",
            "[.runners[] | {name, status, busy}]",
        ]
    )
    if r.returncode != 0:
        raise click.ClickException(
            f"`gh api repos/{repo}/actions/runners` failed "
            f"(rc={r.returncode}): {(r.stderr or r.stdout).strip()}"
        )
    try:
        data = json.loads(r.stdout) if (r.stdout or "").strip() else []
    except json.JSONDecodeError as exc:
        raise click.ClickException(
            f"gh api returned non-JSON for {repo} runners: {exc}"
        )
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# IO orchestration
# ---------------------------------------------------------------------------


@dataclass
class EnsureResult:
    """What one ``ensure`` pass did — returned so tests/cron can assert."""

    lease_action: str  # "book" | "rebook" | "noop"
    lease_node: str = ""
    restarted: list[str] = field(default_factory=list)
    online: list[str] = field(default_factory=list)


def ensure_lease(
    cfg: dict,
    *,
    hpc_runner: _reservation.HpcRunner | None = None,
) -> tuple[str, str]:
    """Make the scitex-hpc reservation healthy. Returns ``(action, node)``.

    Idempotent: when the lease is live this is two cheap CLI calls (get +
    refresh) and no booking. ``action`` is the value from
    :func:`decide_lease_action`; ``node`` is the live compute node (empty if a
    fresh book has not yet allocated, in which case runner restart is skipped
    this pass and the next cron tick picks it up once SLURM schedules it).
    """
    res_cfg = cfg.get("reservation") or {}
    name = res_cfg.get("name")
    if not name:
        raise click.ClickException(
            "reservation.name is required for `ci runner ensure` — name the "
            "scitex-hpc reservation that backs CI (see the ci-runner skill)."
        )
    cli = res_cfg.get("cli", "scitex-hpc")
    host = res_cfg.get("host") or cfg["hpc"].get("ssh_host")

    state = _reservation.get_state(name, host=host, cli=cli, hpc_runner=hpc_runner)
    refreshed: _reservation.ReservationState | None = None
    if state.present:
        refreshed = _reservation.refresh_state(
            name, host=host, cli=cli, hpc_runner=hpc_runner
        )

    action = decide_lease_action(state, refreshed)

    if action == "noop":
        assert refreshed is not None  # present+live path
        return action, refreshed.node

    if action == "rebook":
        _reservation.cancel(name, host=host, cli=cli, hpc_runner=hpc_runner)

    book_args = _reservation.build_book_args(res_cfg, host=host)
    booked = _reservation.book(
        name, book_args=book_args, cli=cli, hpc_runner=hpc_runner
    )
    return action, booked.node


def restart_runner_on_node(
    cfg: dict,
    runner: DesiredRunner,
    node: str,
    *,
    launcher_path: str | None = None,
) -> None:
    """Restart one runner on the reservation's ``node`` via the launcher.

    Reuses the exact SSH-vector-safe path of ``ci runner up`` (stage the
    launcher on the shared FS, then ``ssh -J <login> <node> 'setsid nohup bash
    launcher'``) so ``ensure`` never re-implements launch mechanics. The launch
    is idempotent enough for a watchdog: a fresh ``./run.sh`` re-registers the
    runner with GitHub (the launcher mints a registration token), and starting
    a second listener for a runner that is actually already up is harmless —
    but ``ensure`` only calls this for runners GitHub reports offline/missing.
    """
    from ._up import (
        _build_compute_run_script,
        _build_launcher_stage_script,
        _staging_paths,
    )

    target = config._ssh_target(cfg)
    gh_token = config.get_gh_token(cfg)
    apptainer = cfg["hpc"]["apptainer"]
    sif = cfg["hpc"]["sif"]
    wrap_log = cfg["runner"]["wrap_log"]

    pkg_launcher = launcher_path or _shipped_launcher_path()
    with open(pkg_launcher, "r") as f:
        launcher_content = f.read()

    stage_dir, wrapper_remote, _launcher_remote = _staging_paths(runner.home)
    stage_script = _build_launcher_stage_script(
        runner_home=runner.home,
        launcher_content=launcher_content,
    )
    ssh_opts = config.SSH_MUX_OPTS

    mkdir = subprocess.run(
        ["ssh", *ssh_opts, target, f"mkdir -p '{stage_dir}'"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if mkdir.returncode != 0:
        raise click.ClickException(
            f"Failed to create staging dir {stage_dir}: {mkdir.stderr.strip()}"
        )

    # Stage the launcher via stdin (no scp temp file needed for ensure's path:
    # the staging script is self-contained and small).
    stage = subprocess.run(
        [
            "ssh",
            *ssh_opts,
            target,
            f"cat > '{wrapper_remote}' && bash '{wrapper_remote}'",
        ],
        input=stage_script,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if stage.returncode != 0:
        raise click.ClickException(
            f"Failed to stage launcher for {runner.name}: {stage.stderr.strip()}"
        )

    run_script = _build_compute_run_script(
        runner_home=runner.home,
        gh_token=gh_token,
        gh_repo=runner.repo,
        runner_name=runner.name,
        runner_labels=runner.labels,
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
            f"Failed to (re)start runner {runner.name} on {node}: "
            f"{run_result.stderr.strip()}"
        )


def _shipped_launcher_path() -> str:
    import os

    pkg_launcher = os.path.join(os.path.dirname(__file__), "launcher.sh")
    if not os.path.exists(pkg_launcher):
        raise click.ClickException(
            "launcher.sh not found in the scitex-dev package; pass --launcher."
        )
    return pkg_launcher


def register(group: click.Group) -> None:
    @group.command("ensure")
    @click.option(
        "--launcher",
        default=None,
        help="Path to launcher.sh on the HPC host. Default: shipped copy.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Report the decisions (book/rebook/noop + which runners are "
        "offline) WITHOUT booking or restarting anything.",
    )
    @click.option(
        "--fleet",
        "fleet",
        is_flag=True,
        default=False,
        help="ALSO sweep ALL per-repo runners on the lease node: in ONE "
        "`reservations exec`, auto-discover every actions-runner-* home and "
        "relaunch any whose Runner.Listener is dead (keeps the ~60-runner "
        "self-hosted fleet alive). Auto-on when reservation.fleet: true.",
    )
    @click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
    def ensure_cmd(
        launcher: str | None, dry_run: bool, fleet: bool, as_json: bool
    ) -> None:
        """Keep the CI runners alive across the 7-day SLURM walltime (the SOLVER).

        \b
        Idempotent + cron-safe. One pass:
          1. Ensure a scitex-hpc *persistent* reservation backs CI
             (book if absent; cancel+rebook if the allocation died; the
             persistent reservation's own SIGUSR1 auto-resubmit + this
             pass's `reservations refresh` bridge the 7-day walltime).
          2. For each desired runner GitHub reports offline/missing, restart
             it on the reservation's node via the launcher (same path as `up`).
          3. No-op when the reservation is healthy and N runners are online.

        \b
        With --fleet (or reservation.fleet: true in config), ALSO keep every
        per-repo runner on the lease alive: in ONE `reservations exec` to the
        node, auto-discover each actions-runner-* home and relaunch any whose
        Runner.Listener process is dead — so the ~60-runner self-hosted fleet
        doesn't erode as runners die. One cron tick -> lease + ALL runners.

        \b
        Suggested cron (well inside the 7-day window):
          */30 * * * *  scitex-dev ci runner ensure --fleet

        \b
        Examples:
          $ scitex-dev ci runner ensure
          $ scitex-dev ci runner ensure --dry-run --json
          $ scitex-dev ci runner ensure --fleet            # lease + all runners
          $ scitex-dev ci runner ensure --fleet --dry-run  # report fleet decisions
        """
        cfg = config.load_runner_config()
        pool = desired_runners(cfg)

        if dry_run:
            result = _ensure_dry_run(cfg, pool)
        else:
            result = run_ensure(cfg, pool, launcher_path=launcher)

        # Fleet pass: keep ALL per-repo runners on the lease alive (one
        # `reservations exec` to the node — no per-repo ssh from this host).
        # Runs when --fleet is passed OR the config opts in (reservation.fleet:
        # true), so the existing */30 cron picks it up once the knob is set.
        fleet_result = None
        if fleet or _fleet.fleet_enabled(cfg):
            if result.lease_node:
                fleet_result = _fleet.run_fleet_ensure(
                    cfg,
                    node=result.lease_node,
                    dry_run=dry_run,
                    launcher_path=launcher,
                )
            else:
                # No allocated node yet (freshly booked / PENDING); the
                # fleet sweep needs a node to ssh to. Defer to the next tick.
                click.echo(
                    "fleet: lease has no allocated node yet; deferring fleet "
                    "sweep to the next pass.",
                    err=True,
                )

        if as_json:
            payload = {
                "lease_action": result.lease_action,
                "lease_node": result.lease_node,
                "restarted": result.restarted,
                "online": result.online,
                "desired": [d.name for d in pool],
                "dry_run": dry_run,
            }
            if fleet_result is not None:
                payload["fleet"] = {
                    "alive": fleet_result.alive,
                    "restarted": fleet_result.restarted,
                    "would_restart": fleet_result.would_restart,
                    "failed": fleet_result.failed,
                }
            click.echo(json.dumps(payload, indent=2))
            return

        click.echo(f"lease: {result.lease_action} (node={result.lease_node or '-'})")
        if result.restarted:
            click.echo(f"restarted: {', '.join(result.restarted)}")
        click.echo(
            f"online: {len(result.online)}/{len(pool)} "
            f"({', '.join(result.online) or 'none'})"
        )
        if fleet_result is not None:
            fr = fleet_result
            n_total = fr.total
            if dry_run:
                click.echo(
                    f"fleet: alive={len(fr.alive)} "
                    f"would_restart={len(fr.would_restart)} "
                    f"failed={len(fr.failed)} (of {n_total} discovered)"
                )
            else:
                click.echo(
                    f"fleet: alive={len(fr.alive)} "
                    f"restarted={len(fr.restarted)} "
                    f"failed={len(fr.failed)} (of {n_total} discovered)"
                )


def _ensure_dry_run(cfg: dict, pool: list[DesiredRunner]) -> EnsureResult:
    """Report decisions without acting. Used by ``--dry-run``."""
    res_cfg = cfg.get("reservation") or {}
    name = res_cfg.get("name")
    if not name:
        raise click.ClickException(
            "reservation.name is required for `ci runner ensure`."
        )
    cli = res_cfg.get("cli", "scitex-hpc")
    host = res_cfg.get("host") or cfg["hpc"].get("ssh_host")

    state = _reservation.get_state(name, host=host, cli=cli)
    refreshed = (
        _reservation.refresh_state(name, host=host, cli=cli) if state.present else None
    )
    action = decide_lease_action(state, refreshed)
    node = refreshed.node if (refreshed and refreshed.live) else ""

    runners_by_repo = _runners_by_repo(pool)
    offline = offline_runner_names(pool, runners_by_repo)
    online = [d.name for d in pool if d.name not in offline]
    return EnsureResult(
        lease_action=action,
        lease_node=node,
        restarted=[],  # dry-run never restarts
        online=online,
    )


def _runners_by_repo(
    pool: list[DesiredRunner],
    *,
    gh_runner: GhRunner | None = None,
) -> dict[str, list[dict]]:
    """Fetch ``actions/runners`` once per distinct repo in the pool."""
    repos = sorted({d.repo for d in pool})
    return {repo: fetch_runners(repo, gh_runner=gh_runner) for repo in repos}


def run_ensure(
    cfg: dict,
    pool: list[DesiredRunner],
    *,
    launcher_path: str | None = None,
    hpc_runner: _reservation.HpcRunner | None = None,
    gh_runner: GhRunner | None = None,
    restart_fn: Callable[[dict, DesiredRunner, str], None] | None = None,
) -> EnsureResult:
    """Execute one full ``ensure`` pass. The IO entry point.

    The ``hpc_runner`` / ``gh_runner`` / ``restart_fn`` seams let tests drive
    the whole pass with real fakes (no mocks of our own code): a fake
    ``hpc_runner`` returns canned ``scitex-hpc`` CLI output, a fake
    ``gh_runner`` returns canned runner lists, and a fake ``restart_fn``
    records which runners were (re)started. Production leaves them ``None``.
    """
    action, node = ensure_lease(cfg, hpc_runner=hpc_runner)

    runners_by_repo = _runners_by_repo(pool, gh_runner=gh_runner)
    offline = offline_runner_names(pool, runners_by_repo)

    restarted: list[str] = []
    if offline:
        if not node:
            # Lease was just booked and SLURM hasn't allocated a node yet;
            # nothing to restart onto. The next cron tick restarts once the
            # reservation is RUNNING. Not an error — report and move on.
            click.echo(
                "lease has no allocated node yet (freshly booked / still "
                "PENDING); deferring runner restart to the next pass.",
                err=True,
            )
        else:
            do_restart = restart_fn or (
                lambda c, r, n: restart_runner_on_node(
                    c, r, n, launcher_path=launcher_path
                )
            )
            by_name = {d.name: d for d in pool}
            for rname in offline:
                do_restart(cfg, by_name[rname], node)
                restarted.append(rname)

    online = [d.name for d in pool if d.name not in offline]
    return EnsureResult(
        lease_action=action,
        lease_node=node,
        restarted=restarted,
        online=online,
    )


# EOF
