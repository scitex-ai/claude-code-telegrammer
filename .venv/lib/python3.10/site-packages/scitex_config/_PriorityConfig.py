#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: "2025-12-09 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-code/src/scitex/config/PriorityConfig.py


"""
Priority-based configuration resolver.

Functionalities
---------------
- `PriorityConfig.resolve()` — precedence cascade `direct → config_dict → env → default`.
- `load_dotenv()` — load `.env` file(s) into `os.environ` (cwd / $HOME / walk-up modes).
- `get_scitex_dir()` — resolve `$SCITEX_DIR` (direct → env → `~/.scitex`).

IO
--
- Reads: process env, `.env` files (cwd, `$HOME`, walk-up parents), config dicts.
- Writes: `os.environ` (only keys not already set — process env wins).

Dependencies
------------
- stdlib only (`os`, `pathlib`, `typing`).

Based on priority-config by ywatanabe (https://github.com/ywatanabe1989/priority-config),
incorporated into scitex for self-contained configuration management. Config-dict
values (from YAML or passed dict) take priority over environment variables, following
the Scholar module's CascadeConfig pattern.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

from ._env_loader import parse_src_file


def _parse_dotenv_file(path: Path) -> bool:
    """Parse a single .env file and merge into os.environ.

    Line/value parsing (``export`` prefix, quote stripping, ``$VAR`` expansion)
    is delegated to :func:`scitex_config._env_loader.parse_src_file` so the
    ``.env`` and ``.src`` surfaces share one canonical parser.

    Existing env vars are preserved (not overridden) — process env wins
    over .env file contents.

    Returns
    -------
    bool
        True if the file was successfully read and parsed, False on error.
    """
    if not (path.exists() and path.is_file()):
        return False
    try:
        parsed = parse_src_file(path)
        for key, value in parsed.items():
            # Only set if not already in environment (env takes precedence)
            if key not in os.environ:
                os.environ[key] = value
        return True
    except Exception:
        return False


def load_dotenv(
    dotenv_path: Optional[str] = None,
    *,
    walk_up: bool = False,
    stop_at: Optional[Union[str, Path]] = None,
) -> bool:
    """Load environment variables from .env file(s).

    Default behavior (``walk_up=False``, backward compatible):
        Searches for .env file in the following order, loading the first match:
        1. Explicit ``dotenv_path`` if provided
        2. Current working directory (``cwd/.env``)
        3. User home directory (``$HOME/.env``)

    Parent-walking behavior (``walk_up=True``, opt-in):
        Walks parent directories starting from ``cwd``, looking for ``.env``
        at each level. Stops when reaching ``stop_at`` (or ``$HOME`` if not
        given) or the filesystem root. **All** ``.env`` files found are loaded,
        with the most-distant parent loaded first so that closer-to-cwd values
        take precedence (closer .env wins). An existing process env var is
        never overridden by any .env (process env > closest .env > ... > root .env).

        Note: ``walk_up=True`` is ignored if ``dotenv_path`` is explicitly given.

    Parameters
    ----------
    dotenv_path : str, optional
        Path to .env file. If None, searches default locations.
    walk_up : bool, optional
        If True (and ``dotenv_path`` not given), walk parent dirs from cwd.
        Default False for backward compatibility — new callers should pass True.
    stop_at : str or Path, optional
        Directory at which to stop the upward walk (inclusive — its ``.env``
        is considered). If None, stops at ``$HOME`` (or filesystem root if
        ``$HOME`` is not a parent of cwd). Only used when ``walk_up=True``.

    Returns
    -------
    bool
        True if at least one .env file was found and loaded, False otherwise.
    """
    if dotenv_path:
        path = Path(dotenv_path)
        if path.exists() and path.is_file():
            return _parse_dotenv_file(path)
        return False

    if not walk_up:
        # Legacy behavior: try cwd then $HOME, first hit wins.
        for path in (Path.cwd() / ".env", Path.home() / ".env"):
            if path.exists() and path.is_file():
                return _parse_dotenv_file(path)
        return False

    # walk_up=True: collect .env files from cwd up through parents.
    cwd = Path.cwd().resolve()
    home = Path.home().resolve()
    stop_dir = Path(stop_at).expanduser().resolve() if stop_at is not None else home

    collected: List[Path] = []
    current = cwd
    visited: set = set()
    while True:
        resolved = current.resolve()
        if resolved in visited:
            break
        visited.add(resolved)

        candidate = current / ".env"
        if candidate.exists() and candidate.is_file():
            collected.append(candidate)

        # Stop condition: reached the configured stop directory.
        if resolved == stop_dir:
            break

        parent = current.parent
        if parent == current:
            # Filesystem root reached.
            break
        current = parent

    if not collected:
        return False

    # `collected` is in cwd→root order (closest first). Load in that order:
    # `_parse_dotenv_file` skips keys already in os.environ, so the closest
    # .env wins for any shared key. Process env (set before this call) wins
    # over all .env files.
    loaded_any = False
    for path in collected:
        if _parse_dotenv_file(path):
            loaded_any = True
    return loaded_any


def get_scitex_dir(direct_val: Optional[str] = None) -> Path:
    """Get SCITEX_DIR with priority: direct → env → default.

    This is a convenience function for the most common use case.

    Parameters
    ----------
    direct_val : str, optional
        Direct value (highest precedence)

    Returns
    -------
    Path
        Resolved SCITEX_DIR path
    """
    # Try to load .env first (won't override existing env vars)
    load_dotenv()

    if direct_val is not None:
        return Path(direct_val).expanduser()

    env_val = os.getenv("SCITEX_DIR")
    if env_val:
        return Path(env_val).expanduser()

    return Path.home() / ".scitex"


class PriorityConfig:
    """Universal config resolver with precedence: direct → config_dict → env → default

    Config dict (from YAML or passed dict) takes priority over env variables.
    This follows the Scholar module's CascadeConfig pattern.

    Examples
    --------
    >>> from scitex_config import PriorityConfig
    >>> config = PriorityConfig(config_dict={"port": 3000}, env_prefix="SCITEX_")
    >>> port = config.resolve("port", None, default=8000, type=int)
    3000  # from config_dict (highest after direct)
    >>> # With env: SCITEX_PORT=5000 python script.py
    >>> port = config.resolve("port", None, default=8000, type=int)
    3000  # config_dict takes precedence over env
    >>> port = config.resolve("port", 9000, default=8000, type=int)
    9000  # direct value takes highest precedence
    """

    SENSITIVE_EXPRESSIONS = [
        "API",
        "PASSWORD",
        "SECRET",
        "TOKEN",
        "KEY",
        "PASS",
        "AUTH",
        "CREDENTIAL",
        "PRIVATE",
        "CERT",
    ]

    def __init__(
        self,
        config_dict: Optional[Dict[str, Any]] = None,
        env_prefix: str = "",
        auto_uppercase: bool = True,
    ):
        """Initialize PriorityConfig.

        Parameters
        ----------
        config_dict : dict, optional
            Dictionary with configuration values
        env_prefix : str
            Prefix for environment variables (e.g., "SCITEX_")
        auto_uppercase : bool
            Whether to uppercase keys for env lookup
        """
        self.config_dict = config_dict or {}
        self.env_prefix = env_prefix
        self.auto_uppercase = auto_uppercase
        self.resolution_log: List[Dict[str, Any]] = []

    def __repr__(self) -> str:
        return f"PriorityConfig(prefix='{self.env_prefix}', configs={len(self.config_dict)})"

    def get(self, key: str) -> Any:
        """Get value from config dict only."""
        return self.config_dict.get(key)

    def resolve(
        self,
        key: str,
        direct_val: Any = None,
        default: Any = None,
        type: Type = str,
        mask: Optional[bool] = None,
    ) -> Any:
        """Get value with precedence hierarchy.

        Precedence: direct → config_dict → env → default

        This follows the Scholar module's CascadeConfig pattern where
        config dict takes higher priority than environment variables.

        Parameters
        ----------
        key : str
            Configuration key to resolve
        direct_val : Any, optional
            Direct value (highest precedence)
        default : Any, optional
            Default value if not found elsewhere
        type : Type
            Type conversion (str, int, float, bool, list)
        mask : bool, optional
            Override automatic masking of sensitive values

        Returns
        -------
        Any
            Resolved configuration value
        """
        source = None
        final_value = None

        # Replace dots with underscores for env key (e.g., axes.width_mm -> AXES_WIDTH_MM)
        normalized_key = key.replace(".", "_")
        env_key = f"{self.env_prefix}{normalized_key.upper() if self.auto_uppercase else normalized_key}"
        env_val = os.getenv(env_key)

        # Priority: direct → config_dict → env → default
        if direct_val is not None:
            source = "direct"
            final_value = direct_val
        elif key in self.config_dict:
            source = "config_dict"
            final_value = self.config_dict[key]
        elif env_val:
            source = f"env:{env_key}"
            final_value = self._convert_type(env_val, type)
        else:
            source = "default"
            final_value = default

        if mask is False:
            should_mask = False
        else:
            should_mask = self._is_sensitive(key)

        display_value = self._mask_value(final_value) if should_mask else final_value

        self.resolution_log.append(
            {
                "key": key,
                "source": source,
                "value": display_value,
                "type": type.__name__,
            }
        )

        return final_value

    def print_resolutions(self) -> None:
        """Print how each config was resolved."""
        if not self.resolution_log:
            print("No configurations resolved yet")
            return

        print("Configuration Resolution Log:")
        print("-" * 50)
        for entry in self.resolution_log:
            print(f"{entry['key']:<20} = {entry['value']:<20} ({entry['source']})")

    def clear_log(self) -> None:
        """Clear resolution log."""
        self.resolution_log = []

    def _convert_type(self, value: str, type: Type) -> Any:
        """Convert string value to specified type."""
        if type == int:
            return int(value)
        elif type == float:
            return float(value)
        elif type == bool:
            return value.lower() in ("true", "1", "yes")
        elif type == list:
            return value.split(",")
        return value

    def _is_sensitive(self, key: str) -> bool:
        """Check if key contains sensitive expressions."""
        key_upper = key.upper()
        return any(expr in key_upper for expr in self.SENSITIVE_EXPRESSIONS)

    def _mask_value(self, value: Any) -> str:
        """Mask sensitive values for display."""
        if value is None:
            return None
        value_str = str(value)
        if len(value_str) <= 4:
            return "****"
        return value_str[:2] + "*" * (len(value_str) - 4) + value_str[-2:]


# EOF
