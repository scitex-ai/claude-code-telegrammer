"""Branding-registry helper implementation.

Loads ``registry.yaml`` once (cached) and exposes the four public helpers
plus a small set of inspection utilities used by the auditor.

No fallbacks: unknown brand or unknown field raises ``KeyError``. Hiding
misses defeats the registry's purpose (see plan doc).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Optional, TypedDict

import yaml

_REGISTRY_PATH = Path(__file__).with_name("registry.yaml")


class Brand(TypedDict, total=False):
    pypi: str
    import_: str  # `import` is reserved; expose as import_
    umbrella_attr: str
    alias: str
    display: str
    method_prefix: str
    env_prefix: str
    umbrella_brand: str
    native_brand: str


def _normalise_entry(raw: dict) -> Brand:
    """YAML uses ``import:`` because that reads naturally; Python code wants
    ``import_`` to avoid the keyword clash. Translate at load time."""
    entry: Brand = {}
    for key, value in raw.items():
        if key == "import":
            entry["import_"] = value  # type: ignore[typeddict-unknown-key]
        else:
            entry[key] = value  # type: ignore[literal-required]
    return entry


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Brand]:
    text = _REGISTRY_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    brands_raw = data.get("brands", {})
    return {key: _normalise_entry(raw) for key, raw in brands_raw.items()}


# ── Public API ──────────────────────────────────────────────────────────────


def get_brand(brand_key: str) -> Brand:
    """Whole entry for one brand. Raises KeyError if unknown."""
    registry = _load_registry()
    if brand_key not in registry:
        raise KeyError(f"Unknown brand key: {brand_key!r}. Known: {sorted(registry)}")
    return registry[brand_key]


def get(brand_key: str, field: str) -> Any:
    """Look up a single field. No fallbacks — registry is authoritative."""
    entry = get_brand(brand_key)
    if field not in entry:
        raise KeyError(
            f"Brand {brand_key!r} has no field {field!r}. "
            f"Available fields: {sorted(entry)}"
        )
    return entry[field]  # type: ignore[literal-required]


def iter_brands() -> Iterator[tuple[str, Brand]]:
    """Iterate (brand_key, entry). For audit rules."""
    yield from _load_registry().items()


def _counterpart(brand_key: str) -> Optional[str]:
    """Return the paired brand key (umbrella ↔ native) if any."""
    entry = get_brand(brand_key)
    return entry.get("umbrella_brand") or entry.get("native_brand")


def translate(name: str, *, from_brand: str, to_brand: str) -> str:
    """Layer-5 only — swap one brand's method_prefix for the counterpart's.

    Raises ValueError if from_brand/to_brand are not declared as
    native/umbrella counterparts in the registry.

        >>> translate("fr_conf_mat", from_brand="figrecipe", to_brand="scitex-plt")
        'stx_conf_mat'
    """
    if _counterpart(from_brand) != to_brand:
        raise ValueError(
            f"{from_brand!r} and {to_brand!r} are not declared counterparts "
            f"in the branding registry."
        )
    src_prefix = get(from_brand, "method_prefix")
    dst_prefix = get(to_brand, "method_prefix")
    if not name.startswith(src_prefix):
        raise ValueError(
            f"Name {name!r} does not start with {from_brand!r}'s "
            f"method_prefix {src_prefix!r}."
        )
    return dst_prefix + name[len(src_prefix) :]


def register_method_aliases(cls, *, brand_key: str) -> None:
    """Walk ``dir(cls)`` and bind the counterpart-brand's prefix as aliases.

    For each method starting with ``<this brand>.method_prefix``, bind an
    attribute named with the counterpart's method_prefix that points at the
    same function. The alias gets ``__module__`` rebound to the counterpart's
    import path so ``help()`` on the umbrella side doesn't leak the native
    package name.

    No-op if the brand has no counterpart or no method_prefix.
    """
    entry = get_brand(brand_key)
    if "method_prefix" not in entry:
        return
    counterpart_key = _counterpart(brand_key)
    if counterpart_key is None:
        return
    src_prefix = entry["method_prefix"]
    counterpart = get_brand(counterpart_key)
    if "method_prefix" not in counterpart:
        return
    dst_prefix = counterpart["method_prefix"]
    # Pick a sensible __module__ for the alias methods:
    # umbrella side preferred (umbrella_attr), else import_ name.
    alias_module = (
        counterpart.get("umbrella_attr")
        or counterpart.get("import_")
        or counterpart_key
    )

    for attr_name in list(vars(cls)):
        if not attr_name.startswith(src_prefix):
            continue
        original = vars(cls)[attr_name]
        if not callable(original):
            continue
        alias_name = dst_prefix + attr_name[len(src_prefix) :]
        if alias_name == attr_name:
            continue
        # Refuse to shadow an existing real method on the class or its MRO
        # (e.g. matplotlib's own Axes ancestor has its own swarmplot etc.).
        # If the same method already exists with the alias name as a true
        # member (not inherited from object), surface the conflict.
        existing = getattr(cls, alias_name, None)
        if existing is not None and existing is not original:
            # Walk MRO to see if it's a real conflict (not just our own
            # idempotent re-registration).
            for base in cls.__mro__[1:]:
                if alias_name in vars(base):
                    raise RuntimeError(
                        f"register_method_aliases: alias {alias_name!r} "
                        f"would shadow {base.__name__}.{alias_name}. "
                        f"Add an explicit skip rule before continuing."
                    )
        setattr(cls, alias_name, original)
        # Rebrand __module__ on the alias side without touching the original.
        # Functions store __module__ on the function object itself, so we
        # have to wrap or copy. To stay byte-identical behaviour, we make a
        # thin wrapper sharing the same code object but with its own
        # __module__ / __qualname__.
        try:
            wrapper = _rebrand_module(original, alias_module, cls, alias_name)
            setattr(cls, alias_name, wrapper)
        except TypeError:
            # Builtins / C-level callables: just bind as-is.
            pass


def _rebrand_module(func, module_name: str, cls, alias_name: str):
    """Return a function identical in behaviour to *func* but with
    ``__module__`` set to *module_name* and ``__qualname__`` updated.

    Uses ``functools.wraps`` so help() picks up the original docstring/sig.
    """
    import functools

    @functools.wraps(func)
    def alias(*args, **kwargs):
        return func(*args, **kwargs)

    alias.__module__ = module_name
    alias.__qualname__ = f"{cls.__name__}.{alias_name}"
    alias.__name__ = alias_name
    return alias


def get_env(
    key: str, *, brand_key: str, default: Optional[str] = None
) -> Optional[str]:
    """Read an environment variable using the brand's declared env_prefix,
    with a fallback to the counterpart brand's prefix (for white-label
    rebrands), then the unprefixed name, then *default*.

    Lookup order:
      1. ``<this brand env_prefix>_<key>``
      2. ``<counterpart env_prefix>_<key>`` (if a counterpart exists)
      3. ``<key>`` (unprefixed)
      4. ``default``
    """
    entry = get_brand(brand_key)
    primary_prefix = entry.get("env_prefix")

    tried = []
    if primary_prefix:
        var = f"{primary_prefix}_{key}"
        tried.append(var)
        value = os.environ.get(var)
        if value:
            return value

    counterpart_key = _counterpart(brand_key)
    if counterpart_key is not None:
        counterpart = _load_registry().get(counterpart_key, {})
        counterpart_prefix = counterpart.get("env_prefix")
        if counterpart_prefix and counterpart_prefix != primary_prefix:
            var = f"{counterpart_prefix}_{key}"
            tried.append(var)
            value = os.environ.get(var)
            if value:
                return value

    value = os.environ.get(key)
    if value:
        return value

    return default
