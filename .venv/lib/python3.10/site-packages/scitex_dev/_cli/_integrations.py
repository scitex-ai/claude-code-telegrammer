#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integration-command registration for the scitex-dev CLI.

Extracted from ``_root.py`` to keep that orchestrator under the per-file
line budget. Registers the cross-cutting integration groups on the main
click group:

* ``mcp``     — MCP server lifecycle.
* ``creds``   — credential distribution.
* ``cron``    — ecosystem-wide managed cron.
* ``hooks``   — git/agent hook management.
* ``service`` — keep a declared ``kind='service'`` daemon alive
                (systemd --user or respawn fallback).
"""

from __future__ import annotations

import click


def register_integration_commands(main: click.Group) -> None:
    """Register the integration command groups on ``main``."""
    from ._mcp_cmds import register_mcp_commands
    from .creds import register_creds_commands
    from .cron import register_cron_commands
    from ._hooks_cli import register_hooks_commands
    from .service import register_service_commands

    register_mcp_commands(main)
    register_creds_commands(main)
    register_cron_commands(main)
    register_hooks_commands(main)
    register_service_commands(main)


__all__ = ["register_integration_commands"]


# EOF
