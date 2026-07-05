#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem up`` — one-shot ecosystem reconciler.

PR-1 redesign (2026-06-14, operator policy via lead msg 0502252a): the
SciTeX fleet runs ~70 packages. Per-leaf ``--user`` units are
unmanageable, so ``scitex-dev`` is the SOLE management surface.
``systemctl --user list-units`` shows EXACTLY ONE entry —
``scitex-dev-ecosystem.service`` — and that unit's ``ExecStart`` is the
collective supervisor :func:`scitex_dev._supervisor.run_supervisor`,
which spawns every ``kind="service"`` JobSpec as a child process under
itself.

What this command does
----------------------
Per invocation:

  1. Discover every ``JobSpec`` via :func:`scitex_dev.jobs.discover_jobs`.
  2. Materialise / refresh the managed crontab block. The block carries
     BOTH ``kind="cron"`` jobs (verbatim 5-field expressions) AND
     ``kind="timer"`` jobs (translated to a 5-field cron expression in
     :mod:`._up_timer_lowering`).
  3. Write the supervisor unit (:data:`SUPERVISOR_UNIT_NAME`) to
     ``~/.config/systemd/user/``. Idempotent.
  4. With ``--yes``: ``systemctl --user daemon-reload`` +
     ``enable --now scitex-dev-ecosystem.service``. The supervisor
     process spawns the ~70 children itself — this command does NOT.

Dropped from the previous design (per PR-1 scope)
-------------------------------------------------

* No per-leaf ``.service`` / ``.timer`` writes.
* No ``scitex-dev-ecosystem-reconcile.service`` master oneshot — the
  supervisor IS the runtime. JobSpec changes propagate via
  ``systemctl --user reload scitex-dev-ecosystem.service`` →
  ``ExecReload=/bin/kill -HUP $MAINPID`` → supervisor SIGHUP handler.
* No ``--install-master-unit`` flag.

What this command does NOT do (intentionally)
----------------------------------------------

* It does NOT purge legacy per-leaf units left over from the prior
  design. That helper ships in PR-2 (``ecosystem systemd purge --yes``),
  is opt-in, invoked by the operator only after host-verifying the
  supervisor's children serve the board (8051) + the wake POSTs.
  Sequencing avoids a board-down window during the migration.

Robustness — see the legacy ``_up`` docstring in git history; the
fail-open contract is unchanged.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import click

from ....jobs import JobSpec, discover_jobs
from ._up_supervisor_unit import (
    SUPERVISOR_UNIT_NAME,
    build_supervisor_unit_text,
    write_supervisor_unit,
)
from ._up_timer_lowering import collect_cron_jobs


def _unit_dir() -> Path:
    """Resolve ``~/.config/systemd/user`` honouring ``$HOME`` (test seam)."""
    return Path.home() / ".config" / "systemd" / "user"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UpResult:
    """Aggregate outcome of one ``ecosystem up`` invocation.

    ``error`` is set for catastrophic discovery / write failures only.
    Per-unit outcomes (enable / start) are captured in fields so the
    dispatcher exit code reflects systemic vs transient failure.
    """

    cron_jobs_installed: int = 0
    timer_jobs_lowered_to_cron: int = 0
    supervisor_unit_written: bool = False
    supervisor_unit_enabled: bool = False
    systemctl_missing: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# Seams (test-fakable; production defaults shell out)
# ---------------------------------------------------------------------------


