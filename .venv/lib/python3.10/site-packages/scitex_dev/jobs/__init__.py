#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical federated scheduled-job contract for the SciTeX ecosystem.

This module defines the single ``JobSpec`` dataclass that *every*
ecosystem package imports, and the ``discover_jobs()`` aggregator that
collects jobs from all packages via the ``scitex_dev.jobs`` entry-point
group.

The discovery mechanism mirrors the linter-plugin federation pattern
(see ``scitex_dev.linter._plugin_loader``): each provider registers an
entry point in the ``scitex_dev.jobs`` group that loads to a *callable*
returning ``list[JobSpec]``. A failing or absent provider is tolerated
with a logged warning so one broken package never wedges the whole
aggregation.

Kind taxonomy
-------------
Three explicit kinds, each using only the fields relevant to its
backing mechanism. ``JobSpec.validate()`` enforces this — invalid
combos (a ``service`` with a schedule, a ``cron`` without one, a
``timer`` with no cadence …) raise ``ValueError`` at construction
time rather than producing silently-broken units.

* ``kind="service"`` — long-running systemd ``--user`` Service.
  The 8051 scitex-todo dashboard, a long-poll listener, etc. Brought
  up at boot with ``OnBootSec``, kept alive via ``Restart=on-failure``
  (configurable). ``schedule`` MUST be empty; ``on_unit_active_sec``
  MUST be ``None`` (it's not a Timer).
* ``kind="timer"`` — periodic systemd ``--user`` Timer + oneshot
  Service. ``on_unit_active_sec`` carries the cadence
  (e.g. ``"4h"``); ``schedule`` is optional but, if set, can be a
  cron expression we derive a fallback ``OnUnitActiveSec`` from.
* ``kind="cron"`` — crontab line. ``schedule`` is a 5-field cron
  expression. The systemd-specific fields MUST be ``None``.

Contract for downstream packages
--------------------------------
1. ``pip``-install ``scitex-dev`` (for the ``JobSpec`` import only — no
   heavy runtime dependency).
2. Define a module-level callable returning ``list[JobSpec]``::

       from scitex_dev.jobs import JobSpec

       def provide_jobs() -> list[JobSpec]:
           return [
               # A long-running dashboard exposed on a fixed port —
               # systemd brings it up on boot and keeps it alive.
               JobSpec(
                   name="scitex-todo.dashboard",
                   kind="service",
                   schedule="",
                   command="scitex-todo serve --port 8051",
                   description="scitex-todo board on http://localhost:8051",
                   on_boot_sec="15s",
                   restart_policy="on-failure",
                   timeout_sec=30,
               ),
               # A periodic systemd timer — refresh OAuth tokens.
               JobSpec(
                   name="sac.accounts-refresh",
                   kind="timer",
                   schedule="0 */4 * * *",
                   command="sac accounts refresh --all",
                   description="Rotate stored OAuth access tokens.",
                   on_boot_sec="15min",
                   on_unit_active_sec="4h",
                   timeout_sec=120,
               ),
           ]

3. Register it in ``pyproject.toml``::

       [project.entry-points."scitex_dev.jobs"]
       my-package = "my_package._jobs_plugin:provide_jobs"

``scitex-dev ecosystem systemd`` / ``ecosystem cron`` / ``ecosystem up``
then surface the job automatically.

Naming
------
``JobSpec.name`` is the package-prefixed unique id, e.g.
``"sac.accounts-refresh"``. The prefix keeps names globally unique and
makes the owning package obvious in ``list`` output. scitex-dev's own
built-in jobs keep their historical bare slugs (``ci-watch``,
``quota-keepalive``) for backward compatibility with the existing
``scitex-dev cron`` CLI.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Callable

_logger = logging.getLogger(__name__)

#: Entry-point group downstream packages register their job providers in.
ENTRY_POINT_GROUP = "scitex_dev.jobs"

#: Valid ``JobSpec.kind`` values. See module docstring for semantics.
ALLOWED_KINDS: frozenset[str] = frozenset({"service", "timer", "cron"})

#: Valid ``JobSpec.restart_policy`` values. Used by ``kind="service"``
#: only; ignored (and required to be ``"no"``) by ``timer`` / ``cron``.
ALLOWED_RESTART_POLICIES: frozenset[str] = frozenset(
    {"no", "on-failure", "on-abnormal", "on-abort", "on-watchdog", "always"}
)


@dataclass(frozen=True)
class JobSpec:
    """One scheduled job, shared across the SciTeX ecosystem.

    Fields
    ------
    name
        Package-prefixed unique id, e.g. ``"sac.accounts-refresh"``.
    kind
        One of ``"service"``, ``"timer"``, ``"cron"``. See the module
        docstring for what each kind means and which fields apply.
    schedule
        For ``kind="cron"``: a 5-field cron expression. For
        ``kind="timer"``: optional, used only as a fallback to derive
        ``OnUnitActiveSec`` when ``on_unit_active_sec`` is omitted. For
        ``kind="service"``: MUST be the empty string (services aren't
        scheduled — they run continuously).
    command
        Shell command to execute. Required for every kind.
    description
        Human-readable summary shown in ``list`` output.
    on_boot_sec
        systemd timer ``OnBootSec`` (timer) or service start delay
        (service). Ignored for ``kind="cron"``. Format: systemd
        duration string (e.g. ``"15s"``, ``"15min"``, ``"4h"``).
    on_unit_active_sec
        systemd timer ``OnUnitActiveSec`` — required for
        ``kind="timer"`` unless ``schedule`` is set (then derived).
        MUST be ``None`` for ``service`` and ``cron`` kinds.
    timeout_sec
        Hard timeout in seconds; maps to systemd ``TimeoutStartSec``.
        Applies to ``service`` (start) and ``timer`` (oneshot exec)
        kinds. ``None`` means systemd's default.
    restart_policy
        systemd ``Restart=`` value for ``kind="service"`` only —
        controls automatic restart on exit/failure. Defaults to
        ``"no"`` (no restart). MUST stay ``"no"`` for ``timer`` and
        ``cron`` kinds.
    watchdog_sec
        systemd ``WatchdogSec`` for ``kind="service"`` only — the
        liveness-ping interval that guards against *hangs* (a crash is
        already covered by ``Restart=``; a hang is not). Defaults to
        ``None`` (no watchdog).

        CRITICAL CAVEAT — opt-in on purpose. ``WatchdogSec`` does
        NOTHING unless the daemon periodically calls
        ``sd_notify(WATCHDOG=1)`` under ``Type=notify``. A plain
        ``Type=simple`` daemon that never pings would be *killed and
        restarted every ``WatchdogSec`` seconds* by systemd — a
        footgun. So a JobSpec must EXPLICITLY set ``watchdog_sec`` to
        request it; when set, the unit builder emits ``Type=notify`` +
        ``WatchdogSec=<N>s`` and the LEAF is responsible for sending
        the pings. When unset, the unit stays ``Type=simple`` and
        relies on ``Restart=`` alone (crashes, not hangs). MUST be
        ``None`` for ``timer`` and ``cron`` kinds.
    """

    name: str
    kind: str
    schedule: str
    command: str
    description: str
    on_boot_sec: str | None = None
    on_unit_active_sec: str | None = None
    timeout_sec: int | None = None
    restart_policy: str = "no"
    watchdog_sec: int | None = None

    def __post_init__(self) -> None:
        # Run the validator at construction time so a malformed leaf
        # crashes EARLY — never let a silently-broken unit reach the
        # systemd installer (or worse, a running host).
        self.validate()

    # ----------------------------------------------------------------- #
    # Validation                                                        #
    # ----------------------------------------------------------------- #
    def validate(self) -> None:
        """Raise ``ValueError`` if the field combination is invalid.

        Called from ``__post_init__`` so a malformed leaf crashes at
        ``JobSpec(...)`` construction (NOT later in the systemd
        installer when a half-written unit hits the disk).

        The rule set is the documented kind-taxonomy above, flattened
        into explicit checks so the error messages name the precise
        broken invariant.
        """
        if not self.name:
            raise ValueError("JobSpec.name must be non-empty")
        if not self.command:
            raise ValueError(
                f"JobSpec({self.name!r}).command must be non-empty"
            )
        if self.kind not in ALLOWED_KINDS:
            raise ValueError(
                f"JobSpec({self.name!r}).kind={self.kind!r} not in "
                f"{sorted(ALLOWED_KINDS)}"
            )
        if self.restart_policy not in ALLOWED_RESTART_POLICIES:
            raise ValueError(
                f"JobSpec({self.name!r}).restart_policy="
                f"{self.restart_policy!r} not in "
                f"{sorted(ALLOWED_RESTART_POLICIES)}"
            )

        if self.kind == "service":
            self._validate_service()
        elif self.kind == "timer":
            self._validate_timer()
        elif self.kind == "cron":
            self._validate_cron()

    def _validate_service(self) -> None:
        # A service is a long-running unit. Schedules / timer fields
        # don't apply — surfacing them at install-time would be a
        # silent-misconfiguration trap.
        if self.schedule != "":
            raise ValueError(
                f"JobSpec({self.name!r}, kind='service').schedule must be "
                f"empty (services aren't scheduled — they run "
                f"continuously). Got: {self.schedule!r}"
            )
        if self.on_unit_active_sec is not None:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='service')."
                f"on_unit_active_sec must be None (Timer-only field; "
                f"services use Restart= for keepalive, not a timer). "
                f"Got: {self.on_unit_active_sec!r}"
            )
        if self.watchdog_sec is not None and self.watchdog_sec <= 0:
            # A non-positive interval is meaningless and, worse, would
            # produce a WatchdogSec=0s that systemd treats as "disabled"
            # while implying the leaf opted in — a confusing half-state.
            raise ValueError(
                f"JobSpec({self.name!r}, kind='service').watchdog_sec "
                f"must be a positive number of seconds when set. "
                f"Got: {self.watchdog_sec!r}"
            )

    def _validate_timer(self) -> None:
        # A systemd Timer needs SOMETHING to tell it when to fire.
        # Accept either an explicit on_unit_active_sec OR a cron-style
        # schedule we can derive from. Rejecting both is the early-
        # crash that catches "I forgot to set the cadence".
        if not self.on_unit_active_sec and not self.schedule:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='timer') needs either "
                f"on_unit_active_sec or a schedule (cron expr) to derive "
                f"the cadence from — both are empty."
            )
        if self.restart_policy != "no":
            raise ValueError(
                f"JobSpec({self.name!r}, kind='timer').restart_policy "
                f"must be 'no' (timers fire oneshot services; Restart= "
                f"doesn't apply). Got: {self.restart_policy!r}"
            )
        if self.watchdog_sec is not None:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='timer').watchdog_sec "
                f"must be None (WatchdogSec guards long-running services, "
                f"not oneshot timer bodies). Got: {self.watchdog_sec!r}"
            )

    def _validate_cron(self) -> None:
        # Cron lines are inert text in the user's crontab. The systemd
        # fields would be meaningless; insist they're None so a
        # mis-set field flags up as a clear bug rather than silently
        # being dropped.
        if not self.schedule:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron').schedule must be a "
                f"5-field cron expression (got empty)"
            )
        fields = self.schedule.split()
        if len(fields) != 5:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron').schedule must have "
                f"exactly 5 cron fields, got {len(fields)}: "
                f"{self.schedule!r}"
            )
        if self.on_boot_sec is not None:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron').on_boot_sec must "
                f"be None (cron has no boot concept). Got: "
                f"{self.on_boot_sec!r}"
            )
        if self.on_unit_active_sec is not None:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron')."
                f"on_unit_active_sec must be None (systemd-only field). "
                f"Got: {self.on_unit_active_sec!r}"
            )
        if self.restart_policy != "no":
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron').restart_policy "
                f"must be 'no' (cron has no restart concept). Got: "
                f"{self.restart_policy!r}"
            )
        if self.watchdog_sec is not None:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron').watchdog_sec "
                f"must be None (systemd-only field). Got: "
                f"{self.watchdog_sec!r}"
            )


