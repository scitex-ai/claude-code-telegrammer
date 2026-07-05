"""Public ecosystem-glue API — stable for other SciTeX packages.

Underscore-private modules under `scitex_dev._ecosystem.*` are
implementation; this module is the supported import path for code
in other packages (e.g. the `scitex` umbrella's MCP tools).
"""

from __future__ import annotations

from ._ecosystem._mcp._compat import get_tools_sync
from ._ecosystem._mcp._core import (
    docs_build,
    docs_get,
    docs_list,
    docs_search,
    register_docs_tools,
)
from ._ecosystem._mcp._utils import (
    async_wrap_as_mcp,
    result_to_mcp,
    run_as_mcp,
    wrap_as_mcp,
)
from ._ecosystem._skills.skills import (
    export_skills,
    get_skill,
    list_skills,
)
from ._ecosystem.click_helpers import CategorizedGroup, make_categorized_group

__all__ = [
    "CategorizedGroup",
    "async_wrap_as_mcp",
    "docs_build",
    "docs_get",
    "docs_list",
    "docs_search",
    "export_skills",
    "get_skill",
    "get_tools_sync",
    "list_skills",
    "make_categorized_group",
    "register_docs_tools",
    "result_to_mcp",
    "run_as_mcp",
    "wrap_as_mcp",
]
