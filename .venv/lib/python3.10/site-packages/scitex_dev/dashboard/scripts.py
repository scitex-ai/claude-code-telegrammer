#!/usr/bin/env python3
# Timestamp: 2026-02-05
# File: scitex_dev/dashboard/scripts.py

"""JavaScript for the dashboard.

This module re-exports get_javascript() from the modular scripts/ package.
The JavaScript has been split into:
- scripts/core.py: Fetch, cache, refresh functions
- scripts/filters.py: Filter rendering
- scripts/cards.py: Package card rendering with source badges
- scripts/render.py: Main data rendering
- scripts/utils.py: Export, copy, toggle utilities
"""

from .scripts import get_javascript

__all__ = ["get_javascript"]


# EOF
