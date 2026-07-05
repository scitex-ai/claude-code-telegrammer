#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Category layout for `scitex-dev ecosystem --help`.

Section ordering for the categorised --help. Names below MUST match the
registered subcommand names; anything not listed falls into the built-in
"Other" section so nothing silently disappears.
"""

from __future__ import annotations

ECOSYSTEM_COMMAND_CATEGORIES = [
    (
        "Audit",
        [
            "audit-all",
            "audit-brand",
            "audit-cli",
            "audit-django",
            "audit-mcp-tools",
            "audit-project",
            "audit-python-apis",
            "audit-skills",
            "audit-summary",
            "list-audit-rules",
        ],
    ),
    (
        "Bulk",
        [
            "bulk",
        ],
    ),
    (
        "Discovery",
        [
            "list",
            "show-graph",
            "show-stats",
            "dashboard",
            "start-dashboard",
        ],
    ),
    (
        "Quality",
        [
            "check-versions",
            "install-audit-gate",
        ],
    ),
    (
        "Maintenance",
        [
            "clean-root",
            "init-config",
            "clone",
            "check-sync",
            "prune-merged",
            "ci-template",
        ],
    ),
    (
        "Scheduled jobs",
        [
            "cron",
            "systemd",
            "daemon",
            # `up` provisions the supervisor unit + crontab block;
            # `run` is the supervisor itself (systemd ExecStart);
            # `status` reads the supervisor's state snapshot.
            "up",
            "run",
            "status",
        ],
    ),
    (
        "Legacy (use `bulk` instead)",
        [
            "install",
            "sync",
            "pull",
            "checkout",
            "test-remote",
            "sync-remote",
        ],
    ),
]


__all__ = ["ECOSYSTEM_COMMAND_CATEGORIES"]
