"""scitex-dev's OWN FastMCP server.

The MCP helper utilities (`wrap_as_mcp`, `register_docs_tools`,
`get_tools_sync`, …) used to live here but are now ecosystem-glue
under `scitex_dev._ecosystem._mcp` and re-exported as the public
`scitex_dev.ecosystem` surface. This package retains only the
`_server` module that hosts scitex-dev's own MCP tools.
"""
