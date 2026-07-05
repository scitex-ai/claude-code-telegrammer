#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SciTeX ecosystem dependency graph generator.

Parse every ecosystem ``pyproject.toml`` on demand and emit current-state
dependency graphs (mermaid / DOT) plus analyses (cycles, fan-in/out).

The package list is *derived from the filesystem* — never hardcoded — so
the output reflects reality at run time and cannot drift.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


# Ecosystem package-name regex. Used both to discover and to filter edges.
ECOSYSTEM_NAME_RE = re.compile(
    r"^(scitex-[a-z0-9-]+|figrecipe|crossref-local|openalex-local)$"
)

# Strip trailing version specifier from a dependency string:
#   "scitex-io>=0.1.0" -> "scitex-io"
#   "scitex-io[extra]>=0.1.0" -> "scitex-io"
_DEP_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*(?:[<>=!~;].*)?$")

# Heuristic tier mapping. Pure heuristic — only used for visual subgraphs in
# mermaid output. Adding a new ecosystem package without classifying it just
# falls through to "other" and the graph still renders.
TIER_MAP: Dict[str, str] = {
    # foundational — zero/few ecosystem deps, leaf packages
    "scitex-io": "foundational",
    "scitex-types": "foundational",
    "scitex-logging": "foundational",
    "scitex-decorators": "foundational",
    "scitex-str": "foundational",
    "scitex-path": "foundational",
    "scitex-os": "foundational",
    "scitex-context": "foundational",
    "scitex-errors": "foundational",
    # middle — utility / domain libs
    "scitex-pd": "middle",
    "scitex-plt": "middle",
    "scitex-stats": "middle",
    "scitex-dsp": "middle",
    "scitex-nn": "middle",
    "scitex-linalg": "middle",
    "scitex-dict": "middle",
    "scitex-datetime": "middle",
    "scitex-repro": "middle",
    "scitex-config": "middle",
    "scitex-session": "middle",
    "scitex-db": "middle",
    "scitex-tex": "middle",
    "scitex-parallel": "middle",
    "scitex-resource": "middle",
    "scitex-web": "middle",
    "scitex-notification": "middle",
    "scitex-dev": "middle",
    "scitex-clew": "middle",
    "scitex-ui": "middle",
    "scitex-app": "middle",
    "figrecipe": "middle",
    "crossref-local": "middle",
    "openalex-local": "middle",
    # apps — user-facing endpoints, large fan-in
    "scitex": "apps",
    "scitex-writer": "apps",
    "scitex-scholar": "apps",
    "scitex-hub": "apps",
    "scitex-template": "apps",
}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _default_roots() -> List[Path]:
    """Default search globs covering the SciTeX ecosystem layout."""
    proj = Path.home() / "proj"
    return [proj]


def discover_packages(roots: Optional[Iterable[Path]] = None) -> Dict[str, Path]:
    """Discover ecosystem ``pyproject.toml`` files on disk.

    Returns a mapping ``{pkg_name: pyproject_path}``. The set of packages is
    derived purely from the filesystem and the
    :data:`ECOSYSTEM_NAME_RE` filter — *never* hardcoded.
    """
    roots = list(roots) if roots else _default_roots()
    out: Dict[str, Path] = {}
    for root in roots:
        root = Path(root).expanduser()
        if not root.exists():
            continue
        # Each ecosystem package lives at <root>/<pkg-dir>/pyproject.toml
        for pyproj in sorted(root.glob("*/pyproject.toml")):
            try:
                with pyproj.open("rb") as fh:
                    data = tomllib.load(fh)
            except (OSError, tomllib.TOMLDecodeError):
                continue
            name = (data.get("project") or {}).get("name")
            if not name:
                continue
            if not ECOSYSTEM_NAME_RE.match(name):
                continue
            # Prefer first occurrence; later duplicates ignored.
            out.setdefault(name, pyproj)
    return out


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _strip_dep(spec: str) -> Optional[str]:
    """Return the bare distribution name from a PEP 508 string, or None."""
    m = _DEP_RE.match(spec)
    if not m:
        return None
    return m.group(1).strip().lower()


