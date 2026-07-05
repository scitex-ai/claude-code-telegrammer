"""Project-structure auditor — engine + rules.

Rules cover the automatable items from
`scitex-dev/src/scitex_dev/_skills/general/02_package/01_project-structure-root.md`
(and its sibling `scientific/02_research-project_01_project-structure.md`).

Numbering: ``PS<§><idx>`` (PS = Project Structure), e.g. PS-201 = §2 rule 01.
Mirrors the ``PA<n>`` / ``SK<n>`` / ``M<n>`` pattern of sibling auditors.

This file is the public-API facade for the project-structure auditor.
Implementation was split across sibling modules (issue #103) — pure
refactor, zero behaviour change. Imports below preserve the original
public surface so consumers reading via
``from scitex_dev._cli.audit._project._audit import X`` keep working.
"""

from __future__ import annotations

from pathlib import Path

import click

# Re-exported symbols so internal callers and external tests that read
# `from scitex_dev._cli.audit._project._audit import X` keep working
# after the split.
from ._checks import (
    _check_docs_structure,
    _check_empty_test_dirs,
    _check_loose_top_level_tests,
    _check_mirror,
    _check_placeholder_tests,
    _check_tests_subdir_convention,
    _check_top_level,
    _suggest_test_location,
    _test_has_src_match,
    check_codecov_target,
)
from ._constants import (
    _FORBIDDEN_TOP_DIRS,
    _JUNK_FILE_RE,
    _KNOWN_TEST_SUBDIRS,
    _META_TESTS_AT_ROOT,
    _MIRROR_EXEMPT_CATEGORIES,
    _PRIVATE_TEST_RE,
    _PUBLIC_TEST_RE,
    _WALK_BLACKLIST_RE,
    _is_blacklisted,
)
from ._discovery import (
    _has_py,
    _import_name,
    _is_git_ignored,
    _resolve_repo_root,
    _src_pkg_dir,
    _tests_root,
)
from ._registry import RULES, Rule
from ._violation import Violation

