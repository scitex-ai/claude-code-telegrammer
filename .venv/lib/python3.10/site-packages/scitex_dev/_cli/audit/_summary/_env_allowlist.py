"""§6a per-package env-var allowlist — pyproject opt-out.

Some packages legitimately ship operator-facing env vars that pre-date
the SciTeX ecosystem (acronym brands, integrations with external
operator tooling) and cannot be renamed to ``SCITEX_<PKG>_*`` without
breaking every running deployment. Such packages declare the prefix
in their own ``pyproject.toml``::

    [tool.scitex_dev]
    env_allowlist = ["SAC_"]

Mirror of :func:`scitex_dev._cli.audit._summary._mcp_parity.is_mcp_parity_exempt`
— same ``[tool.scitex_dev]`` namespace, same checked-out-tree
resolution (registry ``local_path`` when present, else walk up from
the import location). The matching helper lives in its own file
because ``_audit.py`` is already at 2139 LoC; growing it further is
deferred to a separate refactor PR.

Use sparingly: each entry shrinks the audit surface for the package,
so the brand-prefix justification must be real (e.g. operator-facing
shell exports / hooks / dotfiles / agent specs that predate the
SciTeX adoption), not a catch-all noise silencer for new code that
could have been written with the canonical ``SCITEX_<PKG>_*`` prefix.

Semantics
---------
Entries apply "equal-to-stripped or prefix-match" — identical shape to
the universal allowlist in ``_audit._ALLOWED_ENV_PREFIXES`` so callers
don't have to remember which list a prefix lives in. Examples::

    env_allowlist = ["SAC_"]      # → matches SAC_FOO, SAC_BAR_BAZ, …
    env_allowlist = ["GH_TOKEN"]  # → matches the exact name GH_TOKEN
    env_allowlist = ["BRAND_X_"]  # → matches BRAND_X_HOME, BRAND_X_*

Non-string entries are silently dropped (defensive — a TOML author's
typo shouldn't crash the audit). A missing pyproject, missing
``[tool.scitex_dev]`` table, missing ``env_allowlist`` key, or an
``env_allowlist`` that isn't a list all yield the empty tuple — i.e.
"no per-package allowlist" — and the audit falls through to the
universal allowlist + the standard ``SCITEX_<PKG>_*`` rule.
"""

from __future__ import annotations

from pathlib import Path

_PKG_ENV_ALLOWLIST_KEY = "env_allowlist"


def read_pkg_env_allowlist(package: str, repo: Path | None = None) -> tuple[str, ...]:
    """Return the ``env_allowlist`` declared in ``package``'s pyproject.

    Reads ``[tool.scitex_dev] env_allowlist`` (a list of prefix strings)
    from the audited package's ``pyproject.toml`` — same
    checked-out-tree discovery as
    :func:`scitex_dev._cli.audit._summary._mcp_parity.is_mcp_parity_exempt`
    (registry ``local_path`` when present, else walk up from the
    import location).

    Parameters
    ----------
    package
        ECOSYSTEM key (e.g. ``"scitex-agent-container"``). Used to
        resolve the local checkout via the registry when ``repo`` is
        not given.
    repo
        Explicit repo root. When provided, the registry lookup is
        bypassed — used by tests that operate on a synthetic package
        tree (mirrors the ``repo=`` escape in
        :func:`is_mcp_parity_exempt`).

    Returns
    -------
    tuple[str, ...]
        Empty tuple when the file is absent, the table is missing or
        malformed, the key is absent, the value isn't a list, or all
        entries are non-strings. Otherwise the source-order list of
        non-empty string entries. Order matches the pyproject source —
        callers may sort or dedup if it matters.
    """
    # Local import keeps the module load cycle-free; ``_mcp_parity``
    # is a sibling in the same package and re-uses the same
    # registry-or-import-walk discovery logic.
    from ._mcp_parity import _audited_repo_root

    try:
        import tomllib  # 3.11+
    except ImportError:  # pragma: no cover  -- Python 3.9-3.10 fallback
        import tomli as tomllib  # type: ignore[no-redef]

    root = repo if repo is not None else _audited_repo_root(package)
    if root is None:
        return ()
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return ()
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ()
    tool = data.get("tool", {})
    sd = tool.get("scitex_dev") or tool.get("scitex-dev") or {}
    raw = sd.get(_PKG_ENV_ALLOWLIST_KEY)
    if not isinstance(raw, list):
        return ()
    return tuple(p for p in raw if isinstance(p, str) and p)


def is_var_in_pkg_allowlist(var: str, pkg_allowlist: tuple[str, ...]) -> bool:
    """True when ``var`` matches an entry in the per-package allowlist.

    Apply "equal-to-stripped or prefix-match" semantics — identical
    shape to the universal allowlist in
    ``_audit._ALLOWED_ENV_PREFIXES`` so callers don't have to remember
    which list a prefix lives in.

    Empty ``pkg_allowlist`` → always ``False``. Empty ``var`` →
    always ``False``.
    """
    if not var or not pkg_allowlist:
        return False
    return any(var == p.rstrip("_") or var.startswith(p) for p in pkg_allowlist)


__all__ = [
    "read_pkg_env_allowlist",
    "is_var_in_pkg_allowlist",
]
