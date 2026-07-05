"""SciTeX-dev CLI: skills command group.

- `_manage` — `scitex-dev skills` Click commands (list/get/export/...)
- `_tags`   — tag-expansion helpers shared with `skills` and discovery
"""

from ._manage import register_skills_commands

__all__ = ["register_skills_commands"]
