#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem ci-template apply`` — programmatic core.

Behavioural contract (see PR description for full rationale):

1. **Detect target repo state** — parse ``pyproject.toml`` to derive
   ``PKG_NAME`` (``[project].name``) and ``PKG_MODULE`` (``-`` → ``_``).
   List existing ``.github/workflows/`` files.

2. **Branch-protection compatibility gate** — query the target's
   ``required_status_checks`` for ``develop`` and ``main`` via ``gh api``.
   If any required context is NOT in the rendered templates' emitted
   job-names, refuse to apply. ``skip_required_check_gate=True`` bypasses
   (operator-debug only).

3. **Substitute templates** — read vendored ``*.tmpl`` files and replace
   ``<PKG_NAME>``, ``<PKG_MODULE>``, ``<PYTHON_VERSIONS_JSON>``,
   ``<CLI_HELP_BLOCK>``. The CLI-help block is derived from
   ``[project.scripts]`` so consoles imported via entry-points get a
   smoke ``--help`` exercise inside the import-smoke job.

4. **Apply changes** — write ``pr-ci.yml`` + ``release-ci.yml``; delete
   consolidated standalone workflows by HARDCODED PREFIX LIST (no
   heuristic content-matching, to avoid clobbering an unfamiliar
   workflow that happens to share a prefix). Keep CLA / publish /
   auto-merge / RTD untouched.

5. **--dry-run** — skip writes; return the intended diff for the caller
   to print.

Failure modes use distinct exception types so the CLI can render
operator-friendly errors instead of tracebacks.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore[no-redef]
else:  # pragma: no cover - exercised on py3.10 only
    import tomli as tomllib  # type: ignore[no-redef]


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class ApplyError(RuntimeError):
    """Operator-facing apply failure (bad target, parse error, etc.)."""


class BranchProtectionGateError(ApplyError):
    """The gate found required contexts the new templates won't publish."""

    def __init__(self, missing: Dict[str, List[str]]):
        self.missing = missing  # {branch: [missing_context, ...]}
        msg_lines = ["branch-protection gate failure — required contexts not in emitted set:"]
        for branch, ctxs in sorted(missing.items()):
            msg_lines.append(f"  {branch}: missing {ctxs!r}")
        msg_lines.append(
            "Refusing to apply (would deadlock PRs). Re-run with "
            "skip_required_check_gate=True only for debugging."
        )
        super().__init__("\n".join(msg_lines))


# --------------------------------------------------------------------------- #
# Result type — caller (CLI) decides how to render
# --------------------------------------------------------------------------- #


@dataclass
class ApplyResult:
    """Outcome of ``apply``. ``dry_run`` callers print; live callers see the
    same fields but ``written_paths`` and ``deleted_paths`` reflect the FS.
    """

    repo_dir: Path
    pkg_name: str
    pkg_module: str
    python_versions: List[str]
    emitted_jobs: List[str]
    required_contexts: Dict[str, List[str]] = field(default_factory=dict)
    rendered: Dict[str, str] = field(default_factory=dict)  # path-rel → content
    written_paths: List[Path] = field(default_factory=list)
    deleted_paths: List[Path] = field(default_factory=list)
    skipped_delete_paths: List[Path] = field(default_factory=list)
    dry_run: bool = False
    gate_skipped: bool = False


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


DEFAULT_PYTHON_VERSIONS: List[str] = ["3.11", "3.12", "3.13"]

# Hardcoded prefix list for the delete-on-apply heuristic. ONLY files
# matching one of these prefixes are eligible for deletion; unknown
# workflows are left alone. Keep this list narrow.
_DELETABLE_WORKFLOW_PREFIXES: Tuple[str, ...] = (
    "import-smoke-",
    "pytest-matrix-",
    "dep-hygiene-smoke",
    # `<pkg>-quality-audit*` is covered by the live-check in
    # ``_eligible_for_delete``: filename contains "quality-audit".
)

# Workflows that MUST be preserved no matter what (operator-edited).
_PROTECTED_WORKFLOWS: Tuple[str, ...] = (
    "pr-ci.yml",
    "release-ci.yml",
    "cla.yml",
    "auto-merge-to-develop.yaml",
    "auto-merge-to-develop.yml",
)
# Prefix-based preservation:
_PROTECTED_WORKFLOW_PREFIXES: Tuple[str, ...] = (
    "pypi-publish-",
    "rtd-sphinx-",
)


