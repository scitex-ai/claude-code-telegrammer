"""Static auditor for SciTeX Python APIs — thin orchestrator.

Rules cover the `(A)`-marked items from
`scitex-python/src/scitex/_skills/general/03_interface/01_python-api/12_audit-checklist.md`.

Numbering: `PA<§><idx>` (e.g. PA-101 = §1 rule 01). Mirrors the `S<n>` / `M<n>`
rule-numbering used elsewhere in scitex-dev.

This module is the engine: it owns `audit_api`. The rule registry
(`Rule`/`RULES`), the `Violation` dataclass, and the per-section rule checks
live in the `_checks/` subpackage (split out to stay under the 512-line file
hook — mirrors `_project/_check_*.py` issue #103 and `_django/_checks.py`).
Every public name from that subpackage is re-exported below so existing
imports — `from ..._audit import audit_api, _locate_init, _audit_init,
_audit_no_mocks, _audit_playwright_capture, RULES, Violation` — keep
resolving unchanged.
"""

from __future__ import annotations

import importlib.metadata as im
from pathlib import Path

import click

from .._emit import emit as _emit

# Re-export the rule registry, Violation dataclass, shared constants, and every
# per-section check from the `_checks/` subpackage so all historical import
# paths through `_audit` keep working (pure refactor — no behaviour change).
from ._checks import (  # noqa: F401
    RULES,
    Rule,
    Violation,
    _audit_init,
    _audit_no_mocks,
    _audit_playwright_capture,
    _audit_test_quality,
    _audit_umbrella_imports,
    _import_name,
    _inspect_version_pattern,
    _locate_init,
    _MOCK_FIXTURE_PARAMS_AUDIT,
    _MOCK_MODULES_AUDIT,
    _MOCK_SYMBOLS_AUDIT,
    _STDLIB_SAFE_ROOTS,
    _THIRD_PARTY_ROOTS,
    _type_checking_import_node_ids,
)

__all__ = ["audit_api", "Violation", "RULES", "Rule"]


