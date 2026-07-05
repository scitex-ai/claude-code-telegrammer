"""Load and validate the CI runner config (~/.scitex/dev/config/ci-runner.yaml).

Organized layout (operator directive 2026-06-16, "utilize a directory … organize
various configs"): the CI runner config lives under the ``config/`` subdir, and
it does NOT duplicate the HPC host coordinates — ``hpc.user`` / ``hpc.ssh_host``
are resolved from the sibling ``config.yaml``'s ``hosts:`` entry named by
``hpc.host_ref`` (default ``spartan``). A ci-runner.yaml may still set
``hpc.user`` / ``hpc.ssh_host`` explicitly to override the shared file.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

_DEV_DIR = Path.home() / ".scitex" / "dev"
# Preferred (organized) location first, then the legacy flat path (back-compat).
_CONFIG_CANDIDATES = (
    _DEV_DIR / "config" / "ci-runner.yaml",
    _DEV_DIR / "ci-runner.yaml",
)
_SHARED_CONFIG_YAML = _DEV_DIR / "config.yaml"

# SSH connection MULTIPLEXING for every runner-CLI ssh/scp call.
#
# Spartan's HPC admin flagged excessive login-node connections (2026-06-17:
# 440+ from home). The runner CLI used to force ControlMaster=no (a FRESH
# connection per call) to dodge a multi-login-node /tmp staging race — but that
# race was fixed by moving staging onto the shared FS (PR #208), so the override
# is now pure churn. Multiplex instead: one shared master per host, reused by
# every call, auto-closed 30s after the last use. Caps the runner at ~1
# login-node connection (admin asked for <~20). The dedicated ControlPath keeps
# this socket separate from the operator's interactive ssh sockets.
SSH_MUX_OPTS = [
    "-o",
    "ControlMaster=auto",
    "-o",
    "ControlPersist=30",
    "-o",
    "ControlPath=~/.ssh/.cm-scitex-ci-%C",
]
# Same opts as a single string, for the few shell=True ssh call sites.
SSH_MUX_OPTS_STR = " ".join(SSH_MUX_OPTS)

# SSH options for reaching the LEASE COMPUTE NODE directly (ProxyJump through a
# login node). The runner launch (``ci runner up``) uses this so the runner's
# run.sh / Runner.Listener live on the compute node while the ssh client EXITS
# immediately — leaving ZERO persistent login-node ``srun`` client per runner.
#
# Why this is the SSH-vector fix (2026-06-17 admin incident, ~20 srun/login-node
# ceiling): the old ``up`` ran ``setsid nohup srun --overlap`` ON a login node,
# and that ``srun`` CLIENT stayed alive for the runner's whole lifetime as a
# stdio tether — one persistent login-node srun per runner (~76 across the
# fleet). The runner's real work already executes on the compute node either
# way; only the tether differs. Launching via ``ssh -J <login> <compute-node>``
# puts run.sh on the node and lets the ssh exit at once → no tether, no srun.
#
# StrictHostKeyChecking=accept-new: compute nodes are ephemeral lease holders
# absent from known_hosts; accept-new trusts on first contact (recording the
# key) without the interactive prompt that BatchMode would otherwise turn into a
# hard failure. It does NOT silently accept a CHANGED key (that still fails
# loudly), so it is the safe non-interactive policy for first-contact nodes. A
# dedicated ControlPath keeps the inner-hop master apart from the login sockets.
SSH_COMPUTE_OPTS = [
    "-o",
    "ControlMaster=auto",
    "-o",
    "ControlPersist=30",
    "-o",
    "ControlPath=~/.ssh/.cm-scitex-ci-node-%C",
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=accept-new",
]


def compute_ssh_cmd(login_target: str, compute_node: str) -> list[str]:
    """ssh argv to reach ``compute_node`` via ProxyJump through ``login_target``.

    ``login_target`` is ``user@login-host`` (the lease's submitting host); the
    inner hop reuses that user as ``user@<compute_node>``. The caller appends the
    remote command. Pure (no I/O) so the launch wrapper is unit-testable.
    """
    user = login_target.split("@", 1)[0]
    return [
        "ssh",
        *SSH_COMPUTE_OPTS,
        "-J",
        login_target,
        f"{user}@{compute_node}",
    ]


def _resolve_config_path() -> Path:
    """Return the config path following the precedence contract.

    Precedence:
      $SCITEX_DEV_CONFIG
      → $XDG_CONFIG_HOME/scitex/dev/config/ci-runner.yaml
      → ~/.scitex/dev/config/ci-runner.yaml   (organized — preferred)
      → ~/.scitex/dev/ci-runner.yaml          (legacy flat — back-compat)
    """
    env = os.environ.get("SCITEX_DEV_CONFIG")
    if env:
        return Path(env)

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        candidate = Path(xdg) / "scitex" / "dev" / "config" / "ci-runner.yaml"
        if candidate.exists():
            return candidate

    for candidate in _CONFIG_CANDIDATES:
        if candidate.exists():
            return candidate
    # None exist — return the preferred path so the missing-config error names it.
    return _CONFIG_CANDIDATES[0]


def _resolve_hpc_from_shared(
    host_ref: str, *, shared_path: Path | None = None
) -> dict[str, str]:
    """Resolve ``{user, ssh_host}`` for ``host_ref`` from the shared config.yaml.

    Reuses the single source of truth for host coordinates (operator: "reuse
    config.yaml hosts.spartan + hpc") so ci-runner.yaml never duplicates them.
    Returns {} (silently) when config.yaml is absent or has no matching host —
    the caller's required-key validation then reports precisely what's missing.

    ``shared_path`` is the file-path seam (defaults to ~/.scitex/dev/config.yaml);
    tests pass a real tmp file rather than patching the module constant.
    """
    path = shared_path or _SHARED_CONFIG_YAML
    if not path.exists():
        return {}
    # Best-effort: any failure here (yaml missing/misconfigured, unreadable
    # file, malformed YAML) returns {} so the caller's required-key validation
    # reports the missing hpc.user/ssh_host loudly with the precise path.
    try:
        import yaml

        shared = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}
    for host in shared.get("hosts", []) or []:
        if isinstance(host, dict) and host.get("name") == host_ref:
            out: dict[str, str] = {}
            if host.get("user"):
                out["user"] = str(host["user"])
            if host.get("hostname"):
                out["ssh_host"] = str(host["hostname"])
            return out
    return {}


def load_runner_config(
    *, config_path: Path | None = None, shared_path: Path | None = None
) -> dict[str, Any]:
    """Load + validate the ci-runner config.

    Each required key MUST be present — no defaults.
    Raises SystemExit if required keys are missing.

    ``config_path`` / ``shared_path`` are file-path seams (default to the
    resolved ci-runner.yaml and ~/.scitex/dev/config.yaml); tests pass real
    tmp files rather than patching module state.
    """
    cfg_path = config_path or _resolve_config_path()
    if not cfg_path.exists():
        raise SystemExit(
            f"missing private config at {cfg_path}; "
            f"run: scitex-dev ci runner onboard … to get started, or create "
            f"~/.scitex/dev/config/ci-runner.yaml with your bindings"
        )

    try:
        import yaml
    except Exception:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")

    with cfg_path.open() as fh:
        cfg = yaml.safe_load(fh) or {}

    # Reuse the shared config.yaml for HPC host coordinates (operator: "reuse
    # config.yaml hosts.spartan + hpc"). ci-runner.yaml names the host via
    # hpc.host_ref (default "spartan"); user/ssh_host are filled in from the
    # shared file UNLESS ci-runner.yaml set them explicitly (explicit wins).
    hpc = cfg.get("hpc")
    if isinstance(hpc, dict):
        host_ref = hpc.get("host_ref", "spartan")
        shared_hpc = _resolve_hpc_from_shared(host_ref, shared_path=shared_path)
        for key, value in shared_hpc.items():
            hpc.setdefault(key, value)

    required = [
        ("hpc", "user"),
        ("hpc", "ssh_host"),
        ("hpc", "apptainer"),
        ("hpc", "sif"),
        ("runner", "name"),
        ("runner", "labels"),
        ("runner", "home"),
        ("runner", "wrap_log"),
        ("github", "pat_env"),
        ("github", "default_repo"),
        ("github", "variable_name"),
        ("watchdog", "poll_interval_sec"),
        ("watchdog", "offline_grace_min"),
        ("watchdog", "alert_via"),
    ]

    # Lease backend (operator: "regarding lease, use scitex-hpc"):
    #   * If a `reservation` block is present, the lease IS a scitex-hpc
    #     persistent reservation (book/refresh owns the 7-day-walltime
    #     auto-resubmit). Only `reservation.name` is mandatory; the booking
    #     params (partition/cpus/mem/time/account/qos) are optional pass-through
    #     to `scitex-hpc reservations book`, which has its own config fallback.
    #   * Otherwise the legacy ad-hoc `ci_lease` hold-job applies and its keys
    #     stay required, so pre-migration operator setups keep working.
    if isinstance(cfg.get("reservation"), dict):
        required.append(("reservation", "name"))
    else:
        required += [
            ("ci_lease", "jobname"),
            ("ci_lease", "sbatch_script"),
            ("ci_lease", "renew_threshold_min"),
        ]

    for path in required:
        node = cfg
        for k in path:
            if not isinstance(node, dict) or k not in node:
                raise SystemExit(f"missing config key: {'.'.join(path)} in {cfg_path}")
            node = node[k]

    return cfg


def _ssh_target(cfg: dict[str, Any]) -> str:
    """Return ``user@ssh_host`` from config."""
    return f"{cfg['hpc']['user']}@{cfg['hpc']['ssh_host']}"


def get_gh_token(cfg: dict[str, Any]) -> str:
    """Read the GitHub PAT from the env var named in config."""
    env_name = cfg["github"]["pat_env"]
    token = os.environ.get(env_name)
    if not token:
        raise SystemExit(
            f"environment variable {env_name!r} is not set. "
            f"Set it to a classic PAT with repo + workflow + "
            f"actions:variables:write scopes."
        )
    return token


def _gh_api(
    cfg: dict[str, Any], method: str, path: str, data: dict | None = None
) -> dict:
    """Call GitHub REST API via gh CLI. Returns parsed JSON."""
    token = get_gh_token(cfg)
    repo = cfg["github"]["default_repo"]
    url = f"https://api.github.com/repos/{repo}/{path.lstrip('/')}"

    cmd = ["gh", "api", url, "-X", method, "--jq", "."]
    if data is not None:
        # gh api -f key=value pairs
        for k, v in data.items():
            cmd.extend(["-f", f"{k}={v}"])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise SystemExit(f"gh api {method} {path} failed: {result.stderr.strip()}")

    import json

    try:
        return json.loads(result.stdout.strip()) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        raise SystemExit(f"gh api returned non-JSON: {result.stdout!r}")


def ssh_run(
    cfg: dict[str, Any], cmd: str, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    """Run a command via ssh on the HPC host."""
    target = _ssh_target(cfg)
    result = subprocess.run(
        ["ssh", *SSH_MUX_OPTS, target, cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result
