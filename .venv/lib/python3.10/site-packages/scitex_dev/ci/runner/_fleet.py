"""``scitex-dev ci runner ensure --fleet`` — keep ALL per-repo runners alive.

Problem it solves
-----------------
The self-hosted CI migration registered ~60+ GitHub Actions runners (one per
ecosystem repo, because ``ywatanabe1989`` is a User account with no org-wide
runner pool) that all overlap ONE scitex-hpc lease node. Each runner is a
``Runner.Listener`` process on that compute node. Processes die on node events
(OOM, transient kills, a job that crashes the listener); when they do, that
repo's CI/releases silently queue forever. The single-repo ``ensure`` pass only
watches the ONE runner named in ``ci-runner.yaml`` — so the migration erodes as
the other ~60 runners die unnoticed.

What the fleet pass does (idempotent, cron-safe)
------------------------------------------------
In **ONE** ``ssh -J`` to the lease's compute node (login-
node hygiene is critical — the 2026-06-17 admin incident capped login-node ssh
connections, so we MUST NOT ssh per-repo from the dev host), the pass:

1. **Auto-discovers** every ``<ci_root>/actions-runner-*`` directory on the node
   (the per-repo runner homes; the no-suffix config-managed ``actions-runner``
   home is handled by the existing single-repo path and is intentionally NOT
   matched by the ``-*`` glob).
2. For each, decides liveness by the runner's OWN argv: a runner is alive iff a
   process matches ``<dir>/bin/Runner.Listener`` (the listener carries its home
   dir in argv — verified live on Spartan — so this is unambiguous even when 70+
   peers share the node; no fragile ``/proc/<pid>/environ`` scan needed).
3. For each DEAD runner, relaunches it via the **shipped launcher** — the exact
   mechanism ``ci runner up`` / ``ensure`` already use (re-stage launcher.sh on
   the shared FS, ``setsid nohup bash launcher``). The launcher skips
   registration when ``.runner`` exists (every discovered runner is already
   registered), so a restart only needs ``RUNNER_HOME`` + a valid ``GH_TOKEN``;
   ``GH_REPO`` / ``RUNNER_NAME`` are read back from each dir's ``.runner`` so the
   launcher's env contract (and its TERM/INT deregister trap) stays satisfied.

Reports ``alive=N restarted=M`` (``--dry-run`` reports ``would_restart`` and
touches nothing). Fail-loud: a non-zero ``ssh`` to the node raises.

Why this is ONE ssh, not 60 (and why NOT ``reservations exec``)
--------------------------------------------------------------
The whole discover+restart loop runs on the node in ONE bash script delivered
over a SINGLE ``ssh -J <login> <compute-node>`` (``config.compute_ssh_cmd`` —
the EXACT vector ``ci runner up`` / the single-repo restart already use). The
dev host never ssh's to the node per-repo; the entire fleet sweep is one
compute-node ssh (transiting one login node), so login-node hygiene holds.

We deliberately do NOT launch through ``scitex-hpc reservations exec``: that
runs the command as an ``srun --jobid --overlap`` job STEP, and SLURM reaps the
step's whole process group when the step exits — killing even ``setsid nohup``
children (verified live on Spartan: runners launched via ``reservations exec``
died the instant the step returned). ``ssh -J`` to the node is a plain sshd
session, so ``setsid nohup`` truly orphans the runner to init and it survives —
the same reason ``up`` reaches the node by ssh, not srun. The lease NODE NAME
comes from the scitex-hpc reservation state (``ensure_lease``); scitex-hpc still
owns the lease, we just attach to its node the durable way.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Callable

import click

from . import config

# An injectable seam for the compute-node exec: (script) -> CompletedProcess.
# Tests pass a real fake that records the script + returns canned output; prod
# uses :func:`_default_compute_exec` (ssh -J to the lease node).
ComputeExec = Callable[[str], "subprocess.CompletedProcess[str]"]

# Machine-parseable line tags emitted by the on-node script (tab-separated so a
# dir path with spaces — there are none on the lease, but be safe — never
# confuses the parser).
_TAG_ALIVE = "FLEET_ALIVE"
_TAG_RESTARTED = "FLEET_RESTARTED"
_TAG_WOULD = "FLEET_WOULD_RESTART"
_TAG_FAILED = "FLEET_FAILED"
_TAG_SUMMARY = "FLEET_SUMMARY"


@dataclass
class FleetResult:
    """What one fleet pass observed/did — returned so tests/cron can assert."""

    alive: list[str] = field(default_factory=list)
    restarted: list[str] = field(default_factory=list)
    would_restart: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.alive)
            + len(self.restarted)
            + len(self.failed)
            + len(self.would_restart)
        )


def _shipped_launcher_path() -> str:
    """Path to launcher.sh shipped in this package (single source of truth)."""
    pkg_launcher = os.path.join(os.path.dirname(__file__), "launcher.sh")
    if not os.path.exists(pkg_launcher):
        raise click.ClickException(
            "launcher.sh not found in the scitex-dev package; pass --launcher."
        )
    return pkg_launcher


def fleet_ci_root(cfg: dict) -> str:
    """Resolve the directory that holds the per-repo runner homes.

    Source of truth, in order:
      * ``reservation.fleet_root`` — explicit override (rare).
      * the PARENT of ``runner.home`` — the per-repo runner homes are siblings
        of the config-managed runner home (``.../ci/actions-runner`` →
        ``.../ci/actions-runner-<repo>``), so their common parent is where the
        ``actions-runner-*`` glob is rooted. This keeps one source of truth: the
        operator already configures ``runner.home``.
    """
    res = cfg.get("reservation") or {}
    explicit = res.get("fleet_root")
    if explicit:
        return str(explicit)
    home = cfg["runner"]["home"]
    return os.path.dirname(home.rstrip("/"))


def fleet_enabled(cfg: dict) -> bool:
    """True when config opts into the fleet pass.

    Auto-on when the ``reservation`` block carries ``fleet: true`` (or a
    ``repos:`` list, kept for forward-compat as an explicit allow-list knob).
    The ``--fleet`` CLI flag forces it regardless; this only governs the
    auto-trigger so the existing cron picks up the fleet sweep once the operator
    flips the knob — no separate command needed.
    """
    res = cfg.get("reservation") or {}
    if res.get("fleet") is True:
        return True
    if res.get("repos"):
        return True
    return False


def build_fleet_script(
    *,
    ci_root: str,
    launcher_content: str,
    gh_token: str,
    apptainer: str,
    sif: str,
    wrap_log_dir: str,
    dry_run: bool,
) -> str:
    """Build the ONE bash script run on the node via ``ssh -J``. Pure.

    The script is self-contained: it re-stages the launcher onto the shared FS
    (idempotent — covers a fresh node after a re-book where the staged copy may
    be absent), then loops over ``<ci_root>/actions-runner-*`` deciding liveness
    by each runner's own ``Runner.Listener`` argv and relaunching the dead ones
    with the EXACT ``setsid nohup bash launcher`` detach the single-repo path
    uses. It prints tagged, tab-separated lines that :func:`parse_fleet_output`
    turns into a :class:`FleetResult`.

    ``GH_TOKEN`` is assigned once at the top from the heredoc-injected value and
    exported only into the per-runner ``env`` line — it is never placed in a
    long-lived process argv that ``ps`` would show.
    """
    stage_dir = os.path.join(ci_root, "run")
    launcher_remote = os.path.join(stage_dir, "scitex_ci_launcher.sh")
    glob = os.path.join(ci_root, "actions-runner-*")
    dry = "1" if dry_run else "0"

    return f"""#!/bin/bash