def audit_api(
    distribution: str,
    *,
    json_out: bool = False,
    rules: set[str] | None = None,
    repo_root: Path | None = None,
) -> int:
    """Audit `<distribution>` against the Python API checklist. Warn-only.

    Parameters
    ----------
    distribution : str
        Distribution name (e.g. ``"scitex-io"``).
    json_out : bool
        Emit machine-readable output on stdout.
    rules : set of str, optional
        If given, only run these rule codes.
    repo_root : Path, optional
        Repository root used to load ``.scitex/dev/config.yaml``. When given,
        the project's ``audit.skip`` list defers the named PA rules — they are
        dropped from the violation set entirely, mirroring ``audit-project`` —
        and a ``django`` project-type relaxes the no-mocks rule (PA-306) from
        error to warning. When ``None`` the legacy behaviour is preserved
        (every rule applies at its declared severity).

    Returns
    -------
    int
        Exit code: 0 = no violations, 1 = violations, 2 = could not import.
    """
    # Category-aware skip — see `should_skip_audit` in _ecosystem._core.
    try:
        from ...._ecosystem import should_skip_audit
    except ImportError:
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(distribution, "audit-python-apis")
    if skip:
        if json_out:
            import json

            click.echo(
                json.dumps(
                    {
                        "distribution": distribution,
                        "init": None,
                        "skipped": reason,
                        "violations": [],
                    },
                    indent=2,
                )
            )
        else:
            _emit("skip", f"{distribution}: {reason}")
        return 0

    import_name = _import_name(distribution)
    init_path = _locate_init(distribution, import_name)
    if init_path is None:
        # Skipped, not failed: many packages run audit-all from CI before
        # `pip install -e .` (e.g. when scitex_dev is the only install).
        # Treat absence as "no API surface to check" rather than an error.
        _emit(
            "info",
            f"{distribution}: cannot locate __init__.py for "
            f"'{import_name}' — package not importable, skipped.",
            err=True,
        )
        return 0

    # Probe distribution metadata to surface missing-install issues early.
    try:
        im.version(distribution)
    except im.PackageNotFoundError:
        _emit(
            "warning",
            f"audit-api: distribution metadata for '{distribution}' "
            "not found (continuing with source-only checks)",
            err=True,
        )

    violations = _audit_init(init_path, distribution)
    violations.extend(_audit_umbrella_imports(init_path, distribution, import_name))
    violations.extend(_audit_playwright_capture(init_path, distribution, import_name))
    violations.extend(_audit_no_mocks(init_path, distribution, import_name))
    violations.extend(_audit_test_quality(init_path, distribution, import_name))
    if rules:
        violations = [v for v in violations if v.rule in rules]

    # repo_root may be None when the registry's dev-box local_path is absent
    # (notably on CI runners). Derive it from the authoritatively-resolved
    # init_path so the package's deferral config loads on CI exactly as on a dev
    # box; otherwise deferred rules silently re-fire as false positives. Only
    # acts when repo_root was not supplied; never overrides an explicit root.
    if repo_root is None:
        _src_pkg = init_path.parent  # <repo>/src/<pkg>/
        _src = _src_pkg.parent  # <repo>/src/  (or <repo>/ flat)
        _derived = _src.parent if _src.name == "src" else _src
        if (_derived / "pyproject.toml").is_file():
            repo_root = _derived
        else:
            # Fail loud (no silent fallback): repo root unresolved -> deferral
            # config will NOT apply. Surface it rather than silently emitting
            # deferred rules as violations.
            _emit(
                "warning",
                f"audit-api: could not resolve repo root for '{distribution}' "
                f"from {init_path} (no pyproject.toml at {_derived}); deferral "
                f"config NOT applied — violations may include deferred rules.",
                err=True,
            )

    # Per-project rule scoping — mirror ``audit-project``. A repo can defer
    # specific PA rules via ``.scitex/dev/config.yaml`` ``audit.skip`` (with a
    # documented reason in ``audit.reasons``), and a ``django`` project-type
    # relaxes the no-mocks rule to a warning. Deferred rules are dropped from
    # the violation set entirely (not merely downgraded) so they no longer
    # drive the error-level exit code that ``audit-all`` gates on.
    downgraded: set[str] = set()
    if repo_root is not None:
        from .._config import load_config

        cfg = load_config(repo_root)
        if "deferred" in cfg.project_types:
            # `deferred` = "I know this is messy; remind me later." Mirror the
            # project auditor: opt out of all rules for this run.
            violations = []
        else:
            violations = [
                v for v in violations if cfg.applies(v.rule) and v.rule not in cfg.skip
            ]
            # Django apps legitimately use test doubles for external services
            # (HTTP, browser, telegram, ssh); the no-mocks rule (PA-306) is
            # wrong-by-default for them, so a ``django`` project-type drops it
            # to a warning. PA-307 (test-quality) still applies at full
            # severity. Explicit and documented, not a silent exception.
            if "django" in cfg.project_types:
                downgraded.add("PA-306")

    if json_out:
        import json

        click.echo(
            json.dumps(
                {
                    "distribution": distribution,
                    "init": str(init_path),
                    "violations": [
                        {"rule": v.rule, "where": v.where, "detail": v.detail}
                        for v in violations
                    ],
                },
                indent=2,
            )
        )
        return 0 if not violations else 1

    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

    if not violations:
        _emit("success", f"{distribution}: no Python API violations")
        emit_disclaimer()
        return 0

    # Compute the highest severity across all fired rules. The headline
    # ("error" vs "warning") and exit code track that — so packages
    # that break error-severity rules (NM/TQ) fail CI gates, while
    # warning-only violations don't. A rule relaxed for this run (e.g.
    # PA-306 under a `django` project-type) reports at warning level so it
    # no longer drives the error exit code or the error headline.
    def _effective_severity(rule: str) -> str:
        if rule in downgraded:
            return "warning"
        return getattr(RULES.get(rule), "severity", "warning")

    has_error = any(_effective_severity(v.rule) == "error" for v in violations)
    headline_level = "error" if has_error else "warning"
    _emit(headline_level, f"{distribution}: {len(violations)} violation(s)")
    # Per-violation lines use the rule's effective severity so a mixed run
    # shows each rule at its actual level (warnings for PA-301, errors for
    # PA-307, and PA-306 as a warning when django-relaxed).
    for v in violations:
        sev = _effective_severity(v.rule)
        line = v.format()
        _emit(sev, line)
    emit_disclaimer()
    emit_skill_hints()
    return 2 if has_error else 1
