"""Register the ``scitex-dev ci runner`` click group."""

from __future__ import annotations

import click


def register(ci_group: click.Group) -> click.Group:
    """Register ``scitex-dev ci runner`` on the given ci group."""

    @ci_group.group("runner", invoke_without_command=True)
    @click.pass_context
    def runner(ctx: click.Context) -> None:
        """Self-hosted GitHub Actions runner lifecycle.

        \b
        Verbs:
          status            — runner state + CI_RUNS_ON + xdist tuning
          use <target>      — flip CI_RUNS_ON (target: github|self-hosted)
          ensure            — SOLVER: keep lease + N runners alive (cron-safe)
          up                — start the persistent runner
          down              — deregister the runner + stop it
          renew             — renew the SLURM CI lease job
          register <repo>   — copy the ci.yml template into a repo
          preflight         — fail-loud CI-readiness gate (for pre-push)

        \b
        Example:
          $ scitex-dev ci runner status
          $ scitex-dev ci runner status --explain
          $ scitex-dev ci runner use self-hosted
          $ scitex-dev ci runner ensure          # idempotent; run from cron
          $ scitex-dev ci runner up
          $ scitex-dev ci runner down
          $ scitex-dev ci runner renew
          $ scitex-dev ci runner register ../figrecipe
          $ scitex-dev ci runner preflight
        """
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    from ._status import register as register_status
    from ._use import register as register_use
    from ._ensure import register as register_ensure
    from ._up import register as register_up
    from ._down import register as register_down
    from ._renew import register as register_renew
    from ._register import register as register_register
    from ._preflight import register as register_preflight

    register_status(runner)
    register_use(runner)
    register_ensure(runner)
    register_up(runner)
    register_down(runner)
    register_renew(runner)
    register_register(runner)
    register_preflight(runner)

    return runner


# EOF
