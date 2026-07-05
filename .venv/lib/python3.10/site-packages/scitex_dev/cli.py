#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backward-compat shim — re-exports from `scitex_dev._dispatch`.

The reusable docs/skills CLI mixins moved to `scitex_dev._dispatch`
in 0.11.0. This shim keeps `from scitex_dev.cli import ...` working for
downstream packages (figrecipe, scitex-io, scitex-app, etc.) until they
migrate. Will be removed in 0.12.0.
"""

from __future__ import annotations

from ._core.dispatch import (
    docs_click_group,
    register_docs_subcommand,
    register_skills_subcommand,
    skills_click_group,
)

__all__ = [
    "docs_click_group",
    "register_docs_subcommand",
    "register_skills_subcommand",
    "skills_click_group",
]
