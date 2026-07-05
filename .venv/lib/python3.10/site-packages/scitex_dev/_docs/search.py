#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified search across the SciTeX ecosystem.

Searches Python APIs, CLI commands, MCP tools, and documentation pages
across all installed scitex packages.

Query syntax (Google-like):
    search("save figure")           # match any term
    search('"save figure"')         # exact phrase match
    search("stats -deprecated")     # exclude results with "deprecated"
    search("+ttest statistics")     # "ttest" required, "statistics" optional boost

Usage:
    from scitex_dev import search

    search("save figure")                      # search everything
    search("ttest", scope="api")               # Python API only
    search("docs", scope="cli")                # CLI subcommands only
    search("stats -internal", scope="mcp")     # MCP tools, excluding "internal"
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from .._core.discovery import discover_packages, get_package_root

logger = logging.getLogger(__name__)

Scope = Literal["all", "api", "cli", "mcp", "docs"]

# Fuzzy match threshold (0.0–1.0). Lower = more permissive.
_FUZZY_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# Query parsing
# ---------------------------------------------------------------------------


@dataclass
class ParsedQuery:
    """Parsed search query with Google-like operators."""

    required: list[str] = field(default_factory=list)  # +term
    optional: list[str] = field(default_factory=list)  # plain term
    excluded: list[str] = field(default_factory=list)  # -term
    phrases: list[str] = field(default_factory=list)  # "exact phrase"

    @property
    def all_positive(self) -> list[str]:
        """All terms that should match (required + optional)."""
        return self.required + self.optional

    @property
    def is_empty(self) -> bool:
        return not (self.required or self.optional or self.phrases)


def parse_query(query: str) -> ParsedQuery:
    """Parse a Google-like query string.

    Supports:
        word         → optional term (boosts score)
        +word        → required term (must match)
        -word        → excluded term (must NOT match)
        "phrase"     → exact phrase match
    """
    parsed = ParsedQuery()

    # Extract quoted phrases first
    for match in re.finditer(r'"([^"]+)"', query):
        parsed.phrases.append(match.group(1).lower())

    # Remove quoted parts from remaining query
    remaining = re.sub(r'"[^"]*"', "", query).strip()

    for token in remaining.split():
        token_lower = token.lower()
        if token.startswith("+") and len(token) > 1:
            parsed.required.append(token_lower[1:])
        elif token.startswith("-") and len(token) > 1:
            parsed.excluded.append(token_lower[1:])
        else:
            parsed.optional.append(token_lower)

    return parsed


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_text(pq: ParsedQuery, text: str, fuzzy: bool = True) -> float:
    """Score text against a parsed query.

    Returns:
        Score >= 0. Returns -1 if excluded term found or required term missing.
    """
    text_lower = text.lower()

    # Check exclusions first
    for term in pq.excluded:
        if term in text_lower:
            return -1

    # Check required terms
    for term in pq.required:
        if not _term_matches(term, text_lower, fuzzy=fuzzy):
            return -1

    score = 0.0

    # Score required terms (they matched, give credit)
    for term in pq.required:
        score += 2.0  # Required terms get double weight

    # Score optional terms
    for term in pq.optional:
        if term in text_lower:
            score += 1.0
        elif fuzzy and _fuzzy_match(term, text_lower):
            score += 0.5  # Fuzzy matches get half weight

    # Score exact phrases
    for phrase in pq.phrases:
        if phrase in text_lower:
            score += 3.0  # Phrase matches get triple weight

    return score


def _term_matches(term: str, text: str, fuzzy: bool = True) -> bool:
    """Check if a term matches text (exact or fuzzy)."""
    if term in text:
        return True
    if fuzzy:
        return _fuzzy_match(term, text)
    return False


