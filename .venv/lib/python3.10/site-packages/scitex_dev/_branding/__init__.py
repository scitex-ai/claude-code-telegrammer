"""Ecosystem branding / translation registry.

Single source of truth for SciTeX-ecosystem brand identities (pypi name,
import name, umbrella attr, alias, display, method-prefix, env-prefix).
See ``registry.yaml`` for entries and ``BRANDING_TRANSLATION_REGISTRY_PLAN.md``
for design rationale.

Runtime API (minimal — only what figrecipe + socialia need)::

    get(brand_key, field)               -> str
    translate(name, *, from_brand, to_brand) -> str
    register_method_aliases(cls, *, brand_key) -> None
    get_env(key, *, brand_key, default=None) -> str | None

Plus low-level helpers used by the auditor::

    get_brand(brand_key) -> Brand
    iter_brands() -> Iterator[tuple[str, Brand]]
"""

from __future__ import annotations

from ._helpers import (
    Brand,
    get,
    get_brand,
    get_env,
    iter_brands,
    register_method_aliases,
    translate,
)

__all__ = [
    "Brand",
    "get",
    "get_brand",
    "get_env",
    "iter_brands",
    "register_method_aliases",
    "translate",
]
