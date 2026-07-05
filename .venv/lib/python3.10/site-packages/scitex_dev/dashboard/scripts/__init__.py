#!/usr/bin/env python3
# Timestamp: 2026-02-05
# File: scitex_dev/dashboard/scripts/__init__.py

"""Dashboard JavaScript modules aggregator."""

from .cards import get_cards_js
from .core import get_core_js
from .filters import get_filters_js
from .render import get_render_js
from .utils import get_utils_js


def get_javascript() -> str:
    """Return complete dashboard JavaScript by aggregating all modules."""
    return (
        get_core_js()
        + get_filters_js()
        + get_cards_js()
        + get_render_js()
        + get_utils_js()
        + "\nfetchVersions();\ntoggleAutoRefresh(30);\n"
    )


__all__ = ["get_javascript"]


# EOF