def _fuzzy_match(term: str, text: str) -> bool:
    """Check if term fuzzy-matches any word in text."""
    words = text.split()
    for word in words:
        # Strip non-alphanumeric for cleaner matching
        clean = re.sub(r"[^a-z0-9_]", "", word)
        if not clean:
            continue
        ratio = difflib.SequenceMatcher(None, term, clean).ratio()
        if ratio >= _FUZZY_THRESHOLD:
            return True
    return False


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------


def search(
    query: str,
    scope: Scope = "all",
    package: Optional[str] = None,
    packages: Optional[list[str]] = None,
    max_results: int = 10,
    fuzzy: bool = True,
) -> list[dict[str, Any]]:
    """Search across the SciTeX ecosystem.

    Query syntax:
        "save figure"     → match any term
        '"exact phrase"'  → match exact phrase
        "+required term"  → term must appear
        "-excluded"       → results with this term are removed

    Args:
        query: Search query (supports +required, -excluded, "phrases").
        scope: What to search — "all", "api", "cli", "mcp", or "docs".
        package: Limit to a single package.
        packages: Limit to specific packages.
        max_results: Maximum results to return.
        fuzzy: Enable fuzzy matching via difflib (default True).

    Returns:
        List of dicts with: package, name, title, score, scope, match_type.
        Sorted by relevance (score descending).
    """
    pq = parse_query(query)
    if pq.is_empty:
        return []

    # Determine target packages
    targets = _resolve_targets(package, packages)
    results = []

    # Dispatch to scope-specific searchers
    searchers = {
        "docs": _search_docs,
        "api": _search_api,
        "cli": _search_cli,
        "mcp": _search_mcp,
    }

    if scope == "all":
        for searcher in searchers.values():
            results.extend(searcher(pq, targets, fuzzy=fuzzy))
    elif scope in searchers:
        results.extend(searchers[scope](pq, targets, fuzzy=fuzzy))
    else:
        raise ValueError(
            f"Unknown scope: {scope!r}. Use 'all', 'api', 'cli', 'mcp', or 'docs'."
        )

    # Deduplicate by (package, name, scope)
    seen = set()
    unique = []
    for r in results:
        key = (r["package"], r["name"], r["scope"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    unique.sort(key=lambda r: (-r["score"], r["name"]))
    return unique[:max_results]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_targets(
    package: Optional[str],
    packages: Optional[list[str]],
) -> dict[str, Optional[str]]:
    """Resolve which packages to search."""
    if package is not None:
        discovered = discover_packages()
        return {package: discovered.get(package)}
    if packages is not None:
        discovered = discover_packages()
        return {p: discovered.get(p) for p in packages}
    return discover_packages()


def _make_result(
    package: str,
    name: str,
    title: str,
    score: float,
    scope: str,
    match_type: str,
) -> dict[str, Any]:
    return {
        "package": package,
        "name": name,
        "title": title,
        "score": score,
        "scope": scope,
        "match_type": match_type,
    }


# ---------------------------------------------------------------------------
# Scope-specific searchers
# ---------------------------------------------------------------------------


def _search_docs(
    pq: ParsedQuery,
    targets: dict[str, Optional[str]],
    fuzzy: bool = True,
) -> list[dict[str, Any]]:
    """Search documentation pages."""
    from .docs import get_docs

    results = []
    for pkg_name in targets:
        try:
            manifest = get_docs(package=pkg_name)
        except LookupError:
            continue
        if not isinstance(manifest, dict):
            continue

        for page_entry in manifest.get("pages", []):
            if isinstance(page_entry, dict):
                name = page_entry.get("name", "")
                title = page_entry.get("title", "")
            else:
                name = str(page_entry)
                title = name

            text = f"{name} {title}"
            s = score_text(pq, text, fuzzy=fuzzy)
            if s > 0:
                results.append(
                    _make_result(pkg_name, name, title, s, "docs", "page_title")
                )

        # Package description
        desc = manifest.get("description", "")
        if desc:
            s = score_text(pq, desc, fuzzy=fuzzy)
            if s > 0:
                results.append(
                    _make_result(pkg_name, pkg_name, desc[:80], s, "docs", "package")
                )

    return results


def _search_api(
    pq: ParsedQuery,
    targets: dict[str, Optional[str]],
    fuzzy: bool = True,
) -> list[dict[str, Any]]:
    """Search Python API (public functions, classes, methods)."""
    from .._core.introspect import introspect_package

    results = []
    for pkg_name, module_name in targets.items():
        if module_name is None:
            continue
        try:
            info = introspect_package(module_name)
        except Exception:
            continue
        if info is None:
            continue

        for member_name, member_info in info.get("modules", {}).items():
            text = f"{member_name} {member_info.get('description', '')}"
            sig = member_info.get("signature", "")
            if sig:
                text += f" {sig}"
            s = score_text(pq, text, fuzzy=fuzzy)
            if s > 0:
                results.append(
                    _make_result(
                        pkg_name,
                        member_name,
                        member_info.get("description", "")[:80],
                        s,
                        "api",
                        member_info.get("type", "function"),
                    )
                )

            # Search methods within classes
            if member_info.get("type") == "class":
                for method_name, method_info in member_info.get("methods", {}).items():
                    text = f"{member_name}.{method_name} {method_info.get('description', '')}"
                    s = score_text(pq, text, fuzzy=fuzzy)
                    if s > 0:
                        results.append(
                            _make_result(
                                pkg_name,
                                f"{member_name}.{method_name}",
                                method_info.get("description", "")[:80],
                                s,
                                "api",
                                "method",
                            )
                        )

    return results


def _search_cli(
    pq: ParsedQuery,
    targets: dict[str, Optional[str]],
    fuzzy: bool = True,
) -> list[dict[str, Any]]:
    """Search CLI subcommands via console_scripts entry points."""
    results = []
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="console_scripts")
        for ep in eps:
            pkg_match = None
            for pkg_name in targets:
                normalized = pkg_name.replace("-", "_")
                if normalized in ep.value or ep.name.startswith(pkg_name):
                    pkg_match = pkg_name
                    break

            if pkg_match is None:
                continue

            text = f"{ep.name} {ep.value}"
            s = score_text(pq, text, fuzzy=fuzzy)
            if s > 0:
                results.append(
                    _make_result(
                        pkg_match,
                        ep.name,
                        f"CLI: {ep.value}",
                        s,
                        "cli",
                        "console_script",
                    )
                )
    except Exception:
        logger.debug("Failed to search CLI entry points")

    return results


def _search_mcp(
    pq: ParsedQuery,
    targets: dict[str, Optional[str]],
    fuzzy: bool = True,
) -> list[dict[str, Any]]:
    """Search MCP tool names and descriptions."""
    results = []

    for pkg_name, module_name in targets.items():
        if module_name is None:
            continue

        pkg_root = get_package_root(module_name)
        if pkg_root is None:
            continue

        mcp_candidates = [
            pkg_root / "_mcp_tools",
            pkg_root / "mcp",
            pkg_root / "_mcp",
        ]

        for mcp_dir in mcp_candidates:
            if not mcp_dir.exists():
                continue
            for py_file in mcp_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                try:
                    content = py_file.read_text(encoding="utf-8")
                except OSError:
                    continue

                for match in re.finditer(
                    r'(?:async\s+)?def\s+(\w+)\s*\([^)]*\)\s*(?:->.*?)?:\s*\n\s*"""([^"]*)',
                    content,
                ):
                    func_name = match.group(1)
                    docstring = match.group(2).strip()
                    text = f"{func_name} {docstring}"
                    s = score_text(pq, text, fuzzy=fuzzy)
                    if s > 0:
                        results.append(
                            _make_result(
                                pkg_name,
                                func_name,
                                docstring[:80],
                                s,
                                "mcp",
                                "mcp_tool",
                            )
                        )

    return results
