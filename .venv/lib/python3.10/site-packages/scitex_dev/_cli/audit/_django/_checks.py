"""Per-section rule checks for the Django "apps and config" auditor.

Split out of `_audit.py` to stay under the 512-line file hook (mirrors
the `_project/_check_*.py` split). Each `check_*` function takes the
`Violation` class and an `out` list, matching the `_project` auditor's
sidecar-check signature, so the engine in `_audit.py` stays thin.

Discovery helpers (`_import_name`, `resolve_repo_root`, `is_django_app`)
live here too — they mirror `_cli_audit_project`'s equivalents.
"""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _import_name(distribution: str) -> str:
    """Mirror sibling auditors: dist -> import name (`-` -> `_`)."""
    return distribution.replace("-", "_")


def resolve_repo_root(distribution: str, repo: Path | None) -> Path | None:
    """Return the repo root Path or None if it can't be located.

    Mirrors `_cli_audit_project._resolve_repo_root`: prefer an explicit
    `repo`, otherwise resolve the installed package and walk up to the
    `pyproject.toml`, with a `~/proj/<dist>` development fallback.
    """
    if repo is not None:
        return repo
    import importlib.util

    try:
        spec = importlib.util.find_spec(_import_name(distribution))
    except (ImportError, ValueError):
        spec = None
    if spec is not None and spec.submodule_search_locations:
        for loc in spec.submodule_search_locations:
            candidate = Path(loc).parent.parent
            if (candidate / "pyproject.toml").is_file():
                return candidate
            candidate = Path(loc).parent
            if (candidate / "pyproject.toml").is_file():
                return candidate

    proj_roots: list[Path] = []
    try:
        home_proj = Path.home() / "proj"
        if home_proj.is_dir():
            proj_roots.append(home_proj)
    except Exception:
        pass
    try:
        for home_dir in Path("/home").iterdir():
            p = home_dir / "proj"
            if p.is_dir() and p not in proj_roots:
                proj_roots.append(p)
    except Exception:
        pass
    for root in proj_roots:
        candidate = root / distribution
        if (candidate / "pyproject.toml").is_file():
            return candidate.resolve()

    return None


def is_django_app(repo: Path) -> bool:
    """Heuristic: a repo is a Django app iff `manage.py` is at the root.

    `manage.py` is the unambiguous marker — every Django project ships
    one, and no SciTeX library has one. We deliberately do NOT require
    `config/` here (its absence is the very thing DJ-101 reports), so a
    Django app that hasn't migrated yet (e.g. orochi with `orochi/`)
    still gets audited rather than silently skipped.
    """
    return (repo / "manage.py").is_file()


# ---------------------------------------------------------------------------
# Rule checks
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def check_config(repo: Path, violation_cls: type, out: list) -> None:
    """§1 — Django project in config/."""
    config = repo / "config"
    if not config.is_dir():
        out.append(
            violation_cls("DJ-101", str(repo), "no `config/` directory at repo root")
        )
        # The rest of §1 is meaningless without config/; report DJ-101
        # and the manage.py / legacy checks, then stop.
        check_manage_py(repo, violation_cls, out)
        check_legacy_project(repo, violation_cls, out)
        return

    settings = config / "settings"
    if settings.is_dir():
        if not (settings / "__init__.py").is_file():
            out.append(
                violation_cls(
                    "DJ-102",
                    str(settings),
                    "`config/settings/` exists but has no `__init__.py`",
                )
            )
        else:
            init_txt = _read_text(settings / "__init__.py")
            if "_ENV" not in init_txt and "import *" not in init_txt:
                out.append(
                    violation_cls(
                        "DJ-103",
                        str(settings / "__init__.py"),
                        "no SCITEX_<PKG>_ENV dispatch / `from .settings_<env> "
                        "import *` found",
                    )
                )
        if not (settings / "settings_shared.py").is_file():
            out.append(
                violation_cls(
                    "DJ-104",
                    str(settings),
                    "no `settings_shared.py` base module",
                )
            )
        missing_env = [
            f"settings_{e}.py"
            for e in ("dev", "prod")
            if not (settings / f"settings_{e}.py").is_file()
        ]
        if missing_env:
            out.append(
                violation_cls(
                    "DJ-105",
                    str(settings),
                    f"missing per-env settings module(s): {', '.join(missing_env)}",
                )
            )
    elif (config / "settings.py").is_file():
        out.append(
            violation_cls(
                "DJ-102",
                str(config / "settings.py"),
                "`config/settings.py` is a single module; ADR 0002 requires a "
                "`config/settings/` package",
            )
        )
    else:
        out.append(
            violation_cls(
                "DJ-102",
                str(config),
                "no `config/settings/` package (nor `config/settings.py`)",
            )
        )

    if not (config / "urls.py").is_file():
        out.append(
            violation_cls("DJ-106", str(config), "no `config/urls.py` root URLconf")
        )
    missing_server = [
        f"{n}.py" for n in ("asgi", "wsgi") if not (config / f"{n}.py").is_file()
    ]
    if missing_server:
        out.append(
            violation_cls(
                "DJ-107",
                str(config),
                f"missing server entry point(s): {', '.join(missing_server)}",
            )
        )

    check_manage_py(repo, violation_cls, out)
    check_legacy_project(repo, violation_cls, out)


