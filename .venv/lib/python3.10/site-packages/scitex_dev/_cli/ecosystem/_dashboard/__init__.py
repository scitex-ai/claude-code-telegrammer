"""Ecosystem dashboard — TUI / GUI / export over a single state model.

`gather_ecosystem_state(verbosity)` is the source of truth. Three
surfaces consume it:

- ``dashboard start``  — live-refresh TUI (Rich) or GUI (Dash, deferred)
- ``dashboard list``   — one-shot snapshot table
- ``dashboard export`` — JSON / CSV / Markdown dump
"""

from ._state import PackageState, gather_ecosystem_state

__all__ = ["PackageState", "gather_ecosystem_state"]
