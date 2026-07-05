"""Call-level rule lookup tables for the SciTeX checker.

`CALL_RULES`, `AXES_HINTS`, and `PRINT_RULE` are built **lazily** via
module-level `__getattr__` — first access triggers `lookup(rule_id)`
through the plugin loader, which is unsafe at import time because leaf
plugins (e.g. figrecipe) import from `scitex_dev.linter.checker` and
that would create an import cycle. By the time anything queries these
tables (during `lint_source`), both `checker.py` and `_rule_tables.py`
are fully loaded and the cycle is gone.

This indirection is what lets the engine drop its `_rules/_io.py`,
`_rules/_path.py`, etc.: `lookup()` falls through to plugin-shipped
rules with the same id, so removing engine duplicates is safe.
"""

from . import rules  # noqa: F401  (kept for legacy attribute access)

# Note: previously this module re-exported S001-S008 / I001-I007 as
# eager aliases (`S001 = rules.S001`). After the engine `_rules/_structure.py`
# and `_rules/_imports.py` files were deleted, those rules ship from the
# scitex umbrella plugin instead and the checker resolves them via
# `lookup("STX-XXX")` directly. The aliases are gone.

# Names that refer to the scitex package (skip linting on these)
STX_NAMES = frozenset(("stx", "scitex", "scitex_io"))

# Modules to skip for axes hints
AXES_SKIP = frozenset(
    (
        "stx",
        "scitex",
        "os",
        "sys",
        "Path",
        "math",
        "np",
        "numpy",
        "pd",
        "pandas",
    )
)


# Spec → (key, rule_id). The actual Rule object is resolved at first
# access via `lookup()`. Order is irrelevant because dict lookups are
# O(1).
_CALL_RULES_SPEC = (
    # IO rules
    (("np", "save"), "STX-IO001"),
    (("numpy", "save"), "STX-IO001"),
    (("np", "load"), "STX-IO002"),
    (("numpy", "load"), "STX-IO002"),
    (("pd", "read_csv"), "STX-IO003"),
    (("pandas", "read_csv"), "STX-IO003"),
    ((None, "to_csv"), "STX-IO004"),
    (("pickle", "dump"), "STX-IO005"),
    (("pickle", "dumps"), "STX-IO005"),
    (("json", "dump"), "STX-IO006"),
    ((None, "savefig"), "STX-IO007"),
    # Plot rules
    ((None, "show"), "STX-P004"),  # plt.show()
    # Stats rules — scipy.stats.X()
    (("stats", "ttest_ind"), "STX-ST001"),
    (("stats", "mannwhitneyu"), "STX-ST002"),
    (("stats", "pearsonr"), "STX-ST003"),
    (("stats", "f_oneway"), "STX-ST004"),
    (("stats", "wilcoxon"), "STX-ST005"),
    (("stats", "kruskal"), "STX-ST006"),
    # Path rules
    (("os", "makedirs"), "STX-PA-003"),
    (("os", "mkdir"), "STX-PA-003"),
    (("os", "chdir"), "STX-PA-004"),
)

_AXES_HINTS_SPEC = (
    ("plot", "STX-P001"),
    ("scatter", "STX-P002"),
    ("bar", "STX-P003"),
)


# One-time lazy caches. Reset via `_reset_caches()` in tests.
_CALL_RULES_CACHE: dict | None = None
_AXES_HINTS_CACHE: dict | None = None
_PRINT_RULE_CACHE = None


def _reset_caches() -> None:
    """Drop lazy caches (for tests that swap plugins at runtime)."""
    global _CALL_RULES_CACHE, _AXES_HINTS_CACHE, _PRINT_RULE_CACHE
    _CALL_RULES_CACHE = None
    _AXES_HINTS_CACHE = None
    _PRINT_RULE_CACHE = None


def _build_call_rules() -> dict:
    from ._rules import lookup

    return {key: lookup(rid) for key, rid in _CALL_RULES_SPEC if lookup(rid)}


def _build_axes_hints() -> dict:
    from ._rules import lookup

    return {fn: lookup(rid) for fn, rid in _AXES_HINTS_SPEC if lookup(rid)}


def __getattr__(name):
    """Lazy-resolve CALL_RULES / AXES_HINTS / PRINT_RULE.

    Module-level `__getattr__` (PEP 562) fires on missing attribute
    access. The first lookup triggers a plugin-loader call; subsequent
    lookups hit the cache.
    """
    global _CALL_RULES_CACHE, _AXES_HINTS_CACHE, _PRINT_RULE_CACHE
    if name == "CALL_RULES":
        if _CALL_RULES_CACHE is None:
            _CALL_RULES_CACHE = _build_call_rules()
        return _CALL_RULES_CACHE
    if name == "AXES_HINTS":
        if _AXES_HINTS_CACHE is None:
            _AXES_HINTS_CACHE = _build_axes_hints()
        return _AXES_HINTS_CACHE
    if name == "PRINT_RULE":
        if _PRINT_RULE_CACHE is None:
            from ._rules import lookup

            _PRINT_RULE_CACHE = lookup("STX-P005")
        return _PRINT_RULE_CACHE
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
