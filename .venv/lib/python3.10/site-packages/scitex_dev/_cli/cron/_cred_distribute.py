#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``cred-distribute`` cron job — recurring Claude-credential push to peer hosts.

Subsumes the operator's ad-hoc host-side stop-gap
``~/.scitex/push-freshest-cred-to-spartan.sh`` (crontab marker
``# spartan-cred-push``) into a *managed* scitex-dev cron job. Per the
operator directive (TG 2026-06-11) the goal is single-source
governance: no scattered host-level crontabs, behaviour switched by
config alone, robust across host reboots.

What this job does
------------------
Every cron tick (default ``0 */2 * * *`` — every 2 hours, on the hour):

  1. Load ``~/.scitex/dev/cred-distribute.yaml`` — the operator-tunable
     list of target hosts (``hosts:``) and the credential selector
     (``account:`` — default ``auto``, meaning "latest non-expired").
  2. For each enabled host, shell out to:

         sac accounts distribute --to-host <host> --account <account>

     (the new built-in being added in proj-scitex-agent-container at
     the time this job is registered — see the coordination note
     below). The call is per-host so one bad host doesn't poison the
     rest of the sweep.
  3. Append one structured audit line per host to
     ``~/.scitex/dev/logs/cron-cred-distribute.log`` for greppable
     history.
  4. Return a :class:`CredDistributeResult` (attempted / succeeded /
     failed counts + per-host outcomes) so the ``exec`` dispatcher can
     decide its exit code without re-parsing logs.

Robustness contract
-------------------
This runs unattended from cron pushing live credentials. It must
never crash the cron loop:

  * **Missing config file → bootstrap + no-op.** If
    ``~/.scitex/dev/cred-distribute.yaml`` does not exist, the job
    writes a self-documenting template (``hosts: []``, default
    ``account: auto``) and exits 0. The operator drops their host list
    in afterwards; subsequent ticks pick it up automatically.
  * **Empty / commented-out host list → no-op.** ``hosts: []`` is the
    "disable everything" knob — every host can be removed without
    uninstalling the job. The audit log still records the tick so the
    operator can see the loop is alive.
  * **``sac`` binary missing → log + exit 0.** The
    proj-scitex-agent-container ``sac accounts distribute`` capability
    is being built alongside this job (operator directive
    2026-06-11). Until it ships, ``sac`` may not be on PATH or the
    ``accounts`` subcommand may not exist. We treat both as transient,
    log a one-line warning, and exit 0 so the cron loop stays green.
    Once the capability lands no scitex-dev change is required.
  * **Per-host failure isolated.** SSH error, host unreachable,
    auth-failure, sac timeout — each is captured in the per-host
    outcome and the loop continues to the next host. Aggregate exit
    code is non-zero ONLY when every attempted host failed (the
    operator wants to be paged on systemic outage, not a transient
    one-host hiccup).
  * **Config malformed → exit non-zero with diagnostic.** YAML parse
    errors and schema violations (``hosts`` not a list, etc.) surface
    as a structured error result. The cron schedule keeps ticking; the
    next tick re-reads the (presumably-fixed) file.

Coordination with proj-scitex-agent-container
---------------------------------------------
``sac accounts distribute`` is the new built-in agent-container is
adding to replace the per-host push script. The CLI shape this body
calls is the assumption frozen at registration time:

  sac accounts distribute --to-host <host> --account <account>

  - exit 0 = credential synced (or already up-to-date)
  - exit != 0 = transport / auth / freshness error; stderr carries
    the human-readable diagnostic

If the canonical shape changes, the operator can patch this module's
:func:`_build_sac_args` without touching the registry or the cron
line; the schedule is independent.

Schedule rationale
------------------
Every 2 hours (``0 */2 * * *``) — matches the operator's existing
spartan-cred-push cadence and is conservative for credentials that
turn over on a multi-hour window. Tunable in
``_jobs.JOB_REGISTRY['cred-distribute'].schedule``.

Seams
-----
``config_path`` (Path-or-None — None triggers the standard
``~/.scitex/dev/cred-distribute.yaml`` resolution) and ``sac_runner``
(a ``Callable[[list[str]], subprocess.CompletedProcess]``) are
keyword arguments so tests pass real fakes — no monkeypatching of
``subprocess`` or filesystem.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence


# Default location for the operator-tunable config. Honours
# ``$SCITEX_DIR`` so the file lives next to the other cron config /
# logs without per-host bespoke configuration.
_CONFIG_NAME = "cred-distribute.yaml"

# Default per-host distribute command timeout. Long enough for an
# rsync-over-ssh of the credential blob; short enough that a hung host
# doesn't stall the whole sweep.
_DEFAULT_SAC_TIMEOUT_S = 60.0

# Audit log basename — lives in the same ``~/.scitex/dev/logs/`` dir
# as the other cron jobs so a single ``ls`` shows the operator every
# managed-cron's history.
_LOG_BASENAME = "cron-cred-distribute.log"

# Bootstrap template written when the config file does not exist on
# first tick. Self-documenting so the operator can edit it without
# consulting the source.
_BOOTSTRAP_CONFIG = """\
# scitex-dev cron: cred-distribute
#
# Operator-tunable target list for the `cred-distribute` managed cron
# job. The job calls
#
#     sac accounts distribute --to-host <host> --account <account>
#
# once per enabled host, every 2 hours by default (see
# `scitex-dev cron list cred-distribute`). Edit this file to switch
# behaviour; no code redeploy or `scitex-dev cron install` re-run is
# required.
#
# - `hosts`: list of host aliases recognised by your ssh config. Empty
#   list disables the job (audit log still records the tick).
# - `account`: credential selector forwarded to `sac accounts
#   distribute --account ...`. `auto` = latest non-expired (default).

hosts: []
account: auto
"""


def _state_dir() -> Path:
    """Return the canonical scitex-dev local-state dir (``~/.scitex/dev``).

    Honours ``$SCITEX_DIR`` (the ecosystem-wide relocation lever) so
    the cred-distribute config + log live next to the other cron
    artifacts without per-host bespoke configuration.
    """
    base = os.environ.get("SCITEX_DIR") or os.path.join(
        os.path.expanduser("~"), ".scitex"
    )
    return Path(base) / "dev"


def _default_config_path() -> Path:
    """Return ``~/.scitex/dev/cred-distribute.yaml`` (env-relocatable)."""
    return _state_dir() / _CONFIG_NAME


def _default_log_path() -> Path:
    """Return ``~/.scitex/dev/logs/cron-cred-distribute.log``."""
    return _state_dir() / "logs" / _LOG_BASENAME


@dataclass(frozen=True)
class HostOutcome:
    """Per-host outcome of one ``cred-distribute`` sweep."""

    host: str
    account: str
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    # When the failure is "binary missing" rather than a real sac
    # transport error, this is set so the dispatcher can decide whether
    # to count the host as failed-attempted vs skipped-not-due. Empty
    # string for the success path.
    skipped_reason: str = ""


@dataclass(frozen=True)
class CredDistributeResult:
    """Aggregate outcome of one ``cred-distribute`` cron tick.

    ``error`` is set ONLY for config-level failures (file missing
    bootstrap path, YAML parse error, schema violation). Per-host
    failures are captured in ``outcomes`` and rolled up in
    ``failed`` / ``succeeded`` / ``skipped`` so the dispatcher exit
    code reflects systemic vs. transient failure.
    """

    config_path: str
    log_path: str
    hosts_configured: int
    outcomes: Sequence[HostOutcome] = field(default_factory=tuple)
    error: str | None = None

    @property
    def attempted(self) -> int:
        """Hosts the sweep actually shelled out for."""
        return sum(1 for o in self.outcomes if not o.skipped_reason)

    @property
    def succeeded(self) -> int:
        return sum(1 for o in self.outcomes if o.ok and not o.skipped_reason)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if not o.ok and not o.skipped_reason)

    @property
    def skipped(self) -> int:
        return sum(1 for o in self.outcomes if o.skipped_reason)

    @property
    def all_attempted_failed(self) -> bool:
        """True iff every attempted host failed.

        The dispatcher uses this to decide its exit code: non-zero only
        on systemic failure (every host down). A single host failure
        with others succeeding is logged but not paged — that's the
        regime the per-host loop is designed to absorb.
        """
        return self.attempted > 0 and self.failed == self.attempted


