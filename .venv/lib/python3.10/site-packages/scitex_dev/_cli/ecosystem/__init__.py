"""SciTeX-dev CLI: ecosystem command group.

`_registry` — `scitex-dev ecosystem` Click commands (versions, sync, audit-*).
`_audit_brand_cmd` — `audit-brand` subcommand (lives outside _registry.py
because that file is at its size cap).
`_bulk` — `bulk` subcommand (lives outside _registry.py for the same reason).

To keep both ``from .ecosystem import register_ecosystem_commands`` and the
direct ``from .ecosystem._registry import register_ecosystem_commands``
import paths in sync — both used inside scitex-dev — this module replaces
``_registry.register_ecosystem_commands`` with a wrapper that also wires
``audit-brand`` and ``bulk``.
"""

from . import _registry as _registry_mod
from ._audit_brand_cmd import register_audit_brand_command
from ._bulk import register_bulk_command

_register_core = _registry_mod.register_ecosystem_commands


def register_ecosystem_commands(main_group):
    """Wire all ecosystem subcommands onto *main_group* and return the group."""
    ecosystem_group = _register_core(main_group)
    register_audit_brand_command(ecosystem_group)
    register_bulk_command(ecosystem_group)
    return ecosystem_group


# Make the direct import path pick up the wrapped version too.
_registry_mod.register_ecosystem_commands = register_ecosystem_commands  # type: ignore[assignment]

__all__ = ["register_ecosystem_commands", "register_audit_brand_command"]