def parse_deps(pyproject_path: Path) -> Dict:
    """Parse a pyproject.toml's project metadata into ecosystem-only deps.

    Returns ``{"name": str, "hard": [...], "extras": {extra: [...]}}`` where
    every listed name is an ecosystem package (others are filtered out).
    """
    with Path(pyproject_path).open("rb") as fh:
        data = tomllib.load(fh)

    project = data.get("project") or {}
    name = project.get("name", "")

    def _filter(deps: Iterable[str]) -> List[str]:
        result: List[str] = []
        for raw in deps or []:
            stripped = _strip_dep(raw)
            if stripped and ECOSYSTEM_NAME_RE.match(stripped):
                # Don't list self-edges (e.g. all-extra referencing self).
                if stripped != name:
                    result.append(stripped)
        # Stable, dedup
        return sorted(set(result))

    hard = _filter(project.get("dependencies", []))
    extras_raw = project.get("optional-dependencies", {}) or {}
    extras: Dict[str, List[str]] = {}
    for extra_name, deps in extras_raw.items():
        filtered = _filter(deps)
        if filtered:
            extras[extra_name] = filtered

    return {"name": name, "hard": hard, "extras": extras}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_graph(pkgs: Dict[str, Path]) -> Dict[str, Dict]:
    """Build adjacency dict ``{pkg: {"hard": set, "extras": {extra: set}}}``."""
    graph: Dict[str, Dict] = {}
    for name, path in pkgs.items():
        info = parse_deps(path)
        graph[name] = {
            "hard": set(info["hard"]),
            "extras": {k: set(v) for k, v in info["extras"].items()},
        }
    return graph


def _all_edges(
    graph: Dict[str, Dict], include_extras: bool = True
) -> Set[Tuple[str, str]]:
    edges: Set[Tuple[str, str]] = set()
    for src, info in graph.items():
        for dst in info.get("hard", set()):
            edges.add((src, dst))
        if include_extras:
            for deps in info.get("extras", {}).values():
                for dst in deps:
                    edges.add((src, dst))
    return edges


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def find_cycles(
    graph: Dict[str, Dict], include_extras: bool = False
) -> List[List[str]]:
    """Return non-trivial dependency cycles via Tarjan's SCC algorithm.

    Self-loops are ignored. By default only hard deps are considered — opting
    in to extras (``include_extras=True``) is noisy because ``[all]`` extras
    legitimately re-reference siblings.
    """
    # Build adjacency restricted to nodes present in the graph.
    nodes = list(graph.keys())
    adj: Dict[str, Set[str]] = {n: set() for n in nodes}
    for src, dst in _all_edges(graph, include_extras=include_extras):
        if src in adj and dst in adj and src != dst:
            adj[src].add(dst)

    # Tarjan's SCC
    index_counter = [0]
    stack: List[str] = []
    on_stack: Set[str] = set()
    indices: Dict[str, int] = {}
    lowlinks: Dict[str, int] = {}
    sccs: List[List[str]] = []

    def strongconnect(v: str) -> None:
        indices[v] = index_counter[0]
        lowlinks[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in adj[v]:
            if w not in indices:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif w in on_stack:
                lowlinks[v] = min(lowlinks[v], indices[w])
        if lowlinks[v] == indices[v]:
            comp: List[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))

    for v in nodes:
        if v not in indices:
            strongconnect(v)
    return sccs