def check_manage_py(repo: Path, violation_cls: type, out: list) -> None:
    """DJ-108 / DJ-109 — manage.py presence + settings default."""
    manage = repo / "manage.py"
    if not manage.is_file():
        out.append(violation_cls("DJ-108", str(repo), "no `manage.py` at repo root"))
        return
    txt = _read_text(manage)
    # Accept either an explicit "config.settings" default or the
    # SCITEX_<PKG>_DJANGO_SETTINGS_MODULE indirection that resolves to it.
    if "config.settings" not in txt:
        out.append(
            violation_cls(
                "DJ-109",
                str(manage),
                "manage.py does not reference `config.settings` as the "
                "DJANGO_SETTINGS_MODULE default",
            )
        )


def check_legacy_project(repo: Path, violation_cls: type, out: list) -> None:
    """DJ-110 — a legacy <projectname>/settings.py alongside config/."""
    config = repo / "config"
    for child in sorted(repo.iterdir()):
        if not child.is_dir():
            continue
        if child == config:
            continue
        name = child.name
        if name.startswith(".") or name in {"src", "apps", "tests", "node_modules"}:
            continue
        # A sibling dir that looks like a Django project package.
        if (child / "settings.py").is_file() and (
            (child / "wsgi.py").is_file() or (child / "asgi.py").is_file()
        ):
            out.append(
                violation_cls(
                    "DJ-110",
                    str(child),
                    f"`{name}/settings.py` looks like a Django project package "
                    "outside `config/`",
                )
            )


def check_apps(repo: Path, violation_cls: type, out: list) -> None:
    """§2 — apps under apps/."""
    apps = repo / "apps"
    if not apps.is_dir():
        out.append(
            violation_cls("DJ-201", str(repo), "no `apps/` directory at repo root")
        )
        return
    if not (apps / "__init__.py").is_file():
        out.append(
            violation_cls("DJ-202", str(apps), "`apps/` is missing `__init__.py`")
        )

    # Collect candidate app dirs: groups (infra/workspace) one level down,
    # plus any flat app dirs directly under apps/.
    app_dirs: list[Path] = []
    for group in ("infra", "workspace"):
        gpath = apps / group
        if gpath.is_dir():
            for item in sorted(gpath.iterdir()):
                if item.is_dir() and not item.name.startswith("_"):
                    app_dirs.append(item)
    for item in sorted(apps.iterdir()):
        if not item.is_dir() or item.name.startswith("_"):
            continue
        if item.name in {"infra", "workspace", "legacy", "__pycache__"}:
            continue
        app_dirs.append(item)

    # An app is a dir with an `apps.py` AppConfig — this mirrors hub's own
    # `discover_local_apps`, which only registers dirs that have `apps.py`.
    registered = [d for d in app_dirs if (d / "apps.py").is_file()]
    if not registered:
        out.append(
            violation_cls("DJ-203", str(apps), "no app directories found under `apps/`")
        )
        return

    # DJ-204: a dir that *intends* to be an app (has `__init__.py`) but has
    # no `apps.py` is broken. Dirs without `__init__.py` (e.g. leftover
    # `urls/`+`views/` stubs) are not registered apps — hub's discovery
    # skips them, so we don't flag them either.
    broken = [
        d.name
        for d in app_dirs
        if not (d / "apps.py").is_file() and (d / "__init__.py").is_file()
    ]
    if broken:
        sample = ", ".join(sorted(broken)[:8])
        if len(broken) > 8:
            sample += ", ..."
        out.append(
            violation_cls(
                "DJ-204",
                str(apps),
                f"{len(broken)} app package(s) with `__init__.py` but no "
                f"`apps.py`: {sample}",
            )
        )


