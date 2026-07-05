---
description: |
  [TOPIC] Interface Mcp Skills Integration
  [DETAILS] SciTeX MCP — every package exposes `<pkg>_skills_list` and `<pkg>_skills_get` via scitex_dev so agents can discover and read package skills.
tags: [scitex-general-interface-mcp-skills-integration]
---

# §5. Skills integration

Every SciTeX package's MCP server **must** expose two skill-discovery tools that delegate to `scitex_dev.skills`:

```python
# src/scitex_<pkg>/_mcp_server.py — reference implementation
@mcp.tool()
async def skills_list() -> dict:
    """List available skill pages for scitex-<pkg>."""
    from scitex_dev.skills import list_skills
    return list_skills(package="scitex-<pkg>")

@mcp.tool()
async def skills_get(name: str | None = None) -> dict:
    """Get skill page content."""
    from scitex_dev.skills import get_skill
    return get_skill(package="scitex-<pkg>", name=name)
```

Under Convention A namespace mount, these become `<pkg>_skills_list` and `<pkg>_skills_get`.

## Rules

- **Always present.** Even minimal packages ship these two — agents rely on them being predictable.
- **Delegate, don't reimplement.** Both call into `scitex_dev.skills`; no per-package logic.
- **Same JSON shape across packages.** `skills_list` returns `{"skills": [{"name": …, "description": …}, …]}`; `skills_get` returns `{"name": …, "content": …, "frontmatter": {…}}`.

## Why mandatory

An LLM agent encountering `scitex-<pkg>` for the first time should be able to:

1. Call `<pkg>_skills_list` to see what skill pages exist.
2. Call `<pkg>_skills_get(name="…")` to read the relevant one.
3. Apply the skill's guidance.

Without this pair, agents have to grep the source — slow, brittle, and inconsistent across packages.

## Reference

- `~/proj/scitex-audio` — cleanest implementation in the ecosystem.
- Lessons learned: `~/proj/scitex-audio/GITIGNORED/LESSONS.md`.
