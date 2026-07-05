#!/usr/bin/env python3
"""Introspection CLI commands for scitex-ssh."""

import click


@click.command("list-python-apis")
@click.option("-v", "--verbose", count=True, help="Verbosity (-v, -vv, -vvv).")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_python_apis(verbose, as_json):
    """List public Python API functions.

    \b
    Example:
      $ scitex-ssh list-python-apis
      $ scitex-ssh list-python-apis -vv
      $ scitex-ssh list-python-apis --json
    """
    import scitex_ssh

    apis = [
        ("setup", "Set up a persistent SSH reverse tunnel"),
        ("remove", "Remove a persistent SSH reverse tunnel"),
        ("status", "Check status of SSH reverse tunnels"),
        ("get_version", "Get scitex-ssh version"),
    ]

    constants = [
        ("AVAILABLE", "Whether scitex-ssh is available"),
        ("__version__", "Package version string"),
    ]

    if as_json:
        import json as _json

        click.echo(
            _json.dumps(
                {
                    "module": "scitex_ssh",
                    "apis": [{"name": n, "description": d} for n, d in apis],
                    "constants": [{"name": n, "description": d} for n, d in constants],
                },
                indent=2,
            )
        )
        return

    click.echo("scitex_ssh Python API:")
    click.echo()
    for name, desc in apis:
        if verbose >= 2:
            func = getattr(scitex_ssh, name, None)
            sig = ""
            if func and func.__doc__:
                sig = func.__doc__.strip().split("\n")[0]
            click.echo(f"  {name:20s} {sig}")
        elif verbose >= 1:
            click.echo(f"  {name:20s} {desc}")
        else:
            click.echo(f"  {name}")

    if verbose >= 1:
        click.echo()
        click.echo("Constants:")
        for name, desc in constants:
            click.echo(f"  {name:20s} {desc}")


# EOF
