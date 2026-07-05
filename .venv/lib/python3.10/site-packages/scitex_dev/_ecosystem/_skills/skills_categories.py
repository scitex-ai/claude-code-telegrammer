"""Category map and root-index renderer for the SciTeX skills tree.

Skills exported by ``scitex-dev skills export`` land flat under
``~/.claude/skills/scitex/<pkg>/``. This module groups packages into
numbered categories so the root ``SKILL.md`` index is discoverable,
mirroring the ``ywatanabe`` skills layout (``NN_<category>/...``).

The on-disk layout stays flat — only the rendered index is grouped —
so symlinks created by ``--link`` mode keep working without rewrites.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


# (category_id, human label, [pkg_name, ...]).
# category_id uses NN_ prefix so the rendered index sorts naturally.
# Packages absent from this list fall through to ``99_other``; nothing
# is silently dropped when a new package is added upstream.
SCITEX_CATEGORIES: list[tuple[str, str, list[str]]] = [
    ("00_general", "General Standards (read first)", ["general"]),
    (
        "01_core",
        "Core runtime — session, types, paths, logging",
        [
            "scitex",
            "scitex-compat",
            "scitex-types",
            "scitex-path",
            "scitex-str",
            "scitex-dict",
            "scitex-logging",
            "scitex-etc",
        ],
    ),
    (
        "02_io",
        "File I/O, databases, notebooks",
        ["scitex-io", "scitex-db", "scitex-notebook"],
    ),
    (
        "03_plotting",
        "Publication-ready figures",
        ["scitex-plt", "figrecipe"],
    ),
    (
        "04_stats",
        "Statistical testing",
        ["scitex-stats"],
    ),
    (
        "05_data",
        "Datasets and bibliographic databases",
        [
            "scitex-dataset",
            "scitex-scholar",
            "crossref-local",
            "openalex-local",
        ],
    ),
    (
        "06_writing",
        "LaTeX, manuscripts, gists",
        ["scitex-writer", "scitex-gists"],
    ),
    (
        "07_infra",
        "Hub, containers, tunnels, orochi",
        [
            "scitex-hub",
            "scitex-container",
            "scitex-ssh",
            "scitex-orochi",
            "scitex-orochi-private",
            "scitex-agent-container",
            "scitex-parallel",
        ],
    ),
    (
        "08_dev",
        "Dev tooling — linter, audit, repro, clew, templates",
        [
            "scitex-dev",
            "scitex-repro",
            "scitex-clew",
        ],
    ),
    (
        "09_ux",
        "Audio, notification, browser, UI, social",
        [
            "scitex-audio",
            "scitex-notification",
            "scitex-browser",
            "scitex-ui",
            "scitex-app",
            "socialia",
        ],
    ),
]


def categorize(
    exported_packages: Mapping[str, object],
) -> list[tuple[str, str, list[str]]]:
    """Return ``[(category_id, label, [pkg, ...]), ...]`` in display order.

    Packages present in ``exported_packages`` but not in
    :data:`SCITEX_CATEGORIES` are placed under ``99_other`` so the index
    never silently drops a package added upstream.
    """
    seen: set[str] = set()
    grouped: list[tuple[str, str, list[str]]] = []
    for cat_id, label, members in SCITEX_CATEGORIES:
        present = [m for m in members if m in exported_packages]
        if present:
            grouped.append((cat_id, label, present))
            seen.update(present)
    leftovers = sorted(set(exported_packages) - seen)
    if leftovers:
        grouped.append(("99_other", "Other", leftovers))
    return grouped


def render_root_skill_md(dest: Path, exported_packages: Mapping[str, object]) -> None:
    """Write ``<dest>/SKILL.md`` — the categorized root index.

    The ``description`` uses the directive ``ALWAYS invoke ... Do not ...``
    pattern shown to materially improve skill activation rate (≈88.9% vs
    ≈20% for passive descriptions in a 650-trial study).
    """
    if not exported_packages:
        return

    lines = [
        "---",
        "name: scitex",
        (
            "description: ALWAYS invoke this skill when working on any "
            "SciTeX package or ecosystem-wide convention "
            "(io, plt, stats, writer, cloud, container, scholar, etc.). "
            "Do not write SciTeX-pattern code without consulting the "
            "relevant package skill first."
        ),
        "user-invocable: false",
        "---",
        "",
        "# SciTeX Ecosystem Skills",
        "",
        "Skills are grouped into numbered categories for discoverability.",
        "Inside each package skill, leaf files also use `NN_*.md` ordering.",
        "",
    ]

    for cat_id, label, members in categorize(exported_packages):
        lines.append(f"## {cat_id} — {label}")
        for pkg in members:
            lines.append(f"- [{pkg}]({pkg}/SKILL.md)")
        lines.append("")

    skill_md = dest / "SKILL.md"
    if skill_md.exists():
        skill_md.chmod(0o644)
    skill_md.write_text("\n".join(lines))
