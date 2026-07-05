#!/usr/bin/env python3
# Timestamp: 2026-06-07
# File: scitex_dev/_ecosystem/_registry.py

"""SciTeX ecosystem package registry — *data only*.

This module owns the single ``ECOSYSTEM`` dict and the ``PackageInfo``
schema. It is intentionally pure data so the dependency-aware helpers
(``get_local_path`` / ``should_skip_audit`` / etc. in ``_core.py``)
and the upcoming SSoT generator
(``scitex-dev ecosystem regen-umbrella``, which will derive the
umbrella's ``[all]`` extras, ``lazy_attrs`` map, MCP / CLI mounts
from this same dict) can both consume it without circular imports.

Every public name is re-exported from ``scitex_dev._ecosystem._core``
for backwards compatibility, so existing callers
(``from scitex_dev._ecosystem._core import ECOSYSTEM`` — many) keep
working.
"""

from typing import Dict, TypedDict


class PackageInfo(TypedDict, total=False):
    """Package information structure.

    ``category`` controls how the auditor and ecosystem CLI treat the
    entry:

    - ``umbrella``     — top-level ``scitex`` package; full audit
    - ``library``      — standard ``scitex-*`` leaf; full audit
    - ``external-lib`` — non-scitex-prefixed lib (figrecipe, socialia,
                          newb); full audit
    - ``template``     — scaffolds; auditor skips §C5/§E/§L by default
    - ``dataset``      — data-only repos (crossref-local, openalex-local);
                          auditor skips §E (no SKILL.md required)

    ``archived`` (optional, default False) — set ``True`` for repos
    that have been GitHub-archived (read-only) and superseded. The
    CLA / quality / publish auditors short-circuit on archived; the
    entry stays in the registry so historical refs resolve.

    ``umbrella_subcommand`` (optional) — the name this package mounts
    as under the umbrella ``scitex`` CLI / MCP server. For
    ``scitex-<x>`` the default is the part after ``scitex-`` (so
    ``scitex-dataset`` → ``dataset``). Branded packages without the
    prefix (``socialia`` → ``social``, ``figrecipe`` → ``plt``) MUST
    set this explicitly; the umbrella shim and ``audit-cli §5b`` /
    ``audit-mcp-tools §1`` read it to know how to rewrite the program
    name and validate the mount namespace. See
    ``_skills/general/03_interface/02_cli/05a_umbrella-passthrough.md``.

    Umbrella SSoT fields (optional, all consumed by
    ``scitex_dev._ecosystem._umbrella``; defaults are *derived* from
    ``import_name`` so most entries don't need to set them):

    - ``umbrella_lazy_short`` — the ``scitex.<short>`` lazy-module
      alias name. Default = ``import_name.removeprefix("scitex_")``.
      Set explicitly for branded packages (``socialia`` → ``"social"``,
      ``figrecipe`` → ``"fig"``).
    - ``umbrella_extra`` — the ``scitex[<extra>]`` extra-group name
      shipped in the umbrella's ``[project.optional-dependencies]``.
      Default = ``umbrella_lazy_short`` (same name as the alias). Set
      explicitly when the extra name differs from the alias.
    - ``umbrella_external`` — the peer import target used in
      ``EXTERNAL_REEXPORTS`` (the lazy-loader bridge that makes
      ``import scitex.<short>.<sub>`` resolve to the peer standalone).
      Default = ``import_name`` (e.g. ``scitex_io``). Set explicitly
      when the umbrella alias points at a *sub*-module of the peer
      (e.g. ``media`` → ``"scitex_etc.media"``).
    - ``umbrella_core_dep`` — ``True`` iff this peer is pinned in the
      umbrella's core ``dependencies`` (always installed), not just an
      optional extra. Default ``False``.
    - ``umbrella_skip`` — ``True`` iff this entry should NOT be auto-
      mounted by the SSoT generator (e.g. ``scitex-dev`` itself is
      installed but exposes no ``scitex.dev`` lazy_attr beyond the
      in-tree shim; optional peers like ``scitex-hub`` are mounted
      via the auxiliary ``_umbrella.AUX_MOUNTS`` table instead so
      ``[all]`` can deliberately exclude them). Default ``False``.
    """

    local_path: str
    pypi_name: str
    github_repo: str
    import_name: str
    category: str
    archived: bool
    umbrella_subcommand: str
    umbrella_lazy_short: str
    umbrella_extra: str
    umbrella_external: str
    umbrella_core_dep: bool
    umbrella_skip: bool


