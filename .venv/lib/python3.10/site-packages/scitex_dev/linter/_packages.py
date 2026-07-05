"""Detect available packages for conditional rule gating."""

_cache = None


def _can_import(name):
    """Check if a package is importable."""
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def detect():
    """Detect available packages. Cached after first call.

    Returns dict with keys: "scitex", "figrecipe".
    "figrecipe" is True if either figrecipe or scitex.plt is importable.
    """
    global _cache
    if _cache is not None:
        return _cache
    _cache = {
        "scitex": _can_import("scitex"),
        "figrecipe": _can_import("figrecipe") or _can_import("scitex.plt"),
    }
    return _cache


def reset():
    """Reset cache (for testing)."""
    global _cache
    _cache = None
