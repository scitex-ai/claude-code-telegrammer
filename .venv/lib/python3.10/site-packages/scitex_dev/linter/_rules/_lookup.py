"""Unified rule lookup across engine + plugins.

`lookup(rule_id)` returns the most authoritative `Rule` object for an id.
Resolution order:
1. plugin-loaded rules (entry-point group `scitex_dev.linter.plugins`
   and the legacy `scitex_linter.plugins`)
2. engine-defined rules (this package's `_rules/*.py`)

This indirection lets leaf packages own their rules without the engine
holding stale duplicates. Engine code that historically used
`rules.IO001` should switch to `lookup("STX-IO001")` so the rule object
comes from the leaf package's plugin when present.

The lookup is cached but can be invalidated with `reset()` (used by
tests that manipulate plugins at runtime).
"""

from __future__ import annotations

from typing import Optional

from ._base import Rule

_cache: dict | None = None


def _build_cache() -> dict:
    """Merge engine ALL_RULES with plugin rules. Plugin wins on id collision."""
    from . import ALL_RULES

    merged: dict = dict(ALL_RULES)
    try:
        from .._plugin_loader import load_plugins

        plugin_rules = load_plugins().get("rules", {})
    except Exception:
        plugin_rules = {}
    merged.update(plugin_rules)
    return merged


def lookup(rule_id: str) -> Optional[Rule]:
    """Return the `Rule` for *rule_id*, or None if not registered.

    The first call builds and caches the merged engine+plugin dict;
    subsequent calls are O(1) dict lookups.
    """
    global _cache
    if _cache is None:
        _cache = _build_cache()
    return _cache.get(rule_id)


def reset() -> None:
    """Drop the cache (next `lookup()` rebuilds). For tests."""
    global _cache
    _cache = None


# EOF
