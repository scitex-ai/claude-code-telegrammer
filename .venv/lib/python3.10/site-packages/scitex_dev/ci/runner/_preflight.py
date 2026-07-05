"""``scitex-dev ci runner preflight`` — fail-loud CI-readiness gate.

Intended for a git ``pre-push`` hook: BLOCK the push when the self-hosted
Spartan CI cannot run the resulting workflow, instead of letting the push
succeed and the run sit queued forever (or — worse — silently fall back to a
github-hosted runner). Operator directive 2026-06-16: "fail fast, fail loud,
no silent fallbacks" + "pre push might want to check if ci runner is online".

Two hard checks, both must pass:
  1. A RUNNING SLURM CI lease exists (a PENDING lease never allocates, so it
     does not count — operator: "never use pending machines").
  2. At least one runner carrying the required label is ``online`` (and not
     every matching runner is ``busy``, which would queue indefinitely on a
     single-executor host — surfaced as a warning, not a hard fail).

Exit non-zero on any failure so the calling hook aborts the push.
"""

from __future__ import annotations

import json

import click

from . import config
from ._status import _lease_label, _lease_status, _runner_status


def _required_label(cfg: dict) -> str:
    """The self-hosted label that selects the Spartan CI runner.

    The first label that is not one of GitHub's built-in runner labels —
    e.g. ``spartan-cpu`` out of ``[self-hosted, spartan-cpu]``.
    """
    builtins = {"self-hosted", "linux", "x64", "x86", "arm", "arm64"}
    for label in cfg["runner"]["labels"]:
        if str(label).lower() not in builtins:
            return str(label)
    # Degenerate config (only builtins) — fall back to the literal list head.
    return str(cfg["runner"]["labels"][0])


def register(group: click.Group) -> None:
    @group.command()
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Output the readiness report as structured JSON.",
    )
    def preflight(as_json: bool) -> None:
        """Fail-loud CI-readiness gate (for a git pre-push hook).

        \b
        Exits 0 only when BOTH are true:
          * a RUNNING SLURM CI lease exists (pending leases don't count), and
          * at least one runner with the required label is online.
        Otherwise exits non-zero so the pre-push hook aborts the push —
        no silent fallback to a github-hosted runner.

        \b
        Example:
          $ scitex-dev ci runner preflight
          $ scitex-dev ci runner preflight --json
          # in .git/hooks/pre-push:
          #   exec scitex-dev ci runner preflight
        """
        cfg = config.load_runner_config()
        label = _required_label(cfg)

        problems: list[str] = []

        # --- check 1: a RUNNING lease (pending never allocates) -------------
        lease = _lease_status(cfg)
        running_leases: list[dict] = []
        if lease.get("error"):
            problems.append(f"lease query failed: {lease['error']}")
        else:
            running_leases = [
                j for j in lease.get("jobs", []) if j["state"] == "RUNNING"
            ]
            pending = [j for j in lease.get("jobs", []) if j["state"] == "PENDING"]
            if not running_leases:
                hint = (
                    f" ({len(pending)} PENDING — pending leases never allocate; "
                    "do NOT wait on them)"
                    if pending
                    else ""
                )
                problems.append(f"no RUNNING CI lease for {_lease_label(cfg)}{hint}")

        # --- check 2: an online runner with the required label -------------
        rstat = _runner_status(cfg)
        online_matching: list[dict] = []
        if rstat.get("error"):
            problems.append(f"runner query failed: {rstat['error']}")
        else:
            runners = rstat.get("runners", [])
            matching = [r for r in runners if label in (r.get("labels") or [])]
            online_matching = [r for r in matching if r.get("status") == "online"]
            if not matching:
                problems.append(f"no runner registered with label {label!r}")
            elif not online_matching:
                problems.append(
                    f"runner(s) with label {label!r} all OFFLINE "
                    f"({', '.join(r.get('name', '?') for r in matching)})"
                )

        # busy-but-online is not a hard fail (the job just queues), but warn.
        all_busy = bool(online_matching) and all(r.get("busy") for r in online_matching)

        report = {
            "ok": not problems,
            "required_label": label,
            "running_leases": running_leases,
            "online_runners": [r.get("name") for r in online_matching],
            "all_busy": all_busy,
            "problems": problems,
        }

        if as_json:
            click.echo(json.dumps(report, indent=2, default=str))
        else:
            if problems:
                click.secho("CI preflight FAILED — push blocked:", fg="red", bold=True)
                for p in problems:
                    click.secho(f"  ✗ {p}", fg="red")
                click.echo(
                    "\nThe self-hosted Spartan CI is not ready; the run would queue\n"
                    "indefinitely. Bring it up:\n"
                    "  scitex-dev ci runner ensure  # book/refresh lease + restart runners\n"
                    "  scitex-dev ci runner up      # (re)start a single runner\n"
                    "  scitex-dev ci runner status  # inspect\n"
                    "Or push with --no-verify to bypass (the run will not execute)."
                )
            else:
                lease_ids = ", ".join(j["jobid"] for j in running_leases)
                runners = ", ".join(report["online_runners"])
                click.secho(
                    f"CI preflight OK — label={label} lease={lease_ids} runner={runners}",
                    fg="green",
                )
                if all_busy:
                    click.secho(
                        "  (note: all matching runners are BUSY — your run will queue)",
                        fg="yellow",
                    )

        if problems:
            raise SystemExit(1)


# EOF