def check_templates_static(repo: Path, violation_cls: type, out: list) -> None:
    """§3 — project templates / static."""
    if not (repo / "templates").is_dir():
        out.append(
            violation_cls(
                "DJ-301", str(repo), "no project-level `templates/` directory"
            )
        )
    if not (repo / "static").is_dir():
        out.append(
            violation_cls("DJ-302", str(repo), "no project-level `static/` directory")
        )


def check_pip_package(
    repo: Path, distribution: str, violation_cls: type, out: list
) -> None:
    """§4 — pip package <-> Django relationship."""
    pkg = _import_name(distribution)
    src_pkg = repo / "src" / pkg
    if not src_pkg.is_dir():
        out.append(
            violation_cls(
                "DJ-401",
                str(repo / "src"),
                f"no `src/{pkg}/` pip package",
            )
        )
        return
    # Django project must not be nested inside the wheel package.
    for nested in ("config", "apps"):
        nested_dir = src_pkg / nested
        if nested_dir.is_dir() and (nested_dir / "__init__.py").is_file():
            # only flag if it actually looks like the Django project
            if nested == "config" and (
                (nested_dir / "settings").is_dir()
                or (nested_dir / "settings.py").is_file()
            ):
                out.append(
                    violation_cls(
                        "DJ-402",
                        str(nested_dir),
                        f"Django `{nested}/` is nested inside the pip package",
                    )
                )


def _dep_names(reqs: list[str]) -> list[str]:
    """Extract lowercased distribution names from PEP-508 requirement strings."""
    names = []
    for r in reqs:
        token = (
            r.split(";")[0]
            .split("[")[0]
            .split("==")[0]
            .split(">=")[0]
            .split("<=")[0]
            .split("<")[0]
            .split(">")[0]
            .split("~=")[0]
            .strip()
            .lower()
        )
        if token:
            names.append(token)
    return names


def check_deps(repo: Path, violation_cls: type, out: list) -> None:
    """§5 — dependency declaration in pyproject.toml."""
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return  # DJ is layered on top of PS-101; don't double-report.
    try:
        import tomllib
    except ImportError:  # pragma: no cover — py<3.11
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            return
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return

    project = data.get("project", {})
    core_deps = project.get("dependencies", []) or []
    extras = project.get("optional-dependencies", {}) or {}

    all_dep_names = set(_dep_names(core_deps))
    for vals in extras.values():
        all_dep_names.update(_dep_names(vals))

    if "django" not in all_dep_names:
        out.append(
            violation_cls(
                "DJ-501",
                str(pyproject),
                "no `Django` dependency found in [project] dependencies or any "
                "optional-dependencies extra",
            )
        )

    # DJ-502: discourage a dedicated web sub-extra. Only flag if such an
    # extra carries Django (an empty/unrelated `[web]` is not our concern).
    for extra_name in ("django", "web"):
        vals = extras.get(extra_name)
        if vals and "django" in set(_dep_names(vals)):
            out.append(
                violation_cls(
                    "DJ-502",
                    str(pyproject),
                    f"web stack declared under a `[{extra_name}]` sub-extra; "
                    "fold it into `[all]` per ADR 0002 §5",
                )
            )


# Browser/E2E pytest flags that break headless CI when forced via addopts.
_E2E_ADDOPTS_FLAGS = ("--headed", "--browser", "--video", "--screenshot")


def _addopts_value(pytest_ini: dict) -> str:
    """Normalize a pytest `addopts` value (str or list) to one string."""
    addopts = pytest_ini.get("addopts", "")
    if isinstance(addopts, (list, tuple)):
        return " ".join(str(a) for a in addopts)
    return str(addopts)


def check_pytest_config(repo: Path, violation_cls: type, out: list) -> None:
    """§5 (release-gate hygiene) — global pytest addopts must stay CI-safe.

    The tag-release pipeline runs ``pytest tests/ -x``, which inherits
    global ``[tool.pytest.ini_options].addopts``. Forcing browser/E2E
    flags there breaks headless CI (DJ-503). Such tests belong behind an
    ``e2e`` marker.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return
    try:
        import tomllib
    except ImportError:  # pragma: no cover — py<3.11
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            return
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return

    pytest_ini = data.get("tool", {}).get("pytest", {}).get("ini_options", {}) or {}
    addopts = _addopts_value(pytest_ini)
    offenders = [flag for flag in _E2E_ADDOPTS_FLAGS if flag in addopts]
    if offenders:
        out.append(
            violation_cls(
                "DJ-503",
                str(pyproject),
                "global pytest addopts force browser/E2E flag(s): "
                + ", ".join(offenders)
                + " — gate these behind an `e2e` marker (release CI runs "
                "`pytest tests/ -x`)",
            )
        )
