"""MCP server for scitex-linter."""

from fastmcp import FastMCP

from ._mcp.tools import register_all_tools

_INSTRUCTIONS = """\
SciTeX Linter: AST-based linter enforcing reproducible research patterns.

Tools:
- linter_check: Check a Python file
- linter_list_rules: List all lint rules
- linter_check_source: Lint source code string
"""

mcp = FastMCP(name="scitex-linter", instructions=_INSTRUCTIONS)

register_all_tools(mcp)


def run_server(transport: str = "stdio") -> None:
    """Run the MCP server."""
    mcp.run(transport=transport)
