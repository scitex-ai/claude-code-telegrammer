"""Package-name helpers shared by the MCP auditor and its §6 parity split.

Extracted from `_mcp_audit.py` so both `_mcp_audit` and `_mcp_parity`
can use them without a circular import.
"""

from __future__ import annotations


def _import_name(package: str) -> str:
    """`scitex-cloud` → `scitex_cloud`."""
    return package.replace("-", "_")


def _short_name(package: str) -> str:
    """`scitex-cloud` → `cloud`; `scitex-cloud-mcp` → `cloud_mcp`; `scitex` → `scitex`.

    Always a valid Python identifier suffix (no hyphens), usable both as a
    tool-name prefix and as a bridge-file basename.
    """
    if package == "scitex":
        return "scitex"
    if package.startswith("scitex-"):
        return package[len("scitex-") :].replace("-", "_")
    return package.replace("-", "_")


__all__ = ["_import_name", "_short_name"]
