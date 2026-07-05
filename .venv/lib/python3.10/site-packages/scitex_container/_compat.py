#!/usr/bin/env python3
"""Compatibility shim for optional scitex_dev dependency."""

try:
    from scitex_dev import supports_return_as
except ImportError:

    def supports_return_as(fn):
        """No-op fallback when scitex_dev is not installed."""
        return fn