set -u

DRY={dry}
CI_ROOT={shlex.quote(ci_root)}
STAGE_DIR={shlex.quote(stage_dir)}
LAUNCHER={shlex.quote(launcher_remote)}
WRAP_LOG_DIR={shlex.quote(wrap_log_dir)}
export FLEET_GH_TOKEN={shlex.quote(gh_token)}
export FLEET_APPTAINER={shlex.quote(apptainer)}
export FLEET_SIF={shlex.quote(sif)}

mkdir -p "$STAGE_DIR" "$WRAP_LOG_DIR" 2>/dev/null || true

# (Re)stage the shipped launcher onto the shared FS (idempotent).
cat > "$LAUNCHER" << 'SCITEX_FLEET_LAUNCHER_EOF'
{launcher_content}
SCITEX_FLEET_LAUNCHER_EOF
chmod +x "$LAUNCHER" 2>/dev/null || true

alive=0
restarted=0
would=0
failed=0

shopt -s nullglob
for d in {glob}; do
    [ -d "$d" ] || continue
    # Liveness by the runner's OWN argv: the listener runs as
    # "<dir>/bin/Runner.Listener run". pgrep -f matches the full cmdline, so this
    # never matches a peer runner sharing the node.
    if pgrep -u "$USER" -f "$d/bin/Runner.Listener" >/dev/null 2>&1; then
        alive=$((alive+1))
        printf '{_TAG_ALIVE}\\t%s\\n' "$d"
        continue
    fi
    # Dead. A registered runner ('.runner' present) only needs RUNNER_HOME +
    # GH_TOKEN to restart (the launcher skips registration). Derive GH_REPO and
    # RUNNER_NAME from .runner so the launcher's env contract (+ its TERM/INT
    # deregister trap) is fully populated.
    if [ ! -f "$d/.runner" ]; then
        # Not a registered runner home (no creds) — fleet can't safely restart
        # it without a registration token; report and skip (the per-repo `up`
        # path is the place to register a brand-new runner).
        failed=$((failed+1))
        printf '{_TAG_FAILED}\\t%s\\tno-.runner\\n' "$d"
        continue
    fi
    if [ "$DRY" = "1" ]; then
        would=$((would+1))
        printf '{_TAG_WOULD}\\t%s\\n' "$d"
        continue
    fi
    repo=$(python3 -c 'import json,sys
try:
    d=json.load(open(sys.argv[1], encoding="utf-8-sig"))
    u=d.get("gitHubUrl","")
    print("/".join(u.rstrip("/").split("/")[-2:]) if u else "")
except Exception:
    print("")' "$d/.runner" 2>/dev/null)
    name=$(python3 -c 'import json,sys
try:
    d=json.load(open(sys.argv[1], encoding="utf-8-sig"))
    print(d.get("agentName",""))
except Exception:
    print("")' "$d/.runner" 2>/dev/null)
    wrap_log="$WRAP_LOG_DIR/$(basename "$d").wrap.log"
    if env \\
        GH_TOKEN="$FLEET_GH_TOKEN" \\
        GH_REPO="$repo" \\
        RUNNER_NAME="$name" \\
        RUNNER_LABELS="self-hosted" \\
        RUNNER_HOME="$d" \\
        APPTAINER="$FLEET_APPTAINER" \\
        SIF="$FLEET_SIF" \\
        RUNNER_VERSION="2.328.0" \\
        setsid nohup bash "$LAUNCHER" </dev/null >"$wrap_log" 2>&1 & disown; then
        restarted=$((restarted+1))
        printf '{_TAG_RESTARTED}\\t%s\\n' "$d"
    else
        failed=$((failed+1))
        printf '{_TAG_FAILED}\\t%s\\tlaunch-failed\\n' "$d"
    fi
done

printf '{_TAG_SUMMARY}\\talive=%d\\trestarted=%d\\twould_restart=%d\\tfailed=%d\\n' \\
    "$alive" "$restarted" "$would" "$failed"
"""


def parse_fleet_output(stdout: str) -> FleetResult:
    """Parse the tagged on-node output into a :class:`FleetResult`. Pure."""
    result = FleetResult()
    for line in (stdout or "").splitlines():
        parts = line.split("\t")
        tag = parts[0] if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        if tag == _TAG_ALIVE and arg:
            result.alive.append(arg)
        elif tag == _TAG_RESTARTED and arg:
            result.restarted.append(arg)
        elif tag == _TAG_WOULD and arg:
            result.would_restart.append(arg)
        elif tag == _TAG_FAILED and arg:
            result.failed.append(arg)
    return result


def _default_compute_exec(target: str, node: str) -> ComputeExec:
    """Return an exec that ssh -J's the script to the lease's compute node.

    Uses :func:`config.compute_ssh_cmd` (``ssh -J <login> <node>``) + ``bash
    -s`` over stdin — the identical SSH-vector-safe path ``ci runner up`` and
    the single-repo restart use, so a relaunched runner's ``setsid nohup``
    orphans to init and survives (unlike an ``srun`` job step, which SLURM
    reaps). One ssh per fleet pass; the on-node script touches ~70 dirs.
    """

    def _run(script: str) -> "subprocess.CompletedProcess[str]":
        cmd = config.compute_ssh_cmd(target, node)
        return subprocess.run(
            [*cmd, "bash -s"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )

    return _run


def run_fleet_ensure(
    cfg: dict,
    *,
    node: str,
    dry_run: bool = False,
    launcher_path: str | None = None,
    compute_exec: ComputeExec | None = None,
) -> FleetResult:
    """Execute one fleet pass via a SINGLE compute-node ssh. IO entry point.

    ``node`` is the lease's live compute node (resolved by ``ensure_lease``);
    the whole discover+restart loop runs there over one ``ssh -J`` session so a
    relaunched runner survives (see the module docstring on why NOT srun).

    The ``compute_exec`` seam lets tests drive the whole pass with a real fake
    (records the script + returns canned on-node output) — no mocks of our own
    code, mirroring the ``_ensure`` / ``_reservation`` test strategy. Production
    leaves it ``None`` and ssh's to ``node`` via :func:`_default_compute_exec`.
    """
    if not node:
        raise click.ClickException(
            "fleet pass needs the lease's compute node, but none is allocated "
            "yet (freshly booked / PENDING). The next cron tick runs the fleet "
            "sweep once SLURM schedules the lease."
        )

    ci_root = fleet_ci_root(cfg)
    gh_token = config.get_gh_token(cfg)
    apptainer = cfg["hpc"]["apptainer"]
    sif = cfg["hpc"]["sif"]
    wrap_log_dir = os.path.dirname(cfg["runner"]["wrap_log"].rstrip("/")) or ci_root

    launcher = launcher_path or _shipped_launcher_path()
    with open(launcher, "r") as fh:
        launcher_content = fh.read()

    script = build_fleet_script(
        ci_root=ci_root,
        launcher_content=launcher_content,
        gh_token=gh_token,
        apptainer=apptainer,
        sif=sif,
        wrap_log_dir=wrap_log_dir,
        dry_run=dry_run,
    )

    target = config._ssh_target(cfg)
    run = compute_exec or _default_compute_exec(target, node)
    r = run(script)
    if r.returncode != 0:
        raise click.ClickException(
            f"fleet pass (ssh to lease node {node}) failed "
            f"(rc={r.returncode}): {(r.stderr or r.stdout).strip()}"
        )
    return parse_fleet_output(r.stdout or "")


# EOF
