"""§6 — Python-API ↔ MCP-tool parity check (extracted from `_mcp_audit`).

Two concerns live here:

1. **Parity / orphan-tool detection** (`_check_api_parity`) — every MCP
   tool should map to a public Python-API function and vice-versa. A
   large mismatch in either direction is flagged §6.

2. **Per-package exemption** (`is_mcp_parity_exempt`) — some packages
   legitimately expose far more MCP tools than Python-API functions.
   figrecipe mirrors ~74 matplotlib Axes methods (plot / scatter / bar /
   hist / …) as tools that have no standalone Python-function counterpart
   by design; for that package class §6 is a false positive.

A package declares the exemption in its OWN repo, mirroring the
``no_cli`` / ``no_e2e`` opt-out precedent in
``_check_smoke_e2e_layers.py``::

    # pyproject.toml (REQUIRED primary)
    [tool.scitex_dev]
    mcp_parity_exempt = true

    # .scitex/dev/config.yaml (OPTIONAL — convention parity)
    audit:
      mcp-parity-exempt: true

When set, `_check_api_parity` emits an informational "exempt by config"
line instead of a §6 violation. The rule still fires for every package
that did NOT declare the exemption.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from ._audit import Violation
from ._mcp_names import _import_name, _short_name


# --------------------------------------------------------------------- #
# §6 exemption — per-package opt-out                                    #
# --------------------------------------------------------------------- #

_TOOL_BLOCK_RE = re.compile(
    r"^\[tool\.scitex[_-]dev\](.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
_MCP_PARITY_EXEMPT_RE = re.compile(
    r"^\s*mcp_parity_exempt\s*=\s*true\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_YAML_MCP_PARITY_EXEMPT_RE = re.compile(
    r"^\s*mcp-parity-exempt\s*:\s*true\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _repo_root_from_import(package: str) -> Path | None:
    """Resolve the package's repo root from the installed/checked-out tree.

    Walks up from the import location (``src/<pkg>/__init__.py``) to the
    repo root that holds ``pyproject.toml``. Mirrors audit-project's
    ``_resolve_repo_root`` so the §6 exemption can be read from the tree
    that is actually being audited — critical in CI, where the editable
    install lives at ``$GITHUB_WORKSPACE`` and the ecosystem registry's
    fixed ``local_path`` does not exist on the runner.
    """
    import importlib.util

    import_name = _import_name(package)
    try:
        spec = importlib.util.find_spec(import_name)
    except (ImportError, ValueError, ModuleNotFoundError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    for loc in spec.submodule_search_locations:
        # src/<pkg>/__init__.py → repo root is two levels up (src layout)
        candidate = Path(loc).parent.parent
        if (candidate / "pyproject.toml").is_file():
            return candidate
        # flat layout fallback
        candidate = Path(loc).parent
        if (candidate / "pyproject.toml").is_file():
            return candidate

    # Fallback: module is in site-packages (non-editable PyPI install), so
    # walking up from its location won't find pyproject.toml. Try common
    # development checkout locations: $HOME/proj/<package>/ (which matches
    # the ecosystem registry's ~/proj/<name> convention) and all
    # /home/*/proj/<package>/ for container/multi-user environments.
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
        candidate = root / package
        if (candidate / "pyproject.toml").is_file():
            return candidate.resolve()

    return None


def _audited_repo_root(package: str) -> Path | None:
    """Best-effort local checkout path for `package`.

    Prefers the ecosystem registry's ``local_path`` (the dev workstation
    case), then falls back to the installed/checked-out tree via
    ``find_spec``. The fallback is what makes the §6 exemption work in CI,
    where the registry path is absent but the package is editable-installed
    from the checkout.
    """
    try:
        from ...._ecosystem import get_local_path
    except ImportError:
        get_local_path = None  # type: ignore[assignment]

    if get_local_path is not None:
        try:
            path = get_local_path(package)
        except Exception:
            path = None
        if path is not None and path.is_dir():
            return path

    return _repo_root_from_import(package)


def is_mcp_parity_exempt(package: str, repo: Path | None = None) -> bool:
    """Return True when `package` declares §6 (MCP-parity) exemption.

    pyproject.toml ``[tool.scitex_dev] mcp_parity_exempt = true`` is the
    required primary; ``.scitex/dev/config.yaml`` ``audit.mcp-parity-exempt:
    true`` is honored for convention parity. Either form opts the package
    out of the §6 parity/orphan-tool check.

    Parameters
    ----------
    package
        ECOSYSTEM key (e.g. ``"figrecipe"``). Used to resolve the local
        checkout via the registry when `repo` is not given.
    repo
        Explicit repo root. When provided, the registry lookup is
        bypassed — used by tests that operate on a synthetic package
        tree.
    """
    root = repo if repo is not None else _audited_repo_root(package)
    if root is None:
        return False

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            txt = pyproject.read_text(errors="ignore")
        except OSError:
            txt = ""
        m = _TOOL_BLOCK_RE.search(txt)
        if m is not None and _MCP_PARITY_EXEMPT_RE.search(m.group(1)):
            return True

    cfg = root / ".scitex" / "dev" / "config.yaml"
    if cfg.is_file():
        try:
            cfg_txt = cfg.read_text(errors="ignore")
        except OSError:
            cfg_txt = ""
        if _YAML_MCP_PARITY_EXEMPT_RE.search(cfg_txt):
            return True

    return False


def declares_no_mcp(package: str, repo: Path | None = None) -> bool:
    """Return True when `package` declares the ``no-mcp`` CAPABILITY.

    Reads ``.scitex/dev/config.yaml`` ``audit.capabilities: [no-mcp]`` via the
    shared :func:`load_config` loader (operator directive 2026-06-22). This is
    the package-TYPE knob for ALIAS packages with no first-party MCP surface
    (e.g. ``scitex-plt`` aliases ``figrecipe``): the §6 MCP↔Python-API parity
    check does not apply, and the auditor skips it with a VISIBLE notice.

    Distinct from :func:`is_mcp_parity_exempt` (the older ``mcp_parity_exempt``
    flag for diagram-rich packages whose tools mirror external methods): both
    skip §6, but the capability emits the canonical
    ``skipped (declared capability: no-mcp)`` notice.
    """
    root = repo if repo is not None else _audited_repo_root(package)
    if root is None:
        return False
    from .._config import load_config

    return load_config(root).has_capability("no-mcp")


def mcp_tools_allowlist(package: str, repo: Path | None = None) -> set[str] | None:
    """Return the package's declared MCP tool allowlist, or None if absent.

    Finer-grained alternative to the all-or-nothing `mcp_parity_exempt`: a
    package that intentionally exposes a curated MCP surface (rather than
    mirroring its whole Python API) lists exactly the tools it means to ship.
    When present, §6 verifies the registered tools match this set — no
    full-API mirror required, and no blanket skip of the check.

    Read from (first match wins):
      1. ``pyproject.toml`` → ``[tool.scitex_dev] mcp_tools_allowlist = [...]``
      2. ``.scitex/dev/config.yaml`` → ``audit: {mcp-tools-allowlist: [...]}``

    Names may be bare (``compute_metrics``) or prefixed (``ml_compute_metrics``);
    the §6 check normalizes both. ``skills_list`` / ``skills_get`` are always
    permitted and need not be listed.
    """
    root = repo if repo is not None else _audited_repo_root(package)
    if root is None:
        return None

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib

            data = tomllib.loads(pyproject.read_text(errors="ignore"))
            value = (
                data.get("tool", {}).get("scitex_dev", {}).get("mcp_tools_allowlist")
            )
            if isinstance(value, list):
                return {str(x) for x in value}
        except Exception:
            pass

    cfg = root / ".scitex" / "dev" / "config.yaml"
    if cfg.is_file():
        try:
            import yaml

            data = yaml.safe_load(cfg.read_text(errors="ignore")) or {}
            audit = data.get("audit") or {}
            value = audit.get("mcp-tools-allowlist")
            if isinstance(value, list):
                return {str(x) for x in value}
        except Exception:
            pass

    return None


# --------------------------------------------------------------------- #
# §6 — Python API parity                                                 #
# --------------------------------------------------------------------- #


def _python_api_names(package: str) -> set[str]:
    """Return the set of public *function* names exported by `scitex_<pkg>`.

    Best-effort: imports the top-level module, reads `__all__` (or non-private
    attributes), and keeps only callables that are NOT classes/types. Classes
    are exposed as API but are rarely wrapped as MCP tools — including them
    in the parity check produces false positives.

    Two layouts are accepted, matching the two patterns in the
    SciTeX ecosystem:

    1. **Flat** — `pkg.<verb>_<noun>(...)` (the original convention).
       Used by scitex-stats, scitex-io, etc.
    2. **Nested** — `pkg.<noun>.<verb>(...)` (the CLI-mirror form).
       Each noun submodule re-exports verbs under their bare names;
       this auditor flattens them to `<noun>_<verb>` for the parity
       comparison so the MCP tool naming convention still applies
       (a tool named ``agent_list`` matches either ``pkg.agent_list``
       or ``pkg.agent.list``).
    """
    import inspect as _inspect

    import_name = _import_name(package)
    try:
        mod = importlib.import_module(import_name)
    except Exception:
        return set()
    names = getattr(mod, "__all__", None)
    if names is None:
        names = [n for n in dir(mod) if not n.startswith("_")]
    out: set[str] = set()
    for n in names:
        if not isinstance(n, str):
            continue
        val = getattr(mod, n, None)
        if val is None or _inspect.isclass(val):
            continue
        if _inspect.ismodule(val):
            # Nested-form noun submodule. Walk its public verbs and
            # surface them as `<noun>_<verb>` so the parity check can
            # match an MCP tool named the same way. Skip submodules
            # without an explicit __all__ — those tend to be deep
            # internals, not the package's CLI-tree mirror.
            sub_names = getattr(val, "__all__", None)
            if sub_names is None:
                continue
            for sub_n in sub_names:
                if not isinstance(sub_n, str):
                    continue
                sub_val = getattr(val, sub_n, None)
                if (
                    sub_val is None
                    or _inspect.isclass(sub_val)
                    or _inspect.ismodule(sub_val)
                    or not callable(sub_val)
                ):
                    continue
                # Trailing underscore is the Python idiom for keyword
                # aliasing (`import_`, `class_`); strip before joining
                # so `pkg.db.import_` matches MCP `db_import`.
                clean_verb = sub_n.rstrip("_")
                out.add(f"{n}_{clean_verb}")
            continue
        if callable(val):
            out.add(n)
    return out


def _check_api_parity(
    package: str,
    tool_names: set[str],
    out: list[Violation],
    repo: Path | None = None,
) -> None:
    """§6 — every Python API should map to an MCP tool (and vice versa).

    Skipped when the package declares `[tool.scitex_dev] mcp_parity_exempt
    = true` in its own pyproject.toml (see `is_mcp_parity_exempt`). Used by
    plotting/diagram-rich packages (e.g. figrecipe) whose MCP tools mirror
    matplotlib Axes methods with no standalone Python-function counterpart.

    `repo` overrides the registry path lookup for the exemption check —
    used by tests that operate on a synthetic package tree.
    """
    # Leaf-side package-type capability knob: ALIAS packages with no
    # first-party MCP surface declare ``audit.capabilities: [no-mcp]`` in
    # ``.scitex/dev/config.yaml``. §6 does not apply to them; skip it with a
    # VISIBLE "declared capability" notice (operator directive 2026-06-22).
    if declares_no_mcp(package, repo=repo):
        import click

        # Use click.echo(err=True) — NOT _emit("info", ...) — so the notice is
        # ALWAYS visible: the audit logger's default level is WARNING and would
        # swallow an info headline. The operator requires this skip to be
        # visible, not silent (directive 2026-06-22).
        click.echo(
            f"  [capability] {package}: §6 skipped (declared capability: no-mcp)"
            " — alias/no first-party MCP surface; parity does not apply to this"
            " package type",
            err=True,
        )
        return

    if is_mcp_parity_exempt(package, repo=repo):
        from .._emit import emit as _emit

        _emit(
            "info",
            f"{package}: §6 MCP-parity exempt by config "
            "([tool.scitex_dev] mcp_parity_exempt = true) — plotting/diagram-rich "
            "tool surface mirrors external methods with no Python-API counterpart",
        )
        return

    short = _short_name(package)
    # Normalize MCP names to compare against bare Python names.
    mcp_normalized = {n.removeprefix(f"{short}_") for n in tool_names}

    # Finer-grained opt-in: a declared allowlist scopes §6 to the curated
    # surface (registered tools must match the declaration) instead of the
    # full Python-API mirror.
    allowlist = mcp_tools_allowlist(package, repo=repo)
    if allowlist is not None:
        from .._emit import emit as _emit

        _emit(
            "info",
            f"{package}: §6 MCP-parity scoped to mcp_tools_allowlist "
            f"({len(allowlist)} declared) — checked against the curated surface, "
            "not the full Python API",
        )
        out.extend(_allowlist_violations(package, allowlist, mcp_normalized))
        return

    py_apis = _python_api_names(package)
    if not py_apis:
        return  # cannot establish parity; not the auditor's place to invent it.

    out.extend(_parity_violations(package, py_apis, mcp_normalized))


def _allowlist_violations(
    package: str, allowlist: set[str], mcp_normalized: set[str]
) -> list[Violation]:
    """§6 with an explicit allowlist: the registered tools must equal the
    declared ``mcp_tools_allowlist`` (``skills_list`` / ``skills_get`` always
    permitted). Flags tools the server exposes but didn't declare, and declared
    names with no registered tool — finer control than the boolean exemption.

    Split out (pure set comparison) so it is testable without import/registry
    I/O, mirroring :func:`_parity_violations`.
    """
    out: list[Violation] = []
    skill_tools = {"skills_list", "skills_get"}
    short = _short_name(package)
    allow_norm = {n.removeprefix(f"{short}_") for n in allowlist} - skill_tools
    actual = mcp_normalized - skill_tools

    undeclared = actual - allow_norm
    if undeclared:
        out.append(
            Violation(
                package,
                "§6",
                f"MCP tool(s) not in mcp_tools_allowlist: {sorted(undeclared)} "
                "— add them to the allowlist or remove the tool",
            )
        )

    missing = allow_norm - actual
    if missing:
        out.append(
            Violation(
                package,
                "§6",
                f"mcp_tools_allowlist names with no registered MCP tool: "
                f"{sorted(missing)} — register the tool or fix the allowlist",
            )
        )
    return out


def _tool_matches_api(tool: str, api: str) -> bool:
    """Return True if `tool` covers `api` for §6 parity.

    A bare-name match (``tool == api``) always counts. We ALSO accept any
    ``<verb>_<api>`` form — i.e. the tool ends with ``_<api>`` — so an
    MCP tool named ``submit_sbatch`` satisfies §6 for the Python API
    ``sbatch``. This resolves the §2 / §6 conflict surfaced by #82:
    single-token Python APIs (the SLURM verb family ``sbatch`` /
    ``srun`` / ``squeue`` / ``sacct`` / ``scancel`` / ``salloc``, plus
    ``sync``, ``rsync``, etc.) previously could not satisfy both rules
    at once — §2 forbids single-token tool names, §6 demanded an
    exactly-matching MCP tool. Letting §6 accept the verb-prefixed form
    lets the package keep §2-compliant tool names while still passing
    §6.

    The match is intentionally one-way (the API name must appear as the
    tool's suffix after an underscore) so this does NOT silence the
    legitimate case where a totally-unrelated tool happens to share a
    short suffix with an API — the FULL api string must be present.
    """
    if tool == api:
        return True
    return tool.endswith(f"_{api}")


def _parity_violations(
    package: str, py_apis: set[str], mcp_normalized: set[str]
) -> list[Violation]:
    """Pure §6 comparison: given Python-API names and normalized MCP tool
    names, return the §6 violations (missing-in-MCP and orphan-tool).

    Split out from `_check_api_parity` so the comparison logic is testable
    with real sets — no module-import or registry I/O required.

    Matching uses :func:`_tool_matches_api`, which accepts both the bare
    ``tool == api`` form AND the ``<verb>_<api>`` form so single-token
    Python APIs can satisfy both §2 (verb_noun naming) and §6
    (Python-API coverage) at the same time. See :func:`_tool_matches_api`
    docstring and #82 for the motivating conflict.
    """
    out: list[Violation] = []

    missing_in_mcp = {
        api
        for api in py_apis
        if not any(_tool_matches_api(t, api) for t in mcp_normalized)
    }
    if missing_in_mcp and len(missing_in_mcp) > len(py_apis) * 0.5:
        out.append(
            Violation(
                package,
                "§6",
                f"{len(missing_in_mcp)}/{len(py_apis)} Python APIs have no "
                f"matching MCP tool (sample: {sorted(missing_in_mcp)[:3]})",
            )
        )

    # Orphan check (warn-tier; small set is normal for envelope tools).
    # A tool that covers any Python API via the verb_<api> form is not
    # an orphan — same matching rule as the missing-in-MCP direction so
    # the two halves stay symmetric.
    skill_tools = {"skills_list", "skills_get"}
    orphans = {
        t
        for t in mcp_normalized
        if t not in skill_tools
        and not any(_tool_matches_api(t, api) for api in py_apis)
    }
    if orphans and len(orphans) > 3:
        out.append(
            Violation(
                package,
                "§6",
                f"{len(orphans)} MCP tools have no matching Python API "
                f"(sample: {sorted(orphans)[:3]})",
            )
        )
    return out


__all__ = [
    "is_mcp_parity_exempt",
    "mcp_tools_allowlist",
    "_parity_violations",
    "_allowlist_violations",
    "_python_api_names",
    "_check_api_parity",
    "_tool_matches_api",
]
