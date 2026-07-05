#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SciTeX-dev CLI package — entry point + reusable subcommand mixins.

Module map:
- `_root`        — top-level Click group `main` (the `scitex-dev` console script entry point)
- `_utils`       — `handle_result`, `run_as_cli`, `wrap_as_cli`, json/dry-run option helpers
- `_completion`  — shell tab-completion installer
- `_doctor`      — `scitex-dev doctor`
- `_stats`       — `scitex-dev ecosystem stats`
- `audit/`       — `_summary` (was _cli_audit), `_api`, `_project`, `_skills`
- `ecosystem/`   — `_registry` (was _cli_ecosystem)
- `quality/`     — `_check` (was _cli_quality), `_frontmatter`
- `skills/`      — `_manage` (was _cli_skills), `_tags`

The `main` callable is the `[project.scripts]` target — `scitex_dev._cli:main`
must remain importable.
"""

from __future__ import annotations

from ._root import main
from ._utils import (
    add_dry_run_argument,
    add_json_argument,
    dry_run_option,
    handle_result,
    json_option,
    run_as_cli,
    wrap_as_cli,
)

__all__ = [
    "add_dry_run_argument",
    "add_json_argument",
    "dry_run_option",
    "handle_result",
    "json_option",
    "main",
    "run_as_cli",
    "wrap_as_cli",
]