# Ordered dict — order matters for display.
ECOSYSTEM: Dict[str, PackageInfo] = {
    "scitex": {
        "local_path": "~/proj/scitex-python",
        "pypi_name": "scitex",
        "github_repo": "ywatanabe1989/scitex-python",
        "import_name": "scitex",
        "category": "umbrella",
    },
    "scitex-io": {
        "local_path": "~/proj/scitex-io",
        "pypi_name": "scitex-io",
        "github_repo": "ywatanabe1989/scitex-io",
        "import_name": "scitex_io",
        "category": "library",
    },
    "scitex-stats": {
        "local_path": "~/proj/scitex-stats",
        "pypi_name": "scitex-stats",
        "github_repo": "ywatanabe1989/scitex-stats",
        "import_name": "scitex_stats",
        "category": "library",
    },
    "scitex-clew": {
        "local_path": "~/proj/scitex-clew",
        "pypi_name": "scitex-clew",
        "github_repo": "ywatanabe1989/scitex-clew",
        "import_name": "scitex_clew",
        "category": "library",
    },
    "scitex-hub": {
        "local_path": "~/proj/scitex-hub",
        "pypi_name": "scitex-hub",
        "github_repo": "ywatanabe1989/scitex-hub",
        "import_name": "scitex_hub",
        "category": "library",
    },
    "figrecipe": {
        "local_path": "~/proj/figrecipe",
        "pypi_name": "figrecipe",
        "github_repo": "ywatanabe1989/figrecipe",
        "import_name": "figrecipe",
        "category": "external-lib",
    },
    "newb": {
        "local_path": "~/proj/newb",
        "pypi_name": "newb",
        "github_repo": "ywatanabe1989/newb",
        "import_name": "newb",
        "category": "external-lib",
    },
    "openalex-local": {
        "local_path": "~/proj/openalex-local",
        "pypi_name": "openalex-local",
        "github_repo": "ywatanabe1989/openalex-local",
        "import_name": "openalex_local",
        "category": "dataset",
    },
    "crossref-local": {
        "local_path": "~/proj/crossref-local",
        "pypi_name": "crossref-local",
        "github_repo": "ywatanabe1989/crossref-local",
        "import_name": "crossref_local",
        "category": "dataset",
    },
    "scitex-writer": {
        "local_path": "~/proj/scitex-writer",
        "pypi_name": "scitex-writer",
        "github_repo": "ywatanabe1989/scitex-writer",
        "import_name": "scitex_writer",
        "category": "library",
    },
    "scitex-dataset": {
        "local_path": "~/proj/scitex-dataset",
        "pypi_name": "scitex-dataset",
        "github_repo": "ywatanabe1989/scitex-dataset",
        "import_name": "scitex_dataset",
        "category": "library",
    },
    "socialia": {
        "local_path": "~/proj/socialia",
        "pypi_name": "socialia",
        "github_repo": "ywatanabe1989/socialia",
        "import_name": "socialia",
        "category": "external-lib",
    },
    "scitex-container": {
        "local_path": "~/proj/scitex-container",
        "pypi_name": "scitex-container",
        "github_repo": "ywatanabe1989/scitex-container",
        "import_name": "scitex_container",
        "category": "library",
    },
    "scitex-ssh": {
        "local_path": "~/proj/scitex-ssh",
        "pypi_name": "scitex-ssh",
        "github_repo": "ywatanabe1989/scitex-ssh",
        "import_name": "scitex_ssh",
        "category": "library",
    },
    "scitex-ui": {
        "local_path": "~/proj/scitex-ui",
        "pypi_name": "scitex-ui",
        "github_repo": "ywatanabe1989/scitex-ui",
        "import_name": "scitex_ui",
        "category": "library",
    },
    "scitex-app": {
        "local_path": "~/proj/scitex-app",
        "pypi_name": "scitex-app",
        "github_repo": "ywatanabe1989/scitex-app",
        "import_name": "scitex_app",
        "category": "library",
    },
    "scitex-audio": {
        "local_path": "~/proj/scitex-audio",
        "pypi_name": "scitex-audio",
        "github_repo": "ywatanabe1989/scitex-audio",
        "import_name": "scitex_audio",
        "category": "library",
    },
    "scitex-audit": {
        # Security audit orchestrator (bandit, shellcheck, pip-audit, GH
        # alerts). Added 2026-06-07 to close #132 — on PyPI and mounted
        # as ``scitex.audit`` (lazy_attr + ``[audit]`` extra) but missing
        # from this registry, so audit-all and umbrella-extras
        # reconciliation did not know about it.
        "local_path": "~/proj/scitex-audit",
        "pypi_name": "scitex-audit",
        "github_repo": "ywatanabe1989/scitex-audit",
        "import_name": "scitex_audit",
        "category": "library",
    },
    "scitex-parallel": {
        "local_path": "~/proj/scitex-parallel",
        "pypi_name": "scitex-parallel",
        "github_repo": "ywatanabe1989/scitex-parallel",
        "import_name": "scitex_parallel",
        "category": "library",
    },
    "scitex-types": {
        "local_path": "~/proj/scitex-types",
        "pypi_name": "scitex-types",
        "github_repo": "ywatanabe1989/scitex-types",
        "import_name": "scitex_types",
        "category": "library",
    },
    "scitex-path": {
        "local_path": "~/proj/scitex-path",
        "pypi_name": "scitex-path",
        "github_repo": "ywatanabe1989/scitex-path",
        "import_name": "scitex_path",
        "category": "library",
    },
    "scitex-repro": {
        "local_path": "~/proj/scitex-repro",
        "pypi_name": "scitex-repro",
        "github_repo": "ywatanabe1989/scitex-repro",
        "import_name": "scitex_repro",
        "category": "library",
    },
    "scitex-compat": {
        "local_path": "~/proj/scitex-compat",
        "pypi_name": "scitex-compat",
        "github_repo": "ywatanabe1989/scitex-compat",
        "import_name": "scitex_compat",
        "category": "library",
    },
    "scitex-etc": {
        "local_path": "~/proj/scitex-etc",
        "pypi_name": "scitex-etc",
        "github_repo": "ywatanabe1989/scitex-etc",
        "import_name": "scitex_etc",
        "category": "library",
    },
    "scitex-gists": {
        "local_path": "~/proj/scitex-gists",
        "pypi_name": "scitex-gists",
        "github_repo": "ywatanabe1989/scitex-gists",
        "import_name": "scitex_gists",
        "category": "library",
    },
    "scitex-db": {
        "local_path": "~/proj/scitex-db",
        "pypi_name": "scitex-db",
        "github_repo": "ywatanabe1989/scitex-db",
        "import_name": "scitex_db",
        "category": "library",
    },
    "scitex-scholar": {
        "local_path": "~/proj/scitex-scholar",
        "pypi_name": "scitex-scholar",
        "github_repo": "ywatanabe1989/scitex-scholar",
        "import_name": "scitex_scholar",
        "category": "library",
    },
    "scitex-seizure-metrics": {
        "local_path": "~/proj/scitex-seizure-metrics",
        "pypi_name": "scitex-seizure-metrics",
        "github_repo": "ywatanabe1989/scitex-seizure-metrics",
        "import_name": "scitex_seizure_metrics",
        "category": "library",
    },
    "scitex-template": {
        "local_path": "~/proj/scitex-template",
        "pypi_name": "scitex-template",
        "github_repo": "ywatanabe1989/scitex-template",
        "import_name": "scitex_template",
        "category": "template",
    },
    "scitex-dev": {
        "local_path": "~/proj/scitex-dev",
        "pypi_name": "scitex-dev",
        "github_repo": "ywatanabe1989/scitex-dev",
        "import_name": "scitex_dev",
        "category": "library",
    },
    "scitex-agent-container": {
        "local_path": "~/proj/scitex-agent-container",
        "pypi_name": "scitex-agent-container",
        "github_repo": "ywatanabe1989/scitex-agent-container",
        "import_name": "scitex_agent_container",
        "category": "library",
    },
    "scitex-orochi": {
        "local_path": "~/proj/scitex-orochi",
        "pypi_name": "scitex-orochi",
        "github_repo": "ywatanabe1989/scitex-orochi",
        "import_name": "scitex_orochi",
        "category": "library",
    },
    "scitex-str": {
        "local_path": "~/proj/scitex-str",
        "pypi_name": "scitex-str",
        "github_repo": "ywatanabe1989/scitex-str",
        "import_name": "scitex_str",
        "category": "library",
    },
    "scitex-logging": {
        "local_path": "~/proj/scitex-logging",
        "pypi_name": "scitex-logging",
        "github_repo": "ywatanabe1989/scitex-logging",
        "import_name": "scitex_logging",
        "category": "library",
    },
    "scitex-dict": {
        "local_path": "~/proj/scitex-dict",
        "pypi_name": "scitex-dict",
        "github_repo": "ywatanabe1989/scitex-dict",
        "import_name": "scitex_dict",
        "category": "library",
    },
    "scitex-browser": {
        "local_path": "~/proj/scitex-browser",
        "pypi_name": "scitex-browser",
        "github_repo": "ywatanabe1989/scitex-browser",
        "import_name": "scitex_browser",
        "category": "library",
    },
    "scitex-config": {
        "local_path": "~/proj/scitex-config",
        "pypi_name": "scitex-config",
        "github_repo": "ywatanabe1989/scitex-config",
        "import_name": "scitex_config",
        "category": "library",
    },
    "scitex-context": {
        "local_path": "~/proj/scitex-context",
        "pypi_name": "scitex-context",
        "github_repo": "ywatanabe1989/scitex-context",
        "import_name": "scitex_context",
        "category": "library",
    },
    "scitex-events": {
        "local_path": "~/proj/scitex-events",
        "pypi_name": "scitex-events",
        "github_repo": "ywatanabe1989/scitex-events",
        "import_name": "scitex_events",
        "category": "library",
    },
    "scitex-hpc": {
        "local_path": "~/proj/scitex-hpc",
        "pypi_name": "scitex-hpc",
        "github_repo": "ywatanabe1989/scitex-hpc",
        "import_name": "scitex_hpc",
        "category": "library",
    },
    "scitex-decorators": {
        "local_path": "~/proj/scitex-decorators",
        "pypi_name": "scitex-decorators",
        "github_repo": "ywatanabe1989/scitex-decorators",
        "import_name": "scitex_decorators",
        "category": "library",
    },
    "scitex-pd": {
        "local_path": "~/proj/scitex-pd",
        "pypi_name": "scitex-pd",
        "github_repo": "ywatanabe1989/scitex-pd",
        "import_name": "scitex_pd",
        "category": "library",
    },
    "scitex-plt": {
        "local_path": "~/proj/scitex-plt",
        "pypi_name": "scitex-plt",
        "github_repo": "ywatanabe1989/scitex-plt",
        "import_name": "scitex_plt",
        "category": "library",
    },
    "scitex-nn": {
        "local_path": "~/proj/scitex-nn",
        "pypi_name": "scitex-nn",
        "github_repo": "ywatanabe1989/scitex-nn",
        "import_name": "scitex_nn",
        "category": "library",
    },
    "scitex-math": {
        # Mathematical utilities (parity helpers, etc.). Added
        # 2026-06-07 alongside scitex-audit (#132 batch) — on PyPI and
        # GH but was absent from this registry.
        "local_path": "~/proj/scitex-math",
        "pypi_name": "scitex-math",
        "github_repo": "ywatanabe1989/scitex-math",
        "import_name": "scitex_math",
        "category": "library",
    },
    "scitex-ml": {
        "local_path": "~/proj/scitex-ml",
        "pypi_name": "scitex-ml",
        "github_repo": "ywatanabe1989/scitex-ml",
        "import_name": "scitex_ml",
        "category": "library",
    },
    "scitex-genai": {
        "local_path": "~/proj/scitex-genai",
        "pypi_name": "scitex-genai",
        "github_repo": "ywatanabe1989/scitex-genai",
        "import_name": "scitex_genai",
        "category": "library",
    },
    "scitex-dsp": {
        "local_path": "~/proj/scitex-dsp",
        "pypi_name": "scitex-dsp",
        "github_repo": "ywatanabe1989/scitex-dsp",
        "import_name": "scitex_dsp",
        "category": "library",
    },
    "scitex-benchmark": {
        "local_path": "~/proj/scitex-benchmark",
        "pypi_name": "scitex-benchmark",
        "github_repo": "ywatanabe1989/scitex-benchmark",
        "import_name": "scitex_benchmark",
        "category": "library",
    },
    "scitex-bridge": {
        # GH-archived 2026 — cross-module adapter shim superseded by
        # inline integration in scitex-stats / scitex-plt. Kept in the
        # registry so historical refs resolve; auditors short-circuit
        # on archived=True.
        "local_path": "~/proj/scitex-bridge",
        "pypi_name": "scitex-bridge",
        "github_repo": "ywatanabe1989/scitex-bridge",
        "import_name": "scitex_bridge",
        "category": "library",
        "archived": True,
    },
    "scitex-capture": {
        "local_path": "~/proj/scitex-capture",
        "pypi_name": "scitex-capture",
        "github_repo": "ywatanabe1989/scitex-capture",
        "import_name": "scitex_capture",
        "category": "library",
    },
    "scitex-cv": {
        "local_path": "~/proj/scitex-cv",
        "pypi_name": "scitex-cv",
        "github_repo": "ywatanabe1989/scitex-cv",
        "import_name": "scitex_cv",
        "category": "library",
    },
    "scitex-datetime": {
        "local_path": "~/proj/scitex-datetime",
        "pypi_name": "scitex-datetime",
        "github_repo": "ywatanabe1989/scitex-datetime",
        "import_name": "scitex_datetime",
        "category": "library",
    },
    "scitex-git": {
        "local_path": "~/proj/scitex-git",
        "pypi_name": "scitex-git",
        "github_repo": "ywatanabe1989/scitex-git",
        "import_name": "scitex_git",
        "category": "library",
    },
    "scitex-introspect": {
        "local_path": "~/proj/scitex-introspect",
        "pypi_name": "scitex-introspect",
        "github_repo": "ywatanabe1989/scitex-introspect",
        "import_name": "scitex_introspect",
        "category": "library",
    },
    "scitex-linalg": {
        "local_path": "~/proj/scitex-linalg",
        "pypi_name": "scitex-linalg",
        "github_repo": "ywatanabe1989/scitex-linalg",
        "import_name": "scitex_linalg",
        "category": "library",
    },
    "scitex-msword": {
        "local_path": "~/proj/scitex-msword",
        "pypi_name": "scitex-msword",
        "github_repo": "ywatanabe1989/scitex-msword",
        "import_name": "scitex_msword",
        "category": "library",
    },
    "scitex-notebook": {
        "local_path": "~/proj/scitex-notebook",
        "pypi_name": "scitex-notebook",
        "github_repo": "ywatanabe1989/scitex-notebook",
        "import_name": "scitex_notebook",
        "category": "library",
    },
    "scitex-notification": {
        "local_path": "~/proj/scitex-notification",
        "pypi_name": "scitex-notification",
        "github_repo": "ywatanabe1989/scitex-notification",
        "import_name": "scitex_notification",
        "category": "library",
    },
    "scitex-os": {
        "local_path": "~/proj/scitex-os",
        "pypi_name": "scitex-os",
        "github_repo": "ywatanabe1989/scitex-os",
        "import_name": "scitex_os",
        "category": "library",
    },
    "scitex-repl": {
        # Interactive REPL helpers (embed, less, paste). Added
        # 2026-06-07 — shipped to PyPI as v0.1.1 on 2026-06-06
        # (alongside the scitex-math v0.1.x release wave).
        "local_path": "~/proj/scitex-repl",
        "pypi_name": "scitex-repl",
        "github_repo": "ywatanabe1989/scitex-repl",
        "import_name": "scitex_repl",
        "category": "library",
    },
    "scitex-resource": {
        "local_path": "~/proj/scitex-resource",
        "pypi_name": "scitex-resource",
        "github_repo": "ywatanabe1989/scitex-resource",
        "import_name": "scitex_resource",
        "category": "library",
    },
    "scitex-security": {
        # Absorbed into scitex-audit 2026-06-07 per ADR-0001 (#139).
        # scitex-security 0.2.0 is a deprecated re-export shim of
        # ``scitex_audit.github``; the standalone repo will be yanked from
        # PyPI at W3 once reconcile-versions confirms zero downstream
        # pins. Kept here with archived=True so historical refs +
        # umbrella-extras reconciliation know not to expect an active
        # standalone going forward (mirrors the scitex-linter precedent).
        "local_path": "~/proj/scitex-security",
        "pypi_name": "scitex-security",
        "github_repo": "ywatanabe1989/scitex-security",
        "import_name": "scitex_security",
        "category": "library",
        "archived": True,
    },
    "scitex-session": {
        "local_path": "~/proj/scitex-session",
        "pypi_name": "scitex-session",
        "github_repo": "ywatanabe1989/scitex-session",
        "import_name": "scitex_session",
        "category": "library",
    },
    "scitex-sh": {
        "local_path": "~/proj/scitex-sh",
        "pypi_name": "scitex-sh",
        "github_repo": "ywatanabe1989/scitex-sh",
        "import_name": "scitex_sh",
        "category": "library",
    },
    "scitex-tex": {
        "local_path": "~/proj/scitex-tex",
        "pypi_name": "scitex-tex",
        "github_repo": "ywatanabe1989/scitex-tex",
        "import_name": "scitex_tex",
        "category": "library",
    },
    "scitex-todo": {
        "local_path": "~/proj/scitex-todo",
        "pypi_name": "scitex-todo",
        "github_repo": "ywatanabe1989/scitex-todo",
        "import_name": "scitex_todo",
        "category": "library",
    },
    "scitex-web": {
        "local_path": "~/proj/scitex-web",
        "pypi_name": "scitex-web",
        "github_repo": "ywatanabe1989/scitex-web",
        "import_name": "scitex_web",
        "category": "library",
    },
}


__all__ = ["ECOSYSTEM", "PackageInfo"]


# EOF
