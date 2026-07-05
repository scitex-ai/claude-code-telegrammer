#!/usr/bin/env python3
# Timestamp: "2025-12-09 (ywatanabe)"
# File: ./src/scitex/config/__init__.py

"""scitex-config — configuration helpers (YAML + dotenv) — standalone.

Two distinct API surfaces:

**Public** (top-level ``scitex_config.*``) — convention-free generic
primitives usable by any Python project:

- ``PriorityConfig`` — direct → config_dict → env → default cascade
- ``ScitexConfig``, ``get_config``, ``load_yaml`` — YAML-based config
- ``ScitexPaths``, ``get_paths`` — centralized path manager
- ``load_dotenv``, ``get_scitex_dir`` — utilities
- ``parse_src_file``, ``load_env_from_path``, ``load_scitex_env`` — bash-style
  ``.src``/``.env`` parsing (canonical line/value parser; ``load_dotenv`` delegates)

**SciTeX-ecosystem internals** (``scitex_config._ecosystem.*``) — helpers
that embed SciTeX conventions (`pkg-short` naming, project-scope walk to
``.git/``, ``_skills/<pkg>/`` layout, ``SCITEX_<MODULE>_*`` env prefix).
For scitex-* package authors only; **not a stable public API**::

    from scitex_config._ecosystem import local_state, env_registry

**Priority Order** (same for ``PriorityConfig`` and ``ScitexConfig``):
   direct → config (YAML/dict) → env → default

Usage:
    from scitex_config import ScitexConfig, ScitexPaths, get_config, get_paths

    # YAML-based configuration (Scholar pattern)
    config = get_config()
    log_level = config.resolve("logging.level", default="INFO")

    # Centralized path manager
    paths = get_paths()
    print(paths.logs)      # ~/.scitex/logs
    print(paths.cache)     # ~/.scitex/cache

    # Use resolve() pattern in modules
    cache_dir = paths.resolve("cache", user_provided_path)
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("scitex-config")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

from ._env_loader import (
    load_env_from_path,
    load_scitex_env,
    parse_src_file,
)
from ._paths import ScitexPaths, get_paths
from ._PriorityConfig import PriorityConfig, get_scitex_dir, load_dotenv
from ._ScitexConfig import ScitexConfig, get_config, load_yaml

__all__ = [
    "__version__",
    # YAML-based config (Scholar pattern)
    "ScitexConfig",
    "get_config",
    "load_yaml",
    # Path management
    "ScitexPaths",
    "get_paths",
    # Generic primitives
    "PriorityConfig",
    "get_scitex_dir",
    "load_dotenv",
    # .src / .env parsing
    "parse_src_file",
    "load_env_from_path",
    "load_scitex_env",
]


# EOF
