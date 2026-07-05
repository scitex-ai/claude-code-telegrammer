"""Rule definitions for SciTeX linter — re-export + lazy lookup.

After the per-package migration, the engine defines only:

- `EH001`              — generic error-handling lint
- `I001-I007`          — import hygiene (cross-cutting)
- `S001-S008`          — structure / `@stx.session` (cross-cutting)

These are re-exported here for back-compat (`from scitex_dev.linter.rules
import I001`).

For rule ids that migrated to a leaf-package plugin (IO/PA/ST/P/FM/...)
`__getattr__` falls through to `_rules._lookup.lookup()` so existing
code paths like `rules.IO001` keep resolving — they get the plugin's
version transparently.
"""

from __future__ import annotations

__all__ = ["ALL_RULES", "Rule", "SEVERITY_ORDER"]

from ._rules import (  # noqa: F401
    ALL_RULES,
    EH001,
    HPC001,
    I001,
    I002,
    I003,
    I004,
    I005,
    I006,
    I007,
    NET001,
    NL001,
    NM001,
    NM002,
    NM003,
    Rule,
    S001,
    S002,
    S003,
    S004,
    S005,
    S006,
    S007,
    S008,
    S009,
    S010,
    SEVERITY_ORDER,
    TQ001,
    TQ002,
    TQ003,
    TQ004,
    TQ005,
    TQ006,
    TQ007,
)
from ._rules import lookup as _lookup

# PEP 562 — fall through to lookup() for any rule attribute the engine
# no longer defines. Plugin-shipped rules with the matching id get
# returned transparently; truly missing ids raise AttributeError so
# typos still surface.
_RULE_PREFIXES = ("S", "I", "IO", "PA", "ST", "EH", "P", "FM", "NL", "NM", "TQ")


def __getattr__(name: str):
    if any(name.startswith(p) and name[len(p) :].isdigit() for p in _RULE_PREFIXES):
        rule = _lookup(f"STX-{name}")
        # Plugin-shipped rules (FM via figrecipe, ST via scitex-stats, ...)
        # may be missing in lean linter envs. Return None so call sites
        # can skip via a `if rule is None` guard, instead of crashing.
        return rule
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
