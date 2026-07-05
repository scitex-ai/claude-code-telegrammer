#!/usr/bin/env python3
# Timestamp: "2026-05-24"
# File: src/scitex_container/apptainer/_config.py
"""Reproducible-image build config.

The config file lives at ``<root>/config.yaml`` where ``<root>`` is the
output base directory (path-injection — scitex-container takes the base
dir as an argument so a consumer such as scitex-agent-container can point
it at its own root).

Standalone scitex-container defaults its root to ``~/.scitex/container/``,
so the default config path is ``~/.scitex/container/config.yaml``.

Schema (every key optional; defaults applied when absent)::

    images:
      retain: 10               # keep last N (sif+lock) pairs per layer
      require_verified: false  # true = hard-error when using an .unverified image

A project-scope override is honoured: if a ``config.yaml`` exists in the
project scope for the ``container`` package (``<project>/.scitex/container/
config.yaml``), it wins over the user-scope file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from scitex_container._compat import supports_return_as

logger = logging.getLogger(__name__)

# Defaults — the single source of truth for "unspecified" behaviour.
DEFAULT_RETAIN = 10
DEFAULT_REQUIRE_VERIFIED = False


@dataclass(frozen=True)
class ImageConfig:
    """Resolved reproducible-image config."""

    # Keep the last N (sif, lock) pairs per layer; older builds are pruned
    # (a build dir carrying a .keep marker is never pruned).
    retain: int = DEFAULT_RETAIN
    # When True, the use-time check errors (instead of warning) on an
    # .unverified image.
    require_verified: bool = DEFAULT_REQUIRE_VERIFIED


def default_config_path(root: str | Path | None = None) -> Path:
    """Return the config-file path for a given output ``root``.

    Parameters
    ----------
    root : str or Path, optional
        Output base directory. When *None*, resolves to the standalone
        scitex-container default ``~/.scitex/container/`` (via
        ``local_state.user_path``).

    Returns
    -------
    Path
        ``<root>/config.yaml``.
    """
    if root is not None:
        return Path(root) / "config.yaml"

    # Standalone default: ~/.scitex/container/config.yaml
    from scitex_config._ecosystem import local_state

    return local_state.user_path("container", "config.yaml")


def _project_override_path() -> Path | None:
    """Return the project-scope ``config.yaml`` for ``container`` if present."""
    from scitex_config._ecosystem import local_state

    scope = local_state.find_project_scope("container")
    if scope is None:
        return None
    candidate = scope / "config.yaml"
    return candidate if candidate.is_file() else None


def _coerce_image_config(images: object) -> ImageConfig:
    """Build an ``ImageConfig`` from a parsed ``images:`` mapping.

    Unknown keys are ignored; missing keys fall back to defaults. A
    malformed ``retain`` (non-int / negative) falls back to the default
    rather than crashing the build — a misconfigured retain must never
    take down the round-trip.
    """
    if not isinstance(images, dict):
        return ImageConfig()

    retain = images.get("retain", DEFAULT_RETAIN)
    try:
        retain = int(retain)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid images.retain=%r; using default %d", retain, DEFAULT_RETAIN
        )
        retain = DEFAULT_RETAIN
    if retain < 1:
        logger.warning("images.retain=%d < 1; using default %d", retain, DEFAULT_RETAIN)
        retain = DEFAULT_RETAIN

    require_verified = bool(images.get("require_verified", DEFAULT_REQUIRE_VERIFIED))

    return ImageConfig(retain=retain, require_verified=require_verified)


@supports_return_as
def load_config(root: str | Path | None = None) -> ImageConfig:
    """Load the reproducible-image config.

    Resolution order (highest priority first):

    1. Project-scope override (``<project>/.scitex/container/config.yaml``).
    2. The ``<root>/config.yaml`` file (user-scope by default).
    3. Built-in defaults.

    Always returns a valid ``ImageConfig`` — a missing or unreadable
    config falls back to defaults rather than raising, because the
    config is an optional tuning knob, not a build precondition.

    Parameters
    ----------
    root : str or Path, optional
        Output base directory. ``None`` → standalone default
        ``~/.scitex/container/``.

    Returns
    -------
    ImageConfig
        The resolved config.
    """
    path = _project_override_path() or default_config_path(root)

    if not path.is_file():
        return ImageConfig()

    try:
        from scitex_config import load_yaml

        data = load_yaml(path) or {}
    except Exception as exc:  # malformed yaml / missing pyyaml — fall back loudly
        logger.warning(
            "Failed to load image config from %s: %s; using defaults", path, exc
        )
        return ImageConfig()

    if not isinstance(data, dict):
        return ImageConfig()

    return _coerce_image_config(data.get("images"))


# EOF