# --------------------------------------------------------------------------- #
# Template loading + rendering
# --------------------------------------------------------------------------- #


def _templates_dir() -> Path:
    return Path(__file__).parent / "templates"


def _load_template(name: str) -> str:
    path = _templates_dir() / name
    if not path.is_file():
        raise ApplyError(f"vendored template missing: {path}")
    return path.read_text(encoding="utf-8")


def _cli_help_block(scripts: Dict[str, str]) -> str:
    """Render the ``<CLI_HELP_BLOCK>`` payload (steps inside import-smoke).

    Each ``[project.scripts]`` entry becomes::

          - name: smoke <name> --help
            run: .venv/bin/<name> --help

    With no scripts, emit empty string — the template line is consumed.
    """
    if not scripts:
        return ""
    lines: List[str] = []
    for entry in sorted(scripts):
        # YAML indent: 6 spaces (matches `steps:` items in template).
        lines.append(f"      - name: smoke {entry} --help")
        lines.append(f"        run: .venv/bin/{entry} --help")
    return "\n".join(lines)


def render(
    template_name: str,
    *,
    pkg_name: str,
    pkg_module: str,
    python_versions: Sequence[str],
    scripts: Optional[Dict[str, str]] = None,
) -> str:
    """Pure substitution. Exposed for tests + manual diffing."""
    body = _load_template(template_name)
    body = body.replace("<PKG_NAME>", pkg_name)
    body = body.replace("<PKG_MODULE>", pkg_module)
    body = body.replace(
        "<PYTHON_VERSIONS_JSON>",
        json.dumps(list(python_versions)),
    )
    help_block = _cli_help_block(scripts or {})
    # The placeholder occupies its own line; substitute the line content.
    # Empty block → drop the placeholder line entirely.
    if not help_block:
        body = body.replace("<CLI_HELP_BLOCK>\n", "")
    else:
        body = body.replace("<CLI_HELP_BLOCK>", help_block)
    return body


# --------------------------------------------------------------------------- #
# Deterministic emitted-jobs set (gate input)
# --------------------------------------------------------------------------- #


def emitted_job_names(
    python_versions: Sequence[str], *, include_preserved: bool = True
) -> List[str]:
    """Return the sorted set of GitHub check-run names the rendered
    templates publish, given a python-versions matrix.

    Used by the branch-protection gate. MUST stay in lock-step with the
    ``name:`` fields in the .tmpl files; tests assert the rendered YAML
    really does publish these names (no drift).

    When ``include_preserved`` is True (default), also include the
    well-known check-run names emitted by *preserved* workflows that the
    apply step never removes (cla.yml → ``CLAssistant``; rtd-sphinx-*.yml
    → ``sphinx`` / ``docs``). This prevents the gate from refusing
    repos whose ``required_status_checks`` reference those check-run
    names. Pass ``include_preserved=False`` for tests that need the
    pure-rendered-template set.
    """
    names = {
        "import-smoke-on-ubuntu-py3-12",
        "dep-hygiene-smoke",
        "audit",
    }
    for pv in python_versions:
        names.add(f"pytest-matrix-on-ubuntu-py{pv}")
    if include_preserved:
        names.update(_preserved_workflow_job_names())
    return sorted(names)


# Well-known check-run names from preserved workflows. These files are
# intentionally never removed by ci-template apply (see ``_PROTECTED_*``)
# and they publish these standard names. Kept here as a small static set
# so the gate logic never has to read or parse YAML at apply time.
def _preserved_workflow_job_names() -> set:
    return {
        "CLAssistant",   # from cla.yml
        "sphinx",        # from rtd-sphinx-build-*.yml (most repos)
        "docs",          # alt name some repos use for rtd-sphinx
    }


# --------------------------------------------------------------------------- #
# Target-repo inspection
# --------------------------------------------------------------------------- #


def _read_pyproject(repo_dir: Path) -> dict:
    p = repo_dir / "pyproject.toml"
    if not p.is_file():
        raise ApplyError(f"no pyproject.toml at {repo_dir}")
    return tomllib.loads(p.read_text(encoding="utf-8"))


