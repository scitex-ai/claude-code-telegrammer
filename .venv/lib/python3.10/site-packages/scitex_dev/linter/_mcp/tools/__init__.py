"""MCP tool registration for scitex-linter."""


def register_all_tools(mcp) -> None:
    """Register all MCP tools with the server."""
    from .lint import register_lint_tools

    register_lint_tools(mcp)
    _register_skills_tools(mcp)


def _register_skills_tools(mcp) -> None:
    """Register skills MCP tools."""

    @mcp.tool()
    def linter_skills_list() -> dict:
        """Use when you need to see what detailed docs exist for scitex-linter (47 SciTeX convention rules across 7 categories: FM filenames, I imports, IO save/load, P plot, PA path, S style, ST structure)."""
        try:
            from scitex_dev.skills import list_skills

            result = list_skills(package="scitex-linter")
            return {"success": True, "skills": result.get("scitex-linter", [])}
        except ImportError:
            return {"success": False, "error": "scitex-dev not installed"}

    @mcp.tool()
    def linter_skills_get(name: str = None) -> dict:
        """Use when you need to read a specific scitex-linter skill page covering the 47 SciTeX convention rules across 7 categories (FM filenames, I imports, IO save/load, P plot, PA path, S style, ST structure)."""
        try:
            from scitex_dev.skills import get_skill

            content = get_skill(package="scitex-linter", name=name)
            if content:
                return {"success": True, "name": name, "content": content}
            return {"success": False, "error": f"Skill '{name}' not found"}
        except ImportError:
            return {"success": False, "error": "scitex-dev not installed"}