def _default_systemctl_runner(
    args: list[str], *, timeout: float = 30.0
) -> subprocess.CompletedProcess:
    """Real ``systemctl --user`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_cron_block(
    *,
    cron_jobs: list[JobSpec],
    yes: bool,
    echo: Callable[[str], None],
) -> int:
    """Materialise the managed crontab block. Returns total entries installed.

    Accepts the *merged* cron-native + timer-lowered list. Delegates
    to the existing ``_cron_block.upsert_block`` so there's one cron-
    write code path across ``ecosystem cron install`` and ``ecosystem
    up``.
    """
    from ....jobs import _cron_block as cb
    from ...cron import _crontab

    if not cron_jobs:
        echo(
            "cron: no cron-kind / timer-kind jobs discovered; managed block "
            "left untouched"
        )
        return 0

    if not yes:
        echo("cron: --yes required to write the crontab block; skipping")
        return 0

    try:
        current = _crontab.read_crontab()
        new = cb.upsert_block(current, cron_jobs)
        _crontab.write_crontab(new)
    except RuntimeError as exc:
        echo(f"cron: ERROR writing crontab: {exc}")
        return 0
    echo(f"cron: installed {len(cron_jobs)} entry(ies) into managed block")
    return len(cron_jobs)


def _systemctl(
    args: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess],
    echo: Callable[[str], None],
) -> bool:
    """Invoke systemctl --user; return True on rc=0. Failure-isolated."""
    try:
        r = runner(args)
    except FileNotFoundError:
        return False
    except Exception as exc:  # noqa: BLE001 — never crash the reconcile
        echo(f"systemctl: ERROR running {args}: {exc}")
        return False
    if r.returncode != 0:
        stderr = (r.stderr or "").strip().splitlines()
        first = stderr[0] if stderr else ""
        echo(f"systemctl {' '.join(args)}: rc={r.returncode} {first!r}")
        return False
    return True


def _enable_supervisor_unit(
    *,
    systemctl_runner: Callable[..., subprocess.CompletedProcess],
    echo: Callable[[str], None],
) -> bool:
    """Daemon-reload + enable --now the supervisor unit. Best-effort."""
    if shutil.which("systemctl") is None:
        echo("systemctl not on PATH; supervisor unit written but not enabled")
        return False
    _systemctl(["daemon-reload"], runner=systemctl_runner, echo=echo)
    return _systemctl(
        ["enable", "--now", SUPERVISOR_UNIT_NAME],
        runner=systemctl_runner,
        echo=echo,
    )


def _supports_extra_providers(discover_callable) -> bool:
    """Detect whether the discover callable accepts ``extra_providers=``.

    Production ``discover_jobs`` does; a simple test fake of the form
    ``def fake() -> list[JobSpec]`` does not. Reflecting once keeps
    the seam ergonomic — tests don't have to mimic the real signature.
    """
    import inspect

    try:
        sig = inspect.signature(discover_callable)
    except (TypeError, ValueError):
        return False
    return "extra_providers" in sig.parameters


# ---------------------------------------------------------------------------
# Top-level ``up`` body — every external touch goes through a kwarg seam.
# ---------------------------------------------------------------------------


def run_up(
    *,
    yes: bool = False,
    systemctl_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    unit_dir: Path | None = None,
    echo: Callable[[str], None] | None = None,
    discover: Callable[..., list[JobSpec]] = discover_jobs,
    which: Callable[[str], str | None] | None = None,
) -> UpResult:
    """Execute one full reconcile pass. Returns aggregate outcome.

    ``which`` is the executable-lookup seam (defaults to ``shutil.which``);
    tests pass a hand-rolled fake to exercise the systemctl-absent path
    without patching production internals.
    """
    runner = systemctl_runner or _default_systemctl_runner
    udir = unit_dir or _unit_dir()
    log = echo or (lambda s: click.echo(s))
    which_fn = which or shutil.which

    # Discover the JobSpec set across all providers. Service-kind jobs
    # are NOT installed here — they become children of the supervisor
    # when `systemctl --user start scitex-dev-ecosystem.service` brings
    # the supervisor up.
    jobs = (
        discover(extra_providers=None)
        if _supports_extra_providers(discover)
        else discover()
    )
    cron_merged, _cron_native_n, timer_lowered_n = collect_cron_jobs(jobs)

    cron_installed = _install_cron_block(cron_jobs=cron_merged, yes=yes, echo=log)

    supervisor_path = write_supervisor_unit(udir)
    log(f"supervisor: wrote {supervisor_path}")

    systemctl_missing = which_fn("systemctl") is None
    supervisor_enabled = False
    if yes:
        supervisor_enabled = _enable_supervisor_unit(systemctl_runner=runner, echo=log)

    return UpResult(
        cron_jobs_installed=cron_installed,
        timer_jobs_lowered_to_cron=timer_lowered_n,
        supervisor_unit_written=True,
        supervisor_unit_enabled=supervisor_enabled,
        systemctl_missing=systemctl_missing,
    )


# ---------------------------------------------------------------------------
# Click registration
# ---------------------------------------------------------------------------


def register(ecosystem):
    @ecosystem.command(
        "up",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem up\n"
            "      (Dry surface — writes the supervisor unit + reports\n"
            "       what would land in the crontab block. No systemctl\n"
            "       enable; no crontab write.)\n"
            "\n"
            "  $ scitex-dev ecosystem up --yes\n"
            "      (Write the supervisor unit, install the crontab block,\n"
            "       enable + start scitex-dev-ecosystem.service. The unit\n"
            "       runs `scitex-dev ecosystem run` — the collective\n"
            "       supervisor that spawns every kind=service JobSpec as\n"
            "       a child process. The ONLY systemd unit registered.)\n"
            "\n"
            "Per operator policy 2026-06-14: systemd shows EXACTLY one\n"
            "entry — scitex-dev-ecosystem.service — for the SciTeX fleet.\n"
            "Per-leaf .service / .timer writes are gone; service-kind\n"
            "JobSpecs lower to supervisor children, timer-kind lowers to\n"
            "cron lines in the managed crontab block.\n"
        ),
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help=(
            "Actually write the crontab block + run "
            "`systemctl --user enable --now scitex-dev-ecosystem.service`. "
            "Without --yes the command writes the unit file (idempotent) "
            "but does NOT touch the crontab or ask systemctl to do anything."
        ),
    )
    def ecosystem_up_cmd(yes: bool) -> None:
        """Reconcile the SciTeX ecosystem: install the supervisor unit + cron."""
        result = run_up(yes=yes)
        click.echo("")
        click.echo("=== ecosystem up summary ===")
        click.echo(f"  cron entries installed:       {result.cron_jobs_installed}")
        click.echo(
            f"  (of which timer-lowered):     {result.timer_jobs_lowered_to_cron}"
        )
        click.echo(f"  supervisor unit written:      {result.supervisor_unit_written}")
        click.echo(f"  supervisor unit enabled+now:  {result.supervisor_unit_enabled}")
        if result.systemctl_missing:
            click.echo(
                "  (systemctl missing — unit file written, not enabled; "
                "rerun on a real host)"
            )
        if result.error is not None:
            raise click.ClickException(result.error)


__all__ = [
    "SUPERVISOR_UNIT_NAME",
    "UpResult",
    "build_supervisor_unit_text",
    "register",
    "run_up",
]


# EOF
