"""Lint MCP tools for scitex-linter."""

from typing import Optional


def register_lint_tools(mcp) -> None:
    """Register lint-related MCP tools."""

    @mcp.tool()
    def linter_check(
        path: str, severity: str = "info", category: Optional[str] = None
    ) -> dict:
        """Lint a Python file against 47+ SciTeX reproducible-research rules — raw `pd.read_csv` / `np.load` / `pickle` instead of `stx.io` (STX-IO), hardcoded `/home/...` paths (STX-P), `plt.show()` in scripts, missing axis labels (STX-PA), p-values without effect sizes (STX-S), missing `@stx.session` entrypoints (STX-ST), etc. Drop-in complement to `flake8` / `ruff` / `pylint` — not a replacement for general style but specifically covers scientific-reproducibility anti-patterns. Use whenever the user asks to "lint this file", "check scitex conventions", "find stx.io violations", "lint my script for reproducibility rules", or before committing scientific Python. Filter by `severity` (error / warning / info) or comma-separated `category`."""
        from ...checker import lint_file
        from ...config import load_config
        from ...formatter import to_json
        from ...rules import SEVERITY_ORDER

        config = load_config(path)
        issues = lint_file(path, config=config)
        min_sev = SEVERITY_ORDER.get(severity, 0)
        categories = set(category.split(",")) if category else None

        issues = [
            i
            for i in issues
            if SEVERITY_ORDER[i.rule.severity] >= min_sev
            and (categories is None or i.rule.category in categories)
        ]

        return to_json(issues, path)

    @mcp.tool()
    def linter_list_rules(
        category: Optional[str] = None, severity: Optional[str] = None
    ) -> dict:
        """Browse the catalog of every lint rule scitex-linter knows — 47 built-ins plus any rules contributed by plugin packages (scitex-io, scitex-stats, figrecipe, etc.) via `scitex_linter.plugins` entry points. Returns each rule's ID (e.g. `STX-IO001`), category, severity, message, and suggested fix. Use whenever the user asks "what rules are there?", "list linter rules", "show me all STX-IO rules", "what does STX-PA-002 mean?", "catalog errors by severity", or is learning the rule set. Filter by `category=` (imports,io,path,axes,stats,fm,structure,…) or `severity=` (error|warning|info)."""
        from ... import list_rules

        rules_list = list_rules()

        if category:
            cats = set(category.split(","))
            rules_list = [r for r in rules_list if r.category in cats]
        if severity:
            rules_list = [r for r in rules_list if r.severity == severity]

        return {
            "rules": [
                {
                    "id": r.id,
                    "severity": r.severity,
                    "category": r.category,
                    "message": r.message,
                    "suggestion": r.suggestion,
                }
                for r in rules_list
            ],
            "count": len(rules_list),
        }

    @mcp.tool()
    def linter_check_source(source: str, filepath: str = "<stdin>") -> dict:
        """Lint an in-memory Python source string (no file on disk) against the full SciTeX rule set — useful for LLM-generated code, notebook cells, REPL snippets, and CI hooks checking patches before write. Use whenever the user asks to "lint this code I just wrote", "check this snippet against scitex rules", "validate this function without saving it", "pre-commit lint this patch", or passes a string rather than a path. Optional `filepath=` labels the source in error messages."""
        from ...checker import lint_source
        from ...config import load_config
        from ...formatter import to_json

        config = load_config(filepath)
        issues = lint_source(source, filepath=filepath, config=config)
        return to_json(issues, filepath)