def _load_yaml(path: Path) -> object:
    """Load a YAML document. Local import so a missing parser only surfaces
    when the cron body actually runs (the registry + dispatch wiring
    tests don't import this module's body).
    """
    try:
        from ruamel.yaml import YAML

        return YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except ImportError:  # pragma: no cover — ruamel is in the umbrella
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8"))


def _bootstrap_config(path: Path) -> None:
    """Write the self-documenting default config at ``path``.

    Called when the file does not yet exist on first tick. The
    operator edits it in afterwards; subsequent ticks pick up changes
    without any cron-install ceremony.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_BOOTSTRAP_CONFIG, encoding="utf-8")


def _parse_config(doc: object) -> tuple[list[str], str]:
    """Validate the loaded YAML and return ``(hosts, account)``.

    Raises :class:`ValueError` on schema violation so the caller can
    surface a single-line diagnostic in the audit log without exposing
    YAML-internal exception classes.
    """
    if doc is None:
        # Empty / all-commented-out file → behave as if hosts: [].
        return [], "auto"
    if not isinstance(doc, Mapping):
        raise ValueError(
            f"cred-distribute config must be a YAML mapping, got "
            f"{type(doc).__name__}"
        )
    raw_hosts = doc.get("hosts", [])
    if raw_hosts is None:
        raw_hosts = []
    if not isinstance(raw_hosts, list):
        raise ValueError(
            f"`hosts:` must be a YAML list, got {type(raw_hosts).__name__}"
        )
    hosts: list[str] = []
    for entry in raw_hosts:
        if isinstance(entry, str):
            name = entry.strip()
            if name:
                hosts.append(name)
            continue
        if isinstance(entry, Mapping):
            # Allow per-host overrides in a future extension — for now
            # just pick up the `name:` / `host:` key and skip if
            # `enabled: false` is set.
            if entry.get("enabled") is False:
                continue
            name = entry.get("name") or entry.get("host")
            if isinstance(name, str) and name.strip():
                hosts.append(name.strip())
            continue
        raise ValueError(
            f"unsupported `hosts` entry: {entry!r} (expected str or mapping)"
        )
    account = doc.get("account") or "auto"
    if not isinstance(account, str):
        raise ValueError(
            f"`account:` must be a string, got {type(account).__name__}"
        )
    return hosts, account


def _build_sac_args(host: str, account: str) -> list[str]:
    """Return the ``sac`` argv for distributing the credential to ``host``.

    Centralised here so a CLI-shape change in
    proj-scitex-agent-container's ``sac accounts distribute`` only
    needs a one-line edit (and a one-line test update) rather than a
    grep across the cron package.
    """
    return ["accounts", "distribute", "--to-host", host, "--account", account]


def _default_sac_runner(
    args: list[str],
    *,
    timeout: float = _DEFAULT_SAC_TIMEOUT_S,
) -> subprocess.CompletedProcess:
    """Real ``sac`` invocation. Tests pass their own fake.

    Raises ``FileNotFoundError`` when the ``sac`` binary is not on
    PATH; :func:`run_once` catches that, emits a one-line warning, and
    treats the entire sweep as skipped (returns exit 0 so the cron
    loop stays alive while the agent-container team is still building
    the capability).
    """
    return subprocess.run(
        ["sac", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _distribute_one(
    host: str,
    account: str,
    *,
    sac_runner: Callable[..., subprocess.CompletedProcess],
) -> HostOutcome:
    """Shell out to ``sac`` for one host. Never raises — packs failures
    into the returned :class:`HostOutcome` so the loop above can
    aggregate without try/except clutter.
    """
    args = _build_sac_args(host, account)
    try:
        r = sac_runner(args)
    except FileNotFoundError:
        return HostOutcome(
            host=host,
            account=account,
            ok=False,
            returncode=-1,
            stdout="",
            stderr="`sac` binary not found on PATH",
            skipped_reason="sac-not-installed",
        )
    except subprocess.TimeoutExpired as exc:
        return HostOutcome(
            host=host,
            account=account,
            ok=False,
            returncode=-1,
            stdout="",
            stderr=f"sac call timed out after {exc.timeout}s",
        )
    except Exception as exc:  # stx-allow: fallback (reason: cron must not crash)
        return HostOutcome(
            host=host,
            account=account,
            ok=False,
            returncode=-1,
            stdout="",
            stderr=f"{exc.__class__.__name__}: {exc}",
        )
    stdout = r.stdout or ""
    stderr = r.stderr or ""
    # The capability may not yet exist on the target sac install. We
    # treat "unknown command" / "no such subcommand" stderr signatures
    # as a skip rather than a failure so the cron is green during the
    # rollout window. Once `sac accounts distribute` lands the path
    # falls through to the normal success/failure split.
    if r.returncode != 0 and _looks_like_subcommand_missing(stderr + stdout):
        return HostOutcome(
            host=host,
            account=account,
            ok=False,
            returncode=r.returncode,
            stdout=stdout,
            stderr=stderr,
            skipped_reason="sac-subcommand-missing",
        )
    return HostOutcome(
        host=host,
        account=account,
        ok=(r.returncode == 0),
        returncode=r.returncode,
        stdout=stdout,
        stderr=stderr,
    )


# Substrings that indicate the `sac accounts distribute` subcommand
# isn't implemented yet (rollout-window grace). Conservative — we only
# treat the call as skipped if the stderr matches one of these literal
# patterns; any other non-zero exit is a real failure.
_MISSING_SUBCOMMAND_PATTERNS: tuple[str, ...] = (
    "No such command 'accounts'",
    "No such command 'distribute'",
    "Error: No such command",
    "Unknown command: accounts",
    "Unknown command: distribute",
    "no such subcommand",
)


def _looks_like_subcommand_missing(combined: str) -> bool:
    """Return True if the combined stdout/stderr looks like an "sac doesn't
    know this subcommand yet" error. Used to keep the cron green during
    the proj-scitex-agent-container rollout window.
    """
    lowered = combined.lower()
    return any(p.lower() in lowered for p in _MISSING_SUBCOMMAND_PATTERNS)


def _append_audit_line(log_path: Path, line: str) -> None:
    """Append a single audit line to the cred-distribute log.

    Best-effort: a write failure must not prevent the sweep from
    having run. The shell wrapper in :func:`_jobs._cred_distribute_command`
    also redirects stdout/stderr to the same file, so even if this
    in-process write fails the operator still has the print() output.
    """
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")
    except OSError:  # stx-allow: fallback (reason: audit is best-effort)
        pass


def run_once(
    *,
    config_path: Path | None = None,
    log_path: Path | None = None,
    sac_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    which_runner: Callable[[str], str | None] | None = None,
    now: Callable[[], float] | None = None,
) -> CredDistributeResult:
    """Execute one ``cred-distribute`` sweep.

    Returns a :class:`CredDistributeResult` so the ``exec`` dispatcher
    can decide its exit code without re-parsing the audit log. Per-host
    failures are captured in ``outcomes``; only config-level failures
    set ``error``.

    ``which_runner`` is the seam over :func:`shutil.which` — tests pass
    a real fake (``lambda name: None`` for "sac missing",
    ``lambda name: "/fake/sac"`` for "sac present") instead of
    monkey-patching the stdlib. The default in production is
    :func:`shutil.which` itself.
    """
    cfg = (config_path or _default_config_path()).expanduser()
    log = (log_path or _default_log_path()).expanduser()
    runner = sac_runner or _default_sac_runner
    which = which_runner or shutil.which
    clock = now or (lambda: __import__("time").time())
    timestamp = datetime.fromtimestamp(clock(), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%MZ"
    )

    # --- config load (bootstrap if missing) ---
    if not cfg.exists():
        try:
            _bootstrap_config(cfg)
        except OSError as exc:
            msg = f"failed to bootstrap config at {cfg}: {exc}"
            print(f"[cred-distribute {timestamp}] ERROR: {msg}", file=sys.stderr)
            _append_audit_line(log, f"[cred-distribute {timestamp}] ERROR: {msg}")
            return CredDistributeResult(
                config_path=str(cfg),
                log_path=str(log),
                hosts_configured=0,
                error=msg,
            )
        line = (
            f"[cred-distribute {timestamp}] bootstrapped config at {cfg} "
            f"(empty `hosts:` list — operator to populate); nothing to do"
        )
        print(line)
        _append_audit_line(log, line)
        return CredDistributeResult(
            config_path=str(cfg), log_path=str(log), hosts_configured=0
        )

    try:
        doc = _load_yaml(cfg)
    except Exception as exc:  # noqa: BLE001 — surface any parser error
        msg = f"failed to load {cfg}: {exc.__class__.__name__}: {exc}"
        print(f"[cred-distribute {timestamp}] ERROR: {msg}", file=sys.stderr)
        _append_audit_line(log, f"[cred-distribute {timestamp}] ERROR: {msg}")
        return CredDistributeResult(
            config_path=str(cfg),
            log_path=str(log),
            hosts_configured=0,
            error=msg,
        )

    try:
        hosts, account = _parse_config(doc)
    except ValueError as exc:
        msg = f"config schema error in {cfg}: {exc}"
        print(f"[cred-distribute {timestamp}] ERROR: {msg}", file=sys.stderr)
        _append_audit_line(log, f"[cred-distribute {timestamp}] ERROR: {msg}")
        return CredDistributeResult(
            config_path=str(cfg),
            log_path=str(log),
            hosts_configured=0,
            error=msg,
        )

    # --- short-circuit: no hosts to push to ---
    if not hosts:
        line = (
            f"[cred-distribute {timestamp}] no hosts configured "
            f"(account={account}); skipping sweep"
        )
        print(line)
        _append_audit_line(log, line)
        return CredDistributeResult(
            config_path=str(cfg),
            log_path=str(log),
            hosts_configured=0,
        )

    # --- short-circuit: sac binary missing entirely ---
    if which("sac") is None:
        line = (
            f"[cred-distribute {timestamp}] `sac` binary not on PATH "
            f"(hosts={hosts!r}, account={account!r}); skipping sweep until "
            f"proj-scitex-agent-container ships the capability"
        )
        print(line)
        _append_audit_line(log, line)
        outcomes = tuple(
            HostOutcome(
                host=h,
                account=account,
                ok=False,
                returncode=-1,
                stdout="",
                stderr="sac binary not on PATH",
                skipped_reason="sac-not-installed",
            )
            for h in hosts
        )
        return CredDistributeResult(
            config_path=str(cfg),
            log_path=str(log),
            hosts_configured=len(hosts),
            outcomes=outcomes,
        )

    # --- per-host sweep ---
    outcomes: list[HostOutcome] = []
    for host in hosts:
        outcome = _distribute_one(host, account, sac_runner=runner)
        outcomes.append(outcome)
        tag = (
            "ok"
            if outcome.ok
            else f"SKIP[{outcome.skipped_reason}]"
            if outcome.skipped_reason
            else f"FAIL[rc={outcome.returncode}]"
        )
        line = (
            f"[cred-distribute {timestamp}] host={host} account={account} "
            f"{tag}"
        )
        if outcome.stderr and not outcome.ok:
            # Trim stderr to first line so a noisy traceback doesn't blow up the
            # log; the dispatcher still has the full string in outcome.stderr.
            first = outcome.stderr.splitlines()[0] if outcome.stderr else ""
            line += f" stderr={first!r}"
        print(line)
        _append_audit_line(log, line)

    return CredDistributeResult(
        config_path=str(cfg),
        log_path=str(log),
        hosts_configured=len(hosts),
        outcomes=tuple(outcomes),
    )


# EOF