def _iter_entry_points(group: str):
    """Yield entry points for ``group``, compatible with Python 3.9+."""
    from importlib.metadata import entry_points

    if sys.version_info >= (3, 10):
        return entry_points(group=group)
    eps = entry_points()
    return eps.get(group, [])


def _builtin_jobs() -> list[JobSpec]:
    """scitex-dev's own jobs, adapted from the legacy ``JOB_REGISTRY``.

    Registered through the same provider path as external packages so
    there is a single code path. The legacy ``cron`` CLI keeps its own
    ``JOB_REGISTRY`` for backward compatibility; this adapts those
    entries into the canonical ``JobSpec`` form (``kind="cron"``).
    """
    from scitex_dev._cli.cron._jobs import JOB_REGISTRY

    return [
        JobSpec(
            name=spec.name,
            kind="cron",
            schedule=spec.schedule,
            command=spec.command,
            description=spec.description,
        )
        for spec in JOB_REGISTRY.values()
    ]


def discover_jobs(
    *,
    extra_providers: list[Callable[[], list[JobSpec]]] | None = None,
) -> list[JobSpec]:
    """Aggregate every ``JobSpec`` across the ecosystem.

    Sources, in order:

    1. scitex-dev's built-in jobs (``_builtin_jobs``).
    2. Every callable registered under the ``scitex_dev.jobs``
       entry-point group.
    3. ``extra_providers`` — an injection seam for tests (mirrors the
       ``read_fn`` / ``write_fn`` seams in the cron crontab helpers) so
       a fake provider can be supplied without touching installed
       entry-points.

    A provider that raises (or whose entry point fails to load) is
    skipped with a logged warning — exactly like the linter plugin
    loader — so one broken package never wedges the aggregation.

    De-duplication: jobs are keyed by ``name``. On collision the
    *first* provider wins (built-ins are first, then entry-points in
    discovery order); the duplicate is dropped with a logged warning.
    This matches the linter loader's "later registration is ignored on
    id collision" behavior (provider-wins / first-wins).
    """
    providers: list[Callable[[], list[JobSpec]]] = [_builtin_jobs]

    for ep in _iter_entry_points(ENTRY_POINT_GROUP):
        providers.append(_make_ep_provider(ep))

    if extra_providers:
        providers.extend(extra_providers)

    by_name: dict[str, JobSpec] = {}
    for provider in providers:
        try:
            jobs = provider()
        except Exception:
            _logger.warning(
                "Failed to load jobs from provider %r", provider, exc_info=True
            )
            continue
        for job in jobs:
            if not isinstance(job, JobSpec):
                _logger.warning(
                    "Provider %r yielded a non-JobSpec object %r; skipping",
                    provider,
                    job,
                )
                continue
            if job.name in by_name:
                _logger.warning(
                    "Duplicate job name %r ignored (first provider wins)",
                    job.name,
                )
                continue
            by_name[job.name] = job

    return [by_name[name] for name in sorted(by_name)]


def _make_ep_provider(ep) -> Callable[[], list[JobSpec]]:
    """Wrap an entry point into a provider callable returning JobSpecs."""

    def _provider() -> list[JobSpec]:
        get_jobs = ep.load()
        result = get_jobs()
        return list(result)

    _provider.__name__ = f"entry_point:{getattr(ep, 'name', '?')}"
    return _provider


def jobs_of_kind(kind: str, **kwargs) -> list[JobSpec]:
    """Return discovered jobs whose ``kind`` matches ``kind``."""
    return [j for j in discover_jobs(**kwargs) if j.kind == kind]


__all__ = [
    "JobSpec",
    "ENTRY_POINT_GROUP",
    "ALLOWED_KINDS",
    "ALLOWED_RESTART_POLICIES",
    "discover_jobs",
    "jobs_of_kind",
]


# EOF