def fan_in_out(
    graph: Dict[str, Dict], include_extras: bool = True
) -> Tuple[Counter, Counter]:
    """Return ``(fan_in, fan_out)`` ``Counter`` objects.

    * ``fan_in[pkg]``  = number of ecosystem packages depending on ``pkg``.
    * ``fan_out[pkg]`` = number of ecosystem packages ``pkg`` depends on.
    """
    fan_in: Counter = Counter()
    fan_out: Counter = Counter()
    for src, dst in _all_edges(graph, include_extras=include_extras):
        fan_out[src] += 1
        fan_in[dst] += 1
    # Ensure every node appears (even with zero count) for stable reporting.
    for n in graph:
        fan_in.setdefault(n, 0)
        fan_out.setdefault(n, 0)
    return fan_in, fan_out


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _node_id(name: str) -> str:
    """Mermaid/DOT-safe node id."""
    return name.replace("-", "_")


def _classify_tier(graph: Dict[str, Dict]) -> Dict[str, List[str]]:
    """Group package names by tier; unclassified -> ``other``."""
    groups: Dict[str, List[str]] = defaultdict(list)
    for name in graph:
        tier = TIER_MAP.get(name, "other")
        groups[tier].append(name)
    for v in groups.values():
        v.sort()
    return groups


def to_mermaid(
    graph: Dict[str, Dict],
    *,
    group_by_tier: bool = True,
    include_extras: bool = True,
) -> str:
    """Emit a mermaid ``graph LR`` representation."""
    lines: List[str] = ["graph LR"]

    # Subgraphs by tier (visual only).
    if group_by_tier:
        groups = _classify_tier(graph)
        order = ["foundational", "middle", "apps", "other"]
        for tier in order:
            members = groups.get(tier, [])
            if not members:
                continue
            lines.append(f"    subgraph {tier}")
            for name in members:
                lines.append(f"        {_node_id(name)}[{name}]")
            lines.append("    end")
    else:
        for name in sorted(graph):
            lines.append(f"    {_node_id(name)}[{name}]")

    # Edges
    for src in sorted(graph):
        info = graph[src]
        for dst in sorted(info.get("hard", set())):
            if dst in graph:
                lines.append(f"    {_node_id(src)} --> {_node_id(dst)}")
        if include_extras:
            seen: Set[str] = set()
            for deps in info.get("extras", {}).values():
                for dst in sorted(deps):
                    if dst in info.get("hard", set()):
                        continue
                    if dst in seen or dst not in graph:
                        continue
                    seen.add(dst)
                    lines.append(f"    {_node_id(src)} -.-> {_node_id(dst)}")

    return "\n".join(lines) + "\n"


def to_dot(graph: Dict[str, Dict], *, include_extras: bool = True) -> str:
    """Emit a graphviz DOT representation."""
    lines: List[str] = ["digraph scitex_ecosystem {", "    rankdir=LR;"]
    for name in sorted(graph):
        lines.append(f'    {_node_id(name)} [label="{name}"];')
    for src in sorted(graph):
        info = graph[src]
        hard = info.get("hard", set())
        for dst in sorted(hard):
            if dst in graph:
                lines.append(f"    {_node_id(src)} -> {_node_id(dst)};")
        if include_extras:
            seen: Set[str] = set()
            for deps in info.get("extras", {}).values():
                for dst in sorted(deps):
                    if dst in hard or dst in seen or dst not in graph:
                        continue
                    seen.add(dst)
                    lines.append(
                        f"    {_node_id(src)} -> {_node_id(dst)} [style=dashed];"
                    )
    lines.append("}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# High-level convenience
# ---------------------------------------------------------------------------


def render(
    fmt: str = "mermaid",
    *,
    roots: Optional[Iterable[Path]] = None,
    include_extras: bool = True,
    group_by_tier: bool = True,
) -> str:
    """Discover + render in one step. Used by the CLI."""
    pkgs = discover_packages(roots=roots)
    graph = build_graph(pkgs)
    if fmt == "mermaid":
        return to_mermaid(
            graph, group_by_tier=group_by_tier, include_extras=include_extras
        )
    if fmt == "dot":
        return to_dot(graph, include_extras=include_extras)
    raise ValueError(f"Unknown format: {fmt!r} (expected 'mermaid' or 'dot')")
