#!/usr/bin/env python3
"""SciTeX SSH CLI - backward-compatible entry point."""

from scitex_ssh._cli import main  # noqa: F401

# EOF


# audit §4 — inject version into root --help
try:
    from importlib.metadata import version as _v
    main.help = (
        f"scitex-ssh (v{_v('scitex-ssh')}) — "
        + (main.help or "").lstrip()
    )
except Exception:
    pass

# audit-cli §1a — packages with _skills/ MUST expose
# `<cli> skills {list,get,install}`.
from ._skills import skills_group as _skills_group

main.add_command(_skills_group, name="skills")