def _derive_pkg(meta: dict) -> Tuple[str, str]:
    project = meta.get("project", {})
    name = project.get("name")
    if not name:
        raise ApplyError("pyproject.toml [project].name missing")
    module = name.replace("-", "_")
    return name, module


def _derive_scripts(meta: dict) -> Dict[str, str]:
    return dict(meta.get("project", {}).get("scripts", {}))


def _detect_owner_repo(repo_dir: Path) -> Optional[str]:
    """Return ``owner/repo`` from ``origin`` remote, or None if not a git repo
    or no origin configured. We never raise — the gate just degrades to
    "no required contexts found", which is safe.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=7,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if out.returncode != 0:
        return None
    url = out.stdout.strip()
    # SSH: git@github.com:owner/repo.git ; HTTPS: https://github.com/owner/repo(.git)
    if "github.com" not in url:
        return None
    rest = url.split("github.com", 1)[1].lstrip(":/")
    if rest.endswith(".git"):
        rest = rest[: -len(".git")]
    parts = rest.split("/")
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _gh_api_get(endpoint: str) -> Tuple[int, str]:
    """Plain ``gh api GET`` shim; returns (rc, stdout|stderr)."""
    if shutil.which("gh") is None:
        return 127, "gh CLI not on PATH"
    proc = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, (proc.stdout if proc.returncode == 0 else proc.stderr)


def _is_poisoned_context(ctx: str) -> bool:
    """Detect a context string that is actually a serialised GitHub API
    error body (e.g. ``'{"message":"Branch not protected", …,"status":"404"}'``).

    Historical: in some scitex-* repos the ``required_status_checks.contexts``
    array contains a single literal JSON error-body string from a setup-time
    misstep (a 404 response captured as a context name). Such "contexts" can
    never be satisfied by any real CI job, so they would deadlock the gate
    forever. We filter them here with a warning logged at the callsite.
    """
    s = (ctx or "").strip()
    if not (s.startswith("{") and s.endswith("}")):
        return False
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return False
    return isinstance(obj, dict) and (
        "message" in obj or "status" in obj or "documentation_url" in obj
    )


def _read_required_contexts(owner_repo: str, branch: str) -> List[str]:
    """Query branch-protection required_status_checks for one branch.

    Silently returns [] for 404 (branch not protected) so callers can
    union the result across branches without special-casing.

    Also filters out *poisoned* contexts — entries whose name is a literal
    JSON error body (see ``_is_poisoned_context``). Such contexts are real in
    a handful of legacy scitex-* repos; treating them as required would
    permanently block the gate because no CI job can ever emit such a name.
    """
    rc, out = _gh_api_get(
        f"repos/{owner_repo}/branches/{branch}/protection/required_status_checks"
    )
    if rc != 0:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    raw = list(data.get("contexts") or [])
    return [c for c in raw if not _is_poisoned_context(c)]


# --------------------------------------------------------------------------- #
# Workflow file housekeeping
# --------------------------------------------------------------------------- #


def _eligible_for_delete(workflow_filename: str) -> bool:
    """Return True iff *workflow_filename* matches the hardcoded delete
    prefix list AND is not on the protected list.
    """
    if workflow_filename in _PROTECTED_WORKFLOWS:
        return False
    if any(workflow_filename.startswith(p) for p in _PROTECTED_WORKFLOW_PREFIXES):
        return False
    if any(workflow_filename.startswith(p) for p in _DELETABLE_WORKFLOW_PREFIXES):
        return True
    # `<pkg>-quality-audit*` heuristic.
    if "quality-audit" in workflow_filename:
        return True
    return False


def _list_workflows(repo_dir: Path) -> List[Path]:
    wf_dir = repo_dir / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    return sorted(p for p in wf_dir.iterdir() if p.is_file())


# --------------------------------------------------------------------------- #
# Public entry-point
# --------------------------------------------------------------------------- #


def apply(
    repo_dir: os.PathLike[str] | str,
    *,
    dry_run: bool = False,
    branch: str = "chore/ci-speedup",  # reserved for future PR-flow extension
    python_versions: Optional[Sequence[str]] = None,
    skip_required_check_gate: bool = False,
    # Injection seams (tests pass these; CLI does not).
    required_contexts_lookup=None,
    owner_repo_lookup=None,
) -> ApplyResult:
    """Apply the CI templates to *repo_dir*.

    Parameters
    ----------
    repo_dir
        Path to the target scitex-* repo (must contain pyproject.toml).
    dry_run
        If True, compute everything but write nothing.
    branch
        Reserved: future PR-flow extension will create this branch and
        commit. Today, ``apply`` writes to the working tree; the operator
        commits.
    python_versions
        Override the pytest matrix. Default ["3.11","3.12","3.13"].
    skip_required_check_gate
        Skip the gate. DANGEROUS — never use in batch.
    required_contexts_lookup
        ``(owner_repo, branch) -> List[str]`` callable; defaults to live
        ``gh api`` call. Tests pass a stub.
    owner_repo_lookup
        ``(repo_dir) -> Optional[str]`` callable; defaults to live
        ``git remote get-url origin`` parse. Tests pass a stub.
    """
    repo_dir = Path(repo_dir).resolve()
    if not (repo_dir / ".git").exists():
        raise ApplyError(f"not a git repo: {repo_dir}")
    meta = _read_pyproject(repo_dir)
    pkg_name, pkg_module = _derive_pkg(meta)
    scripts = _derive_scripts(meta)

    pvs = list(python_versions or DEFAULT_PYTHON_VERSIONS)
    emitted = emitted_job_names(pvs)

    # Gate
    or_lookup = owner_repo_lookup or _detect_owner_repo
    owner_repo = or_lookup(repo_dir)
    rc_lookup = required_contexts_lookup or _read_required_contexts
    required: Dict[str, List[str]] = {}
    if owner_repo is not None:
        for br in ("develop", "main"):
            ctxs = rc_lookup(owner_repo, br)
            if ctxs:
                required[br] = ctxs

    if not skip_required_check_gate and required:
        emitted_set = set(emitted)
        missing: Dict[str, List[str]] = {}
        for br, ctxs in required.items():
            gap = [c for c in ctxs if c not in emitted_set]
            if gap:
                missing[br] = gap
        if missing:
            raise BranchProtectionGateError(missing)

    # Render
    rendered = {
        ".github/workflows/pr-ci.yml": render(
            "pr-ci.yml.tmpl",
            pkg_name=pkg_name,
            pkg_module=pkg_module,
            python_versions=pvs,
            scripts=scripts,
        ),
        ".github/workflows/release-ci.yml": render(
            "release-ci.yml.tmpl",
            pkg_name=pkg_name,
            pkg_module=pkg_module,
            python_versions=pvs,
            scripts=scripts,
        ),
    }

    # Plan deletes
    existing = _list_workflows(repo_dir)
    to_delete: List[Path] = []
    skipped: List[Path] = []
    for wf in existing:
        rel = wf.name
        # Never delete a file we're about to (re-)write.
        if any(wf == repo_dir / r for r in rendered):
            continue
        if _eligible_for_delete(rel):
            to_delete.append(wf)
        else:
            # Track skips only for non-protected non-target files so the
            # caller can show "kept" if needed; protected workflows are
            # noise here.
            if rel not in _PROTECTED_WORKFLOWS and not any(
                rel.startswith(p) for p in _PROTECTED_WORKFLOW_PREFIXES
            ):
                skipped.append(wf)

    result = ApplyResult(
        repo_dir=repo_dir,
        pkg_name=pkg_name,
        pkg_module=pkg_module,
        python_versions=pvs,
        emitted_jobs=emitted,
        required_contexts=required,
        rendered=rendered,
        skipped_delete_paths=skipped,
        dry_run=dry_run,
        gate_skipped=skip_required_check_gate,
    )

    if dry_run:
        # Annotate would-be writes/deletes; do not touch FS.
        result.written_paths = [repo_dir / r for r in rendered]
        result.deleted_paths = list(to_delete)
        return result

    # Write
    wf_dir = repo_dir / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in rendered.items():
        out = repo_dir / rel
        out.write_text(content, encoding="utf-8")
        result.written_paths.append(out)

    for d in to_delete:
        d.unlink()
        result.deleted_paths.append(d)

    return result
