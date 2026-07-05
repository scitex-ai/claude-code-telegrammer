"""Django "apps and config" auditor — engine + rules.

Checks a repo against ADR 0002 (scitex-django-app-standard), which
codifies `scitex-hub`'s layout as canonical:

* §1  Django project in `config/` (settings package + env-loader, urls,
      asgi/wsgi, manage.py at root pointing at `config.settings`).
* §2  Apps under `apps/` grouped into `apps/infra/` and `apps/workspace/`,
      each `<name>_app` with an `apps.py` AppConfig.
* §3  Project-level `templates/` and `static/`.
* §4  pip package `src/scitex_<name>/` sibling to the Django project
      (not nested either way).
* §5  Dependency declaration — the web stack lives in the canonical
      install extra (`[all]`), not proliferated sub-extras; `[dev]` for
      dev tooling.

Numbering: ``DJ<§><idx>`` (DJ = Django), e.g. DJ-101 = §1 rule 01.
Mirrors the ``PS<n>`` / ``PA<n>`` / ``SK<n>`` pattern of sibling auditors.

`scitex-hub` is the reference implementation and MUST pass by definition;
if a check fails on hub the check is wrong, not hub. Non-Django packages
are skipped cleanly (no `manage.py` at repo root ⇒ not a Django app).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click


@dataclass(frozen=True)
class Rule:
    code: str
    section: str
    message: str
    # Severity drives the audit's exit code:
    #   E (error)   — at least one E finding fails the audit (exit 1)
    #   W (warning) — printed but does not fail (exit 0 if no E findings)
    #   I (info)    — printed only with --severity info; never fails
    severity: str = "W"
    slug: str = ""


RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        # §1 Django project lives in config/ -------------------------------
        Rule(
            "DJ-101",
            "§1",
            (
                "Django app has no `config/` project package — per ADR 0002 "
                "the Django project lives in `config/` (settings/, urls.py, "
                "asgi.py, wsgi.py), not in `<projectname>/`."
            ),
            severity="E",
            slug="config-package-missing",
        ),
        Rule(
            "DJ-102",
            "§1",
            (
                "`config/settings/` is not a settings *package* — ADR 0002 "
                "requires a split settings package (settings_shared.py + one "
                "module per environment + an env-loader `__init__.py`), not a "
                "single monolithic settings.py."
            ),
            severity="E",
            slug="settings-not-a-package",
        ),
        Rule(
            "DJ-103",
            "§1",
            (
                "`config/settings/__init__.py` is not an environment "
                "auto-loader — ADR 0002 requires it to dispatch on "
                "`SCITEX_<PKG>_ENV` and `from .settings_<env> import *` for "
                "development / staging / prod."
            ),
            severity="W",
            slug="settings-init-not-env-loader",
        ),
        Rule(
            "DJ-104",
            "§1",
            (
                "`config/settings/settings_shared.py` is missing — ADR 0002 "
                "requires a shared base-settings module that the per-env "
                "modules import from."
            ),
            severity="E",
            slug="settings-shared-missing",
        ),
        Rule(
            "DJ-105",
            "§1",
            (
                "per-environment settings module(s) missing — ADR 0002 "
                "requires settings_dev.py and settings_prod.py (settings_"
                "staging.py recommended) under `config/settings/`."
            ),
            severity="W",
            slug="settings-env-modules-missing",
        ),
        Rule(
            "DJ-106",
            "§1",
            (
                "`config/urls.py` (root URLconf) is missing — ADR 0002 "
                "requires the root URLconf at `config/urls.py` "
                '(ROOT_URLCONF = "config.urls").'
            ),
            severity="E",
            slug="config-urls-missing",
        ),
        Rule(
            "DJ-107",
            "§1",
            (
                "`config/asgi.py` and/or `config/wsgi.py` missing — ADR 0002 "
                "requires both server entry points under `config/`."
            ),
            severity="W",
            slug="config-asgi-wsgi-missing",
        ),
        Rule(
            "DJ-108",
            "§1",
            (
                "`manage.py` is missing at the repo root — ADR 0002 keeps "
                "Django's manage.py at the repo root."
            ),
            severity="E",
            slug="manage-py-missing",
        ),
        Rule(
            "DJ-109",
            "§1",
            (
                "`manage.py` / asgi / wsgi do not default DJANGO_SETTINGS_"
                "MODULE to `config.settings` — ADR 0002 requires the "
                "settings module to resolve to `config.settings` (overridable "
                "via SCITEX_<PKG>_DJANGO_SETTINGS_MODULE)."
            ),
            severity="W",
            slug="settings-module-default",
        ),
        Rule(
            "DJ-110",
            "§1",
            (
                "a legacy `<projectname>/settings.py` Django project package "
                "still exists alongside `config/` — ADR 0002 forbids the "
                "project living under the package name; migrate it into "
                "`config/`."
            ),
            severity="W",
            slug="legacy-project-package",
        ),
        # §2 Apps under apps/ ---------------------------------------------
        Rule(
            "DJ-201",
            "§2",
            (
                "no top-level `apps/` package — ADR 0002 puts Django apps "
                "under `apps/` (grouped into `apps/infra/` and "
                "`apps/workspace/`)."
            ),
            severity="E",
            slug="apps-package-missing",
        ),
        Rule(
            "DJ-202",
            "§2",
            (
                "`apps/` is not a Python package (missing `apps/__init__.py`) "
                "— AppConfig names like `apps.workspace.<x>_app` require it."
            ),
            severity="W",
            slug="apps-not-a-package",
        ),
        Rule(
            "DJ-203",
            "§2",
            (
                "no app directories found under `apps/` — ADR 0002 expects "
                "at least one `<name>_app` (or `<name>_api`) directory with "
                "an `apps.py`."
            ),
            severity="W",
            slug="no-app-dirs",
        ),
        Rule(
            "DJ-204",
            "§2",
            (
                "an app directory under `apps/` has no `apps.py` AppConfig — "
                "ADR 0002 requires each app to declare an AppConfig whose "
                "`name` is the full dotted path."
            ),
            severity="W",
            slug="app-missing-appconfig",
        ),
        # §3 Project templates / static -----------------------------------
        Rule(
            "DJ-301",
            "§3",
            (
                "project-level `templates/` directory is missing — ADR 0002 "
                "puts global templates (base, 404, 500) at the repo root "
                "`templates/`."
            ),
            severity="W",
            slug="templates-dir-missing",
        ),
        Rule(
            "DJ-302",
            "§3",
            (
                "project-level `static/` directory is missing — ADR 0002 "
                "puts project static sources at the repo root `static/` "
                "(STATICFILES_DIRS), with collectstatic targeting "
                "`staticfiles/`."
            ),
            severity="W",
            slug="static-dir-missing",
        ),
        # §4 pip package <-> Django relationship --------------------------
        Rule(
            "DJ-401",
            "§4",
            (
                "pip package `src/scitex_<name>/` is missing — ADR 0002 keeps "
                "the standard SciTeX src-layout pip package (CLI/MCP/skills) "
                "as a sibling of the Django project."
            ),
            severity="E",
            slug="src-package-missing",
        ),
        Rule(
            "DJ-402",
            "§4",
            (
                "Django project is nested inside the pip package "
                "(`src/scitex_<name>/config` or `.../apps`) — ADR 0002 keeps "
                "`config/` and `apps/` as repo-root siblings of `src/`, never "
                "nested inside the wheel."
            ),
            severity="E",
            slug="django-nested-in-pip-package",
        ),
        # §5 Dependency declaration ---------------------------------------
        Rule(
            "DJ-501",
            "§5",
            (
                "Django is not declared as a dependency — ADR 0002 puts the "
                "web/runtime stack (Django + DRF + …) in the canonical "
                "`[all]` install extra (or core `dependencies`)."
            ),
            severity="E",
            slug="django-dep-undeclared",
        ),
        Rule(
            "DJ-502",
            "§5",
            (
                "proliferated web-stack sub-extra (`[django]`/`[web]`) — "
                "ADR 0002 flattens the web stack into the single user-facing "
                "`[all]` extra to avoid pip-resolver deadlocks from recursive "
                "sub-extra references. Use `[all]` (+ `[dev]` for tooling)."
            ),
            severity="W",
            slug="proliferated-web-subextra",
        ),
        Rule(
            "DJ-503",
            "§5",
            (
                "global pytest addopts force browser/E2E flag(s) "
                "(--headed/--browser/--video/--screenshot) — the tag-release "
                "pipeline runs `pytest tests/ -x`, which inherits global "
                "[tool.pytest.ini_options].addopts. These flags break headless "
                "CI. Keep addopts minimal (e.g. `-v --tb=short`) and gate "
                "browser/E2E tests behind an `e2e` marker."
            ),
            severity="E",
            slug="pytest-addopts-e2e-flags",
        ),
    ]
}


@dataclass
class Violation:
    rule: str
    where: str
    detail: str

    def format(self) -> str:
        r = RULES.get(self.rule)
        section = r.section if r else "?"
        sev = r.severity if r else "W"
        slug = f" {r.slug}" if r and r.slug else ""
        return f"  [{sev}] [{self.rule} {section}{slug}] {self.where}: {self.detail}"

    @property
    def severity(self) -> str:
        r = RULES.get(self.rule)
        return r.severity if r else "W"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def audit_django(
    distribution: str,
    *,
    repo: Path | None = None,
    json_out: bool = False,
    rules: set[str] | None = None,
    severity: str = "error",
) -> int:
    """Audit `<distribution>` against the Django "apps and config" standard.

    Parameters
    ----------
    distribution : str
        Distribution name (e.g. ``"scitex-hub"``).
    repo : Path, optional
        Repo root. Defaults to locating the installed package, with a
        ``~/proj/<dist>`` development fallback.
    json_out : bool
        Emit machine-readable output on stdout.
    rules : set of str, optional
        If given, only run these rule codes.
    severity : {"error","warning","info"}
        Minimum severity to print AND to drive the exit code. E findings
        fail (exit 1); W/I never fail on their own.

    Returns
    -------
    int
        0 = no E-level violations, 1 = ≥1 E violation,
        2 = repo could not be located.
    """
    from . import _checks

    repo_root = _checks.resolve_repo_root(distribution, repo)

    if repo_root is None:
        if json_out:
            import json as _json

            click.echo(
                _json.dumps(
                    {"distribution": distribution, "repo": None, "violations": []},
                    indent=2,
                )
            )
            return 2
        click.echo(
            f"audit-django: cannot locate repo root for '{distribution}' "
            "(is it installed in editable mode, or pass --repo PATH?)",
            err=True,
        )
        return 2

    # Category-aware skip — reuse the shared registry mechanism.
    try:
        from ...._ecosystem import should_skip_audit
    except ImportError:
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(distribution, "audit-django")
    if skip:
        if not json_out:
            from .._emit import emit as _emit_skip

            _emit_skip("skip", f"{distribution}: {reason}")
        return 0

    # Not a Django app ⇒ this auditor doesn't apply. Skip cleanly so
    # `audit-all` / `audit-django --all` don't fail on libraries.
    if not _checks.is_django_app(repo_root):
        if json_out:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "distribution": distribution,
                        "repo": str(repo_root),
                        "violations": [],
                        "skipped": "not-a-django-app",
                    },
                    indent=2,
                )
            )
            return 0
        from .._emit import emit as _emit_skip

        _emit_skip(
            "skip",
            f"{distribution}: not a Django app (no manage.py at repo root)",
        )
        return 0

    violations: list[Violation] = []
    _checks.check_config(repo_root, Violation, violations)
    _checks.check_apps(repo_root, Violation, violations)
    _checks.check_templates_static(repo_root, Violation, violations)
    _checks.check_pip_package(repo_root, distribution, Violation, violations)
    _checks.check_deps(repo_root, Violation, violations)
    _checks.check_pytest_config(repo_root, Violation, violations)

    if rules:
        violations = [v for v in violations if v.rule in rules]

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
                    "exit_code": exit_code,
                    "errors": n_errors,
                },
                indent=2,
            )
        )
        return exit_code

    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints
    from .._emit import emit as _emit

    if not visible:
        _emit("success", f"{distribution}: no Django-standard violations")
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
            if v.severity == "E"
            else ("warning" if v.severity == "W" else "info")
        )
        _emit(sev, v.format())
    emit_disclaimer()
    if exit_code:
        emit_skill_hints()
    return exit_code
