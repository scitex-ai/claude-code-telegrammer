#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fallback docs generation from Python docstrings and signatures.

Used when neither pre-built _sphinx_html/ nor Sphinx source is available.
Generates a minimal JSON doc structure by introspecting the installed package.
"""

from __future__ import annotations

import importlib
import inspect
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def introspect_package(module_name: str) -> Optional[dict[str, Any]]:
    """Generate docs from a package's docstrings and public API.

    Args:
        module_name: Python import name (e.g. "scitex_writer").

    Returns:
        Dict with package docs, or None if module can't be imported.
    """
    try:
        mod = importlib.import_module(module_name)
    except ImportError:
        logger.debug("Cannot import %s for introspection", module_name)
        return None

    result = {
        "package": getattr(mod, "__name__", module_name),
        "version": getattr(mod, "__version__", None),
        "description": _get_module_doc(mod),
        "modules": {},
    }

    # Introspect public members
    all_names = getattr(mod, "__all__", None)
    if all_names is None:
        all_names = [n for n in dir(mod) if not n.startswith("_")]

    for name in sorted(all_names):
        try:
            obj = getattr(mod, name)
        except AttributeError:
            continue

        if inspect.ismodule(obj):
            result["modules"][name] = _introspect_module(obj)
        elif inspect.isclass(obj):
            result["modules"][name] = _introspect_class(obj)
        elif callable(obj):
            result["modules"][name] = _introspect_callable(obj)

    return result


def _get_module_doc(mod: Any) -> str:
    """Get the first paragraph of a module's docstring."""
    doc = inspect.getdoc(mod)
    if not doc:
        return ""
    # Return first paragraph
    paragraphs = doc.split("\n\n")
    return paragraphs[0].strip()


def _introspect_module(mod: Any) -> dict[str, Any]:
    """Introspect a submodule."""
    return {
        "type": "module",
        "description": _get_module_doc(mod),
    }


def _introspect_class(cls: Any) -> dict[str, Any]:
    """Introspect a class — its docstring and public methods."""
    methods = {}
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith("_") and name != "__init__":
            continue
        methods[name] = _introspect_callable(method)

    return {
        "type": "class",
        "description": _get_module_doc(cls),
        "methods": methods,
    }


def _introspect_callable(obj: Any) -> dict[str, Any]:
    """Introspect a function or method."""
    try:
        sig = str(inspect.signature(obj))
    except (ValueError, TypeError):
        sig = "(...)"

    return {
        "type": "function",
        "signature": sig,
        "description": _get_module_doc(obj),
    }
