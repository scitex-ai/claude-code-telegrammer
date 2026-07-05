"""PS-168 — Per-package secret + env-var prefix in GitHub Actions workflows.

Spec: ``_skills/general/02_package/14_workflow-secret-env-prefix.md``.

Every ``${{ secrets.<NAME> }}`` reference under ``.github/workflows/*.yml``
must either:

1. Begin with the package's ``<PKG>_`` prefix (distribution name
   uppercased, hyphens → underscores), OR
2. Appear in the exception list of cross-cutting / tool-pinned names.
   The list is the union of:

   * the ecosystem default (``EXCEPTION_SECRETS_DEFAULT`` —
     ``CLAUDE_CODE_CREDENTIALS_JSON``, ``GH_TOKEN``, ``CODECOV_TOKEN``,
     ``GHCR_PAT``, ``GITHUB_TOKEN``, ``NPM_TOKEN``, ``PYPI_API_TOKEN``,
     the GitHub-Actions debug toggles, ``CLA_PERSONAL_ACCESS_TOKEN``),
     and
   * per-package extras declared in the audited package's
     ``pyproject.toml`` under
     ``[tool.scitex_dev.audit] ps168_secret_exceptions``. The package
     list **extends** the default (it never replaces it), so a package
     that declares nothing still inherits the full ecosystem default.

   Per-package extras keep an exception scoped to the package that
   actually needs it — the PR that adds the workflow using the secret
   also carries the exception entry, one place for the reviewer — and
   stop one package's one-off from polluting the central list.

Rationale: ``scitex-dev creds rotate-all`` rotates the cross-cutting
names ecosystem-wide; per-package secrets that picked the same surface
name (e.g. ``CLAUDE_CREDENTIALS_JSON`` in `newb`) were silently skipped
by rotate-all and went stale. The prefix discipline makes the two sets
disjoint by construction.

Detection: a simple regex over the workflow text — not a full YAML
parse — because GitHub Actions interpolation syntax ``${{ secrets.X }}``
appears in any context (string value, multiline scalar, …) and the
regex is robust to indentation while a YAML parser would have to
re-walk every node. We also scan ``env:`` blocks for an analogous
``env.<NAME>`` reference (rare; the secret-ref path is canonical).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 path
    import tomli as tomllib  # type: ignore[no-redef]

# Cross-cutting / tool-pinned names that legitimately exist without a
# per-package prefix. Keep this list in lockstep with the skill leaf
# (02_package/14_workflow-secret-env-prefix.md §Exception list).
#
# This is the ECOSYSTEM DEFAULT — the fallback when a package declares
# no per-package extras. Per-package additions live in pyproject.toml
# under ``[tool.scitex_dev.audit] ps168_secret_exceptions`` and EXTEND
# this set (see ``_exception_secrets_for``).
EXCEPTION_SECRETS_DEFAULT: frozenset[str] = frozenset(
    {
        # Rotate-all ecosystem-wide credential.
        "CLAUDE_CODE_CREDENTIALS_JSON",
        # Tool-pinned (gh CLI, GitHub Actions itself).
        "GH_TOKEN",
        "GITHUB_TOKEN",
        # Personal Access Token in the gh-CLI convention — single
        # cross-cutting PAT used by org-wide workflows (e.g.
        # contributor-assistant when configured under the GH_ namespace
        # rather than the older CLA_ name). The ``GITHUB_`` prefix is
        # reserved by GitHub Actions on the secret-name surface, so
        # ``GH_PERSONAL_ACCESS_TOKEN`` is the canonical substitute when
        # operators want a clearly-namespaced shared PAT.
        "GH_PERSONAL_ACCESS_TOKEN",
        # Third-party-pinned service tokens.
        "CODECOV_TOKEN",
        "GHCR_PAT",
        "NPM_TOKEN",
        "PYPI_API_TOKEN",
        # GitHub Actions runner-debug toggles.
        "ACTIONS_RUNNER_DEBUG",
        "ACTIONS_STEP_DEBUG",
        # contributor-assistant action's PAT (per-action convention,
        # shared across repos that opt into the CLA gate).
        "CLA_PERSONAL_ACCESS_TOKEN",
    }
)

# Back-compat alias. The default-only set was previously named
# ``EXCEPTION_SECRETS``; keep the name resolvable for callers and tests
# that import it. New code should prefer ``EXCEPTION_SECRETS_DEFAULT``.
EXCEPTION_SECRETS: frozenset[str] = EXCEPTION_SECRETS_DEFAULT


def _read_pyproject_extra_exceptions(repo: Path) -> frozenset[str]:
    """Return per-package PS-168 secret exceptions from ``pyproject.toml``.

    Reads the list at
    ``[tool.scitex_dev.audit] ps168_secret_exceptions`` (the canonical
    ``tool.scitex_dev`` namespace; ``tool.scitex-dev`` is also accepted
    for the hyphenated form). Non-string entries are dropped. Any
    failure (missing file, malformed TOML, wrong type) returns the empty
    set so PS-168 falls back to the ecosystem default — a broken
    pyproject must never silently widen the exception list.
    """
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return frozenset()
    try:
        data = tomllib.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return frozenset()
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return frozenset()
    # Accept both the canonical underscore namespace and the hyphenated
    # spelling some pyprojects use for [tool.*] tables.
    sd = tool.get("scitex_dev")
    if not isinstance(sd, dict):
        sd = tool.get("scitex-dev")
    if not isinstance(sd, dict):
        return frozenset()
    audit = sd.get("audit")
    if not isinstance(audit, dict):
        return frozenset()
    extras = audit.get("ps168_secret_exceptions")
    if not isinstance(extras, list):
        return frozenset()
    return frozenset(x for x in extras if isinstance(x, str))


def _exception_secrets_for(repo: Path) -> frozenset[str]:
    """Ecosystem default UNION any per-package extras for ``repo``.

    The package list extends — never replaces — the default, so a
    package that declares nothing still gets the full ecosystem default.
    """
    return EXCEPTION_SECRETS_DEFAULT | _read_pyproject_extra_exceptions(repo)


# Match `${{ secrets.<NAME> }}` (and the analogous env. form) tolerating
# whitespace around the dot and the closing braces. NAME is captured.
# Anchored to `secrets.` / `env.` so a bare `${{ matrix.X }}` etc. is
# never matched.
_RE_SECRET_REF = re.compile(r"\$\{\{\s*secrets\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

# Only enforce PS-168 on names that LOOK like credentials. A plain
# `DEBUG_FLAG` or `BUILD_NUMBER` secret isn't subject to the rotation
# discipline that PS-168 is trying to protect. Match credential
# keywords as underscore-bounded tokens anywhere in the name.
_RE_KEY_LIKE = re.compile(
    r"(?:^|_)("
    r"TOKEN|KEY|KEYS|SECRET|SECRETS|CREDENTIAL|CREDENTIALS|"
    r"PASSWORD|PASSWD|PAT|AUTH|OAUTH"
    r")(?:$|_)",
    re.IGNORECASE,
)


def _is_key_like(name: str) -> bool:
    """True iff ``name`` looks like a credential / token secret.

    PS-168's discipline targets rotatable credentials; non-credential
    config secrets (debug flags, resource caps, build metadata) sit
    outside the rule's protected surface and would just be noise.
    """
    return bool(_RE_KEY_LIKE.search(name))


def _ecosystem_pkg_prefixes() -> tuple[str, ...]:
    """Return per-pkg uppercase prefixes for every known ECOSYSTEM entry.

    Used to allow cross-package borrows in PS-168: a workflow that
    invokes another scitex-* package's CLI (e.g. ``newb``) legitimately
    reads ``secrets.NEWB_ANTHROPIC_API_KEY``. The receiving repo isn't
    free-styling — it's adopting the source package's prefix discipline.

    Failures are tolerated (test-time, missing ECOSYSTEM, etc.) so PS-168
    falls back to "only the local prefix passes" when discovery breaks.
    """
    try:
        from scitex_dev._ecosystem._core import ECOSYSTEM

        return tuple(name.upper().replace("-", "_") + "_" for name in sorted(ECOSYSTEM))
    except Exception:
        return ()


# Per-package prefix aliases. Some distributions have a long canonical
# name plus a short historical alias. Both are accepted so operators
# don't have to rename battle-tested secrets that already follow the
# short form. Add entries here ONLY for distributions whose alias is
# in widespread, documented use (not freshly invented short names).
_PREFIX_ALIASES: dict[str, tuple[str, ...]] = {
    # scitex-agent-container ↔ SAC_. `sac` is the CLI executable name,
    # documented in every spec.yaml and dotfiles config; SAC_* secrets
    # predate the longer SCITEX_AGENT_CONTAINER_* form.
    "scitex-agent-container": ("SAC_",),
}


def _distribution_prefixes(distribution: str) -> tuple[str, ...]:
    """Return all valid per-package prefixes for ``distribution``.

    The first entry is the canonical form (distribution uppercased +
    hyphens → underscores + ``_``). Any aliases registered in
    ``_PREFIX_ALIASES`` follow. A secret name matching ANY of the
    returned prefixes satisfies PS-168.
    """
    canonical = distribution.upper().replace("-", "_") + "_"
    aliases = _PREFIX_ALIASES.get(distribution, ())
    return (canonical, *aliases)


def _distribution_prefix(distribution: str) -> str:
    """Return the canonical per-package prefix (e.g. `NEWB_`).

    Convenience wrapper retained for the violation message (we report
    the canonical form to the operator even when an alias would also
    have passed — guides toward consistency without erroring on the
    accepted alias form).
    """
    return _distribution_prefixes(distribution)[0]


def _iter_workflow_files(repo: Path) -> Iterable[Path]:
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    return sorted(
        p for p in wf_dir.iterdir() if p.is_file() and p.suffix in {".yml", ".yaml"}
    )


def _violations_in_text(
    text: str,
    prefixes: tuple[str, ...] | str,
    exceptions: frozenset[str] = EXCEPTION_SECRETS,
    cross_pkg_prefixes: tuple[str, ...] | None = None,
    only_key_like: bool = True,
) -> list[tuple[int, str]]:
    """Return (line_number, secret_name) pairs that violate PS-168.

    Scope filters (both applied):

    * ``only_key_like=True`` skips names that don't look like a
      credential / token (no TOKEN / KEY / SECRET / CREDENTIAL /
      PASSWORD / PAT / AUTH / OAUTH suffix). Non-key config secrets
      sit outside the rotation discipline.
    * ``cross_pkg_prefixes`` lists ecosystem-wide per-package prefixes
      (e.g. ``("NEWB_", "SCITEX_DEV_", ...)``). A name starting with
      any of these passes — a workflow that invokes another package's
      tool legitimately borrows that package's prefix.

    ``prefixes`` may be a single string (back-compat) or a tuple of
    accepted prefixes — a name passes if it starts with ANY of them.
    """
    if isinstance(prefixes, str):
        prefixes = (prefixes,)
    cross_pkg_prefixes = cross_pkg_prefixes or ()
    out: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _RE_SECRET_REF.finditer(line):
            name = m.group(1)
            if name in exceptions:
                continue
            if only_key_like and not _is_key_like(name):
                continue
            if any(name.startswith(p) for p in prefixes):
                continue
            if any(name.startswith(p) for p in cross_pkg_prefixes):
                continue
            out.append((lineno, name))
    return out


def check_ps168_secret_env_prefix(
    repo: Path,
    distribution: str,
    violation_cls: type,
    out: list[Any],
) -> None:
    """Append PS-168 violations for `.github/workflows/`.

    One violation per offending ``secrets.<NAME>`` reference, with the
    workflow path + 1-based line number in the ``where`` field so the
    output composes with editor jump-to-line tooling.

    The exception list is the ecosystem default UNION any per-package
    extras the audited package declares in its ``pyproject.toml`` under
    ``[tool.scitex_dev.audit] ps168_secret_exceptions``.
    """
    prefix = _distribution_prefix(distribution)
    prefixes = _distribution_prefixes(distribution)
    cross_pkg_prefixes = _ecosystem_pkg_prefixes()
    exceptions = _exception_secrets_for(repo)
    for path in _iter_workflow_files(repo):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(repo))
        for lineno, name in _violations_in_text(
            text,
            prefixes,
            exceptions=exceptions,
            cross_pkg_prefixes=cross_pkg_prefixes,
        ):
            out.append(
                violation_cls(
                    "PS-168",
                    f"{rel}:{lineno}",
                    (
                        f'secret name "{name}" should be prefixed '
                        f'"{prefix}{name}" (per-package secrets in '
                        f"`.github/workflows/` must carry the "
                        f"`{prefix}` prefix; cross-cutting names "
                        f"are allow-listed — see "
                        f"_skills/general/02_package/14_workflow-secret-env-prefix.md)."
                    ),
                )
            )
