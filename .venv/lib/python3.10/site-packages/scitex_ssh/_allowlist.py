"""Per-host policy for gating sensitive features (currently: tunnels).

Config file resolution (first that exists wins):
  $SCITEX_SSH_CONFIG  ->  ~/.scitex/ssh/config.yaml

Schema:
  default:
    tunnels: deny           # default policy for unlisted hosts
  hosts:
    mba:    {tunnels: allow}
    nas:    {tunnels: allow}
    spartan: {tunnels: deny}

If no config file exists: default policy is `deny` (fail-closed).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

#: Default config location. Overridable per-call via the $SCITEX_SSH_CONFIG
#: environment variable (see `config_path()`), matching the precedence chain
#: advertised in the CLI `--help`.
CONFIG_PATH = Path.home() / ".scitex" / "ssh" / "config.yaml"


class PolicyError(RuntimeError):
    """Raised when an action is denied by the allowlist."""


def config_path() -> Path:
    """Resolve the active config path.

    `$SCITEX_SSH_CONFIG` takes precedence over the default
    `~/.scitex/ssh/config.yaml`. Resolved at call time so the environment
    can be set after import (and so tests can point at a tmp config).
    """
    env = os.environ.get("SCITEX_SSH_CONFIG")
    if env:
        return Path(env)
    return CONFIG_PATH


#: Module-level alias so functions whose keyword parameter is also named
#: ``config_path`` (the explicit-override seam) can still reach the
#: env-aware resolver without the parameter shadowing it.
_resolve_config_path = config_path


def is_allowed(
    host: str,
    feature: Literal["tunnels"],
    *,
    config_path: Path | None = None,
) -> bool:
    """Return True iff `host` is allowed to use `feature`.

    Parameters
    ----------
    config_path : Path, optional
        Override the config file location. Defaults to the path resolved
        by ``config_path()`` (``$SCITEX_SSH_CONFIG`` then
        ``~/.scitex/ssh/config.yaml``). Used by tests to point at a real
        config in ``tmp_path`` without patching module globals.
    """
    resolved = config_path if config_path is not None else _resolve_config_path()
    cfg = _load(resolved)
    if cfg is None:
        return False  # fail-closed when no config
    hosts = cfg.get("hosts") or {}
    host_cfg = hosts.get(host) or {}
    if feature in host_cfg:
        return host_cfg[feature] == "allow"
    default_cfg = cfg.get("default") or {}
    return default_cfg.get(feature) == "allow"


def require(
    host: str,
    feature: Literal["tunnels"],
    *,
    config_path: Path | None = None,
) -> None:
    if not is_allowed(host, feature, config_path=config_path):
        path_for_msg = (
            config_path if config_path is not None else _resolve_config_path()
        )
        raise PolicyError(
            f"feature {feature!r} is not allowed for host {host!r}. "
            f"Edit {path_for_msg} to add 'hosts.{host}.{feature}: allow' "
            f"if your environment permits it."
        )


def _load(config_path: Path) -> dict | None:
    if not config_path.exists():
        return None
    try:
        import yaml
    except ImportError:
        # yaml not installed — treat as no config
        return None
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


# EOF
