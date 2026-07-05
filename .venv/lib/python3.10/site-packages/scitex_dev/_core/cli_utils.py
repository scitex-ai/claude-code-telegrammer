#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backward-compat shim — re-exports from `scitex_dev._cli._utils`.

The CLI helpers moved to `scitex_dev._cli._utils` in 0.11.0. This shim
keeps `from scitex_dev.cli_utils import ...` working for downstream
packages until they migrate. Will be removed in 0.12.0.
"""

from __future__ import annotations

from .._cli._utils import (
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
    "run_as_cli",
    "wrap_as_cli",
]