__all__ = [
    "RULES",
    "Rule",
    "Violation",
    "audit_project",
    "check_codecov_target",
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def audit_project(
    distribution: str,
    *,
    repo: Path | None = None,
    json_out: bool = False,
    rules: set[str] | None = None,
    severity: str = "error",
) -> int:
    """Audit `<distribution>` against the project-structure checklist.

    Parameters
    ----------
    distribution : str
        Distribution name (e.g. ``"scitex-io"``).
    repo : Path, optional
        Repo root. Defaults to the result of locating the installed package.
    json_out : bool
        Emit machine-readable output on stdout.
    rules : set of str, optional
        If given, only run these rule codes.
    severity : {"error","warning","info"}
        Minimum severity to print AND to drive the exit code.
        - ``"error"``  (default): print E findings only; exit 1 iff ≥1 E.
        - ``"warning"``: print E + W findings; exit 1 iff ≥1 E.
        - ``"info"``: print everything; exit 1 iff ≥1 E.
        W and I findings never fail CI on their own.

    Returns
    -------
    int
        Exit code: 0 = no E-level violations, 1 = ≥1 E violation, 2 = could not locate.
    """
    repo_root = _resolve_repo_root(distribution, repo)
    violations: list[Violation] = []

    if repo_root is None:
        if json_out:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "distribution": distribution,
                        "repo": None,
                        "violations": [],
                    },
                    indent=2,
                )
            )
            return 2
        click.echo(
            f"audit-project: cannot locate repo root for '{distribution}' "
            "(is it installed in editable mode, or pass --repo PATH?)",
            err=True,
        )
        return 2

    # Category-aware skip — see `should_skip_audit` in _ecosystem._core.
    try:
        from ...._ecosystem import ECOSYSTEM, should_skip_audit
    except ImportError:
        ECOSYSTEM = {}
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(distribution, "audit-project")
    if skip:
        if not json_out:
            from .._emit import emit as _emit_skip

            _emit_skip("skip", f"{distribution}: {reason}")
        return 0
    info = ECOSYSTEM.get(distribution, {})
    category = info.get("category", "library")
    skip_mirror = category in _MIRROR_EXEMPT_CATEGORIES

    _check_top_level(repo_root, violations)
    if not skip_mirror:
        _check_mirror(repo_root, distribution, violations)
        _check_placeholder_tests(repo_root, violations)
        _check_empty_test_dirs(repo_root, distribution, violations)
    _check_tests_subdir_convention(repo_root, distribution, violations)
    # hook-bypass: line-limit
    # RP-2xx: research projects mirror scripts/ ↔ tests/scripts/ instead of
    # src/<pkg>/ ↔ tests/<pkg>/. Fired only when `research` is in the
    # project-types; the PS package-publish rules drop for pure-research
    # (no `pip` ⇒ applies("PS-*") is False). See _check_research_mirror.
    from .._config import load_config as _load_cfg_for_research

    if "research" in _load_cfg_for_research(repo_root).project_types:
        from ._check_research_mirror import check_research_mirror

        check_research_mirror(repo_root, violations)
    _check_docs_structure(repo_root, violations)
    src_pkg = _src_pkg_dir(repo_root, distribution)
    if src_pkg is not None:
        from ._check_flat_layout import check_flat_layout, check_topical_clutter

        check_flat_layout(src_pkg, Violation, violations)
        check_topical_clutter(src_pkg, Violation, violations)
    from ._check_readme_badges import check_coverage_badge

    check_coverage_badge(repo_root, Violation, violations)
    from ._check_readme_badge_position import check_badge_position

    check_badge_position(repo_root, Violation, violations)
    from ._check_readme_sections import check_readme_sections

    check_readme_sections(repo_root, Violation, violations)
    from ._check_sphinx_html import check_sphinx_html

    check_sphinx_html(repo_root, Violation, violations)
    from ._check_env_example import check_env_example

    check_env_example(repo_root, Violation, violations)
    from ._check_examples import check_examples_conventions

    check_examples_conventions(repo_root, Violation, violations)
    from ._check_readme_structure import check_readme_structure

    check_readme_structure(repo_root, Violation, violations)
    check_codecov_target(repo_root, Violation, violations)
    from ._check_dev_extras_complete import check_dev_extras_complete

    check_dev_extras_complete(repo_root, Violation, violations)
    # hook-bypass: line-limit
    from ._check_optional_deps_guarded import check_ps148_optional_deps_guarded

    check_ps148_optional_deps_guarded(repo_root, distribution, Violation, violations)
    # hook-bypass: line-limit
    from ._check_console_script_core_deps import (
        check_ps213_console_script_core_deps,
    )

    check_ps213_console_script_core_deps(repo_root, distribution, Violation, violations)
    # hook-bypass: line-limit
    from ._check_hard_dep_overreach import check_ps149_hard_dep_overreach

    check_ps149_hard_dep_overreach(repo_root, distribution, Violation, violations)
    from ._check_umbrella_dep_and_integration import (
        check_ps139_umbrella_dep,
        check_ps140_integration_gate,
    )

    check_ps139_umbrella_dep(repo_root, Violation, violations)
    check_ps140_integration_gate(repo_root, distribution, Violation, violations)
    from ._check_audit_pin import check_audit_pin

    check_audit_pin(repo_root, Violation, violations)
    from ._check_workflows_naming import check_ps164_workflow_naming

    check_ps164_workflow_naming(repo_root, Violation, violations)
    # hook-bypass: line-limit
    from ._check_secret_env_prefix import check_ps168_secret_env_prefix

    check_ps168_secret_env_prefix(repo_root, distribution, Violation, violations)
    # hook-bypass: line-limit
    from ._check_workflow_presence import check_ps165_workflow_presence
    from ._check_readme_badge_labels import check_ps166_readme_badge_labels

    check_ps165_workflow_presence(repo_root, Violation, violations)
    check_ps166_readme_badge_labels(repo_root, Violation, violations)
    from ._check_readme_badge_layout import (  # hook-bypass: line-limit
        check_ps167_readme_badge_layout,
    )

    check_ps167_readme_badge_layout(repo_root, Violation, violations)
    from ._check_local_state import (
        check_ps145_cross_package_read,
        check_ps146_pip_install_side_effect,
        check_ps147_eval_form_completion,
    )

    check_ps145_cross_package_read(repo_root, distribution, Violation, violations)
    check_ps146_pip_install_side_effect(repo_root, Violation, violations)
    check_ps147_eval_form_completion(repo_root, Violation, violations)
    # PS-PATH / PS-CLEW / PS-AGENT — paper-scitex-clew MVP lint set.
    # Artifact-gated (only fire when PATH.yaml / clew.add_claim /
    # scripts/agent/ are present); safe to run on every project type.
    # See PR #97 and operator directive 2026-06-01.
    from ._check_path_yaml import (  # hook-bypass: line-limit
        check_ps_path_001_outer_wrapper,
        check_ps_path_002_bare_string_leaf,
    )
    from ._check_clew_claims import (  # hook-bypass: line-limit
        check_ps_agent_001_agent_script_no_claims_json,
        check_ps_clew_001_add_claim_without_self_verify,
    )

    check_ps_path_001_outer_wrapper(repo_root, Violation, violations)
    check_ps_path_002_bare_string_leaf(repo_root, Violation, violations)
    check_ps_clew_001_add_claim_without_self_verify(repo_root, Violation, violations)
    check_ps_agent_001_agent_script_no_claims_json(repo_root, Violation, violations)
    # hook-bypass: line-limit
    # PS-173: ADR format — only fires when docs/adr/ exists (presence is
    # recommended, not mandated). Scope = all project kinds.
    from ._check_adr import check_ps173_adr_format

    check_ps173_adr_format(repo_root, violations)
    # PS-180: runtime/ separation discipline — only fires when
    # src/<pkg>/runtime/ exists on disk AND no .gitignore covers it.
    # Scope = all project kinds with a src/ layout.
    from ._check_runtime_separation import check_runtime_separation

    check_runtime_separation(repo_root, Violation, violations)
    if not skip_mirror:
        from ._check_smoke_e2e_layers import (
            check_ps211_smoke_layer,
            check_ps212_e2e_layer,
        )

        check_ps211_smoke_layer(repo_root, Violation, violations)
        check_ps212_e2e_layer(repo_root, Violation, violations)

    if rules:
        violations = [v for v in violations if v.rule in rules]

    # Project-type dispatch: drop findings for rule families that don't
    # apply to this project (PS rules only fire for `pip` projects, RP
    # rules only for `research`). Honours the user's `audit.skip` list too.
    from .._config import load_config

    cfg = load_config(repo_root)
    # Track findings that the project-type filter would have dropped —
    # specifically PS-103 violations on `deferred`-type projects. The
    # auditor doesn't fire them (deferred opts out) but we surface a
    # one-line warning so the operator has a visible TODO list when
    # revisiting cleanup.
    deferred_dropped: list[Violation] = (
        [v for v in violations if v.rule == "PS-103"]
        if "deferred" in cfg.project_types
        else []
    )

    # Leaf-side package-type CAPABILITY knob (operator directive 2026-06-22):
    # a declared `audit.capabilities` entry (e.g. `no-umbrella`) skips the
    # rules that do not fit the package TYPE — with a VISIBLE
    # "skipped (declared capability: X)" notice, NOT a silent pass and NOT a
    # blanket `audit.skip`. Each capability gates a FIXED rule set
    # (CAPABILITY_RULES), so this can never silence an unrelated rule. We
    # compute the skip BEFORE the project-type/skip filter so the notice
    # reflects exactly what the capability dropped.
    from .._config import capability_for_rule

    capability_skipped: list[tuple[str, str]] = []  # (rule, capability)
    if cfg.capabilities:
        kept: list[Violation] = []
        seen: set[tuple[str, str]] = set()
        for v in violations:
            cap = capability_for_rule(v.rule)
            if cap is not None and cfg.has_capability(cap):
                key = (v.rule, cap)
                if key not in seen:
                    seen.add(key)
                    capability_skipped.append(key)
                continue
            kept.append(v)
        violations = kept

    violations = [
        v for v in violations if cfg.applies(v.rule) and v.rule not in cfg.skip
    ]

    # Severity filtering: print everything ≥ the requested floor.
    _floor = {"error": {"E"}, "warning": {"E", "W"}, "info": {"E", "W", "I"}}
    visible_set = _floor.get(severity, _floor["error"])
    visible = [v for v in violations if v.severity in visible_set]
    n_errors = sum(1 for v in violations if v.severity == "E")
    exit_code = 1 if n_errors > 0 else 0

    if json_out:
        import json as _json

        click.echo(
            _json.dumps(
                {
                    "distribution": distribution,
                    "repo": str(repo_root),
                    "violations": [
                        {
                            "rule": v.rule,
                            "where": v.where,
                            "detail": v.detail,
                            "severity": v.severity,
                        }
                        for v in visible
                    ],
                    "capability_skips": [
                        {"rule": rule, "capability": cap}
                        for rule, cap in capability_skipped
                    ],
                    "exit_code": exit_code,
                    "errors": n_errors,
                },
                indent=2,
            )
        )
        return exit_code

    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

    def _emit_deferred_reminder() -> None:
        if not deferred_dropped:
            return
        click.echo(
            f"  [defer] {distribution}: {len(deferred_dropped)} PS-103 "
            f"finding(s) suppressed by `project-type: deferred`. "
            f"Re-review when time permits — entries currently at root "
            f"that the strict baseline would flag:",
            err=True,
        )
        for v in deferred_dropped[:10]:
            basename = Path(v.where).name
            click.echo(f"    - {basename}", err=True)
        if len(deferred_dropped) > 10:
            click.echo(
                f"    … +{len(deferred_dropped) - 10} more (run with "
                f"`--severity warning` against a non-deferred config to see all)",
                err=True,
            )

    from .._emit import emit as _emit

    def _emit_capability_skips() -> None:
        # Route via click.echo(err=True) — NOT _emit("info", ...) — so the
        # notice is ALWAYS visible: the audit logger's default level is
        # WARNING, which would swallow an info/skip headline. The operator
        # requires this skip to be visible, not silent. Mirrors the
        # always-printed `_emit_deferred_reminder` precedent.
        for rule, cap in capability_skipped:
            click.echo(
                f"  [capability] {distribution}: {rule} skipped "
                f"(declared capability: {cap})",
                err=True,
            )

    if not visible:
        # No findings at the requested severity floor.
        _emit("success", f"{distribution}: no project-structure violations")
        _emit_capability_skips()
        _emit_deferred_reminder()
        emit_disclaimer()
        return exit_code

    n_w = sum(1 for v in visible if v.severity == "W")
    n_i = sum(1 for v in visible if v.severity == "I")
    headline_level = "error" if exit_code else "warning"
    summary = f"{distribution} ({repo_root}): {n_errors} error(s)"
    if n_w:
        summary += f", {n_w} warning(s)"
    if n_i:
        summary += f", {n_i} info"
    _emit(headline_level, summary)
    for v in visible:
        sev = (
            "error"
            if getattr(v, "severity", "W") == "E"
            else ("warning" if getattr(v, "severity", "W") == "W" else "info")
        )
        _emit(sev, v.format())
    _emit_capability_skips()
    _emit_deferred_reminder()
    emit_disclaimer()
    emit_skill_hints()
    return exit_code
