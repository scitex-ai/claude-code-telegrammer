"""Thin adapter over the ``scitex-hpc reservations`` CLI.

scitex-hpc already solves persistent SLURM allocations across the 7-day
walltime limit (``reservations book --persistent`` installs a SIGUSR1
auto-resubmit trap; ``reservations refresh`` re-discovers the new ``job_id``
after a walltime re-key). The CI runner lease used to be an ad-hoc hold-job
submitted by ``ci runner up`` / ``renew`` inside scitex-dev — which meant
scitex-dev re-implemented lease renewal and inevitably hit the 7-day wall.

This module makes scitex-hpc the single source of truth for the CI lease:
``ci runner ensure`` (and ``up``) book/refresh a reservation through this
adapter instead of submitting their own hold-job.

We talk to scitex-hpc over its **CLI**, not its Python API, because:

  * scitex-hpc is not a declared dependency of scitex-dev and is not
    guaranteed importable in the runner's environment; the CLI (resolved
    from config, default ``scitex-hpc``) is the stable public contract.
  * It mirrors the existing ``_ci_watch.py`` pattern (``gh`` / ``sac`` via an
    injectable subprocess runner), so the same real-fake test strategy
    applies — no mocks of our own code.

Test seam: every public function takes an optional ``hpc_runner`` callable
``(args: list[str]) -> CompletedProcess``. Tests pass a real fake; production
leaves it ``None`` and :func:`_default_hpc_runner` shells out to the configured
``scitex-hpc`` binary.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Callable

HpcRunner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class ReservationState:
    """Parsed view of one ``scitex-hpc reservations`` lease.

    ``present`` is False when scitex-hpc reports no lease file for the name
    (``get`` exits 2). ``live`` is True only when squeue currently backs the
    lease with a RUNNING job on an allocated ``node`` — i.e. after a
    successful ``refresh`` the lease still has a ``job_id`` AND a ``node``.
    A persistent lease whose walltime gap has not yet been bridged by the
    auto-resubmit (or that truly died) comes back ``present=True, live=False``
    with an empty ``job_id`` — the signal for ``ensure`` to re-book.
    """

    present: bool
    live: bool
    job_id: str = ""
    node: str = ""

    @classmethod
    def absent(cls) -> "ReservationState":
        return cls(present=False, live=False)


def _default_hpc_runner_factory(cli: str) -> HpcRunner:
    """Return a runner that shells out to the configured ``scitex-hpc`` binary.

    ``cli`` is ``reservation.cli`` from config (default ``scitex-hpc``); the
    operator points it at an absolute path when the binary is not on the
    non-interactive ``PATH`` (e.g. ``/home/<user>/.venv/bin/scitex-hpc``).
    """

    def _run(args: list[str]) -> "subprocess.CompletedProcess[str]":
        return subprocess.run(
            [cli, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,  # book waits for SLURM allocation (poll-timeout default 300s)
        )

    return _run


def _reservations(*tail: str) -> list[str]:
    return ["reservations", *tail]


def _maybe_host(host: str | None) -> list[str]:
    return ["--host", host] if host else []


def _parse_state(stdout: str) -> ReservationState:
    """Parse a ``--json`` reservation blob into :class:`ReservationState`.

    A blob with a non-empty ``job_id`` AND ``node`` is ``live``. scitex-hpc's
    ``refresh`` clears both when squeue finds no live job, so an empty
    ``job_id`` means the lease is not currently backed by a running allocation.
    """
    try:
        data = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        return ReservationState(present=True, live=False)
    job_id = str(data.get("job_id") or "")
    node = str(data.get("node") or "")
    return ReservationState(
        present=True,
        live=bool(job_id and node),
        job_id=job_id,
        node=node,
    )


def get_state(
    name: str,
    *,
    host: str | None = None,
    cli: str = "scitex-hpc",
    hpc_runner: HpcRunner | None = None,
) -> ReservationState:
    """Return the lease state WITHOUT touching SLURM (``reservations get``).

    ``get`` reads only the local lease file. Exit 2 → no lease file →
    :meth:`ReservationState.absent`. This is the cheap first probe; callers
    follow up with :func:`refresh_state` to validate the lease against squeue.
    """
    run = hpc_runner or _default_hpc_runner_factory(cli)
    r = run(_reservations("get", name, *_maybe_host(host), "--json"))
    if r.returncode == 2:
        return ReservationState.absent()
    if r.returncode != 0:
        raise RuntimeError(
            f"`scitex-hpc reservations get {name}` failed "
            f"(rc={r.returncode}): {(r.stderr or r.stdout).strip()}"
        )
    return _parse_state(r.stdout or "")


def refresh_state(
    name: str,
    *,
    host: str | None = None,
    cli: str = "scitex-hpc",
    hpc_runner: HpcRunner | None = None,
) -> ReservationState:
    """Re-discover ``job_id``/``node`` via squeue (``reservations refresh``).

    This is the 7-day-walltime bridge: a persistent reservation resubmits
    itself shortly before walltime (SLURM SIGUSR1 → ``sbatch "$0"``), so the
    ``job_id`` changes. ``refresh`` re-discovers the new id by NAME and updates
    scitex-hpc's cached lease — exactly the "re-key after walltime" the task
    asks ``ensure`` to handle without scitex-dev re-implementing it.

    scitex-hpc's ``refresh`` exits 2 in TWO cases: the lease file is missing,
    or squeue found no live job. We disambiguate via the JSON: a missing lease
    prints ``(no reservation named ...)`` to stderr and emits no JSON, so
    parsing fails → treat as not-live-but-present is wrong there. The caller
    (:func:`ensure` path) always calls :func:`get_state` first to settle
    presence, so here exit 2 with no JSON simply means "not live".
    """
    run = hpc_runner or _default_hpc_runner_factory(cli)
    r = run(_reservations("refresh", name, *_maybe_host(host), "--json"))
    if r.returncode not in (0, 2):
        raise RuntimeError(
            f"`scitex-hpc reservations refresh {name}` failed "
            f"(rc={r.returncode}): {(r.stderr or r.stdout).strip()}"
        )
    # refresh --json prints the (possibly-cleared) blob on rc 0; on rc 2
    # (no live job) it may still print JSON with empty job_id, or only the
    # stderr notice. Parse whatever JSON we got; absence of a usable blob
    # means not-live.
    if not (r.stdout or "").strip():
        return ReservationState(present=True, live=False)
    return _parse_state(r.stdout or "")


def book(
    name: str,
    *,
    book_args: list[str],
    cli: str = "scitex-hpc",
    hpc_runner: HpcRunner | None = None,
) -> ReservationState:
    """Book a fresh persistent reservation (``reservations book``).

    ``book_args`` is the fully-assembled flag list AFTER the name (partition,
    cpus, mem, time, account, qos, ``--persistent``, ``--host``, ``--json`` …),
    built by :func:`build_book_args` from config so this function stays a thin
    transport. Returns the parsed state of the freshly-booked lease.
    """
    run = hpc_runner or _default_hpc_runner_factory(cli)
    r = run(_reservations("book", name, *book_args))
    if r.returncode != 0:
        raise RuntimeError(
            f"`scitex-hpc reservations book {name}` failed "
            f"(rc={r.returncode}): {(r.stderr or r.stdout).strip()}"
        )
    return _parse_state(r.stdout or "")


def cancel(
    name: str,
    *,
    host: str | None = None,
    cli: str = "scitex-hpc",
    hpc_runner: HpcRunner | None = None,
) -> None:
    """Cancel + clear a stale lease (``reservations cancel --missing-ok``).

    Used before re-booking when a lease FILE is present but the allocation is
    dead — scitex-hpc's ``book`` refuses to overwrite an existing lease, so a
    stale file must be cleared first.
    """
    run = hpc_runner or _default_hpc_runner_factory(cli)
    r = run(_reservations("cancel", name, *_maybe_host(host), "-y", "--missing-ok"))
    if r.returncode != 0:
        raise RuntimeError(
            f"`scitex-hpc reservations cancel {name}` failed "
            f"(rc={r.returncode}): {(r.stderr or r.stdout).strip()}"
        )


def build_book_args(reservation_cfg: dict, *, host: str | None) -> list[str]:
    """Assemble the ``reservations book`` flag list from the config block.

    Maps the ``reservation`` config section to scitex-hpc's ``book`` options.
    Always passes ``--persistent`` (the 7-day-walltime auto-resubmit is the
    whole point) and ``--json`` (so callers can parse the booked node), plus
    ``-y`` for non-interactive cron use. ``--host`` is included when known so
    scitex-hpc submits from the right cluster without relying on its own
    config fallback.
    """
    args: list[str] = []
    args += _maybe_host(host)
    mapping = [
        ("partition", "--partition"),
        ("cpus", "--cpus"),
        ("mem", "--mem"),
        ("time", "--time"),
        ("account", "--account"),
        ("qos", "--qos"),
        ("gpus", "--gpus"),
        ("nodelist", "--nodelist"),
    ]
    for key, flag in mapping:
        val = reservation_cfg.get(key)
        if val is not None and val != "":
            args += [flag, str(val)]
    args.append("--persistent")
    args += ["-y", "--json"]
    return args


# EOF
