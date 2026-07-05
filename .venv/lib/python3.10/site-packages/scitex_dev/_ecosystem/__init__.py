"""SciTeX ecosystem registry, dependency graph, and package-state utilities.

Module map:
- `_core`     — `ECOSYSTEM` registry + `get_all_packages` / `get_local_path`
- `_graph`    — pyproject dependency graph (discover, parse, mermaid/dot, cycles)
- `_packages` — multi-host package SHA collection + audit/sync helpers
"""

from __future__ import annotations

from ._core import ECOSYSTEM, get_all_packages, get_local_path, should_skip_audit

__all__ = [
    "ECOSYSTEM",
    "get_all_packages",
    "get_local_path",
    "should_skip_audit",
]
