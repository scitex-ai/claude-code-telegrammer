#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `set-branch-protection` / `unset-branch-protection`.

Brand-wide GitHub branch-protection management. PR #117 raced past CI by
auto-merging before required checks completed; an ecosystem survey then
showed 8 of 10 sampled repos have NO required_status_checks on `develop`.
This module makes "CI-green is the only gate" actually enforced by
configuring branch protection consistently across the fleet.

Policy (from lead msg a3c59d1a):

  required_status_checks       = 6 CI contexts, intersected with what the
                                  repo's workflows actually publish:
                                    pytest-matrix-on-ubuntu-py3.11
                                    pytest-matrix-on-ubuntu-py3.12
                                    pytest-matrix-on-ubuntu-py3.13
                                    sphinx
                                    import-smoke-on-ubuntu-py3-12
                                    audit
  strict                       = False  (don't serialise the parallel fleet
                                          on rebase-before-merge churn)
  enforce_admins (develop)     = True   (the #117 race fix; nobody bypasses
                                          CI on the integration branch)
  enforce_admins (main)        = False  (release flow needs the admin merge
                                          + tag-push to fire PyPI; locking
                                          admin out would wedge releases)
  required_pull_request_reviews = OMIT  (CI-green is the only gate)
  required_linear_history      = True   (matches the squash-merge convention)
  allow_force_pushes           = False
  allow_deletions              = False

CLAssistant is deliberately HELD OUT of the required set today — the bot
has a documented transient timing failure mode; making it blocking would
let a bot hiccup wedge the fleet's auto-merge. Keep it as a non-blocking
check; revisit when stable.

Operations
----------
Both commands default to --dry-run. Pass --execute (or -y / --yes) to
actually PUT or DELETE. The PUT body is computed live from the repo's
current workflows so additions land automatically; the required-set
contexts that the repo doesn't publish are silently dropped (e.g.
scitex-orochi has no develop branch — main-only operation), preventing
"required check that never runs" deadlocks.

The first execution lands on scitex-dev ITSELF; fleet-wide rollout waits
on operator confirm via lead. Sibling `unset-branch-protection` is the
rollback path.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import List, Optional

import click

# The full required-set ceiling. The actual required set per repo is the
# intersection of this ceiling with the repo's published workflow check
# names — repos that don't run, say, sphinx, don't get sphinx required.
_DEFAULT_REQUIRED_CONTEXTS: List[str] = [
    "pytest-matrix-on-ubuntu-py3.11",
    "pytest-matrix-on-ubuntu-py3.12",
    "pytest-matrix-on-ubuntu-py3.13",
    "sphinx",
    "import-smoke-on-ubuntu-py3-12",
    "audit",
]


def _gh_api(method: str, endpoint: str, body: Optional[dict] = None) -> tuple[int, str]:
    """Invoke ``gh api`` with method + endpoint, optional JSON body.

    Returns ``(returncode, stdout_or_stderr_text)``. We delegate auth to
    ``gh`` rather than re-implementing GitHub OAuth.
    """
    if shutil.which("gh") is None:
        return 127, "gh CLI not on PATH; install gh and run `gh auth login`"
    argv = ["gh", "api", "--method", method, endpoint]
    if body is not None:
        argv += ["--input", "-"]
    proc = subprocess.run(
        argv,
        input=json.dumps(body) if body is not None else None,
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout if proc.returncode == 0 else proc.stderr)


def _branch_exists(owner_repo: str, branch: str) -> bool:
    """Return True iff `<owner_repo>` has the named branch live on origin."""
    rc, _ = _gh_api("GET", f"repos/{owner_repo}/branches/{branch}")
    return rc == 0


def _list_published_check_names(owner_repo: str, ref: str = "develop") -> List[str]:
    """Return the actual check-run names published at the tip of ``ref``.

    v0.17.2 tried to derive contexts from workflow filenames (workflow
    ``tests`` → assume ``pytest-matrix-on-ubuntu-py3.11`` etc), which
    only worked when the filename happened to share a prefix with the
    check-run name. The dry-run on scitex-dev exposed it — only
    ``import-smoke-on-ubuntu-py3-12`` landed, the rest were dropped.

    The actual source of truth is GitHub's ``check-runs`` API on the
    branch tip: those are EXACTLY the strings the branch-protection PUT
    accepts as required contexts. If the repo hasn't run CI on this ref
    yet, the API returns an empty list and we fall back to nothing
    required (safer than blocking on a context that doesn't yet exist).
    """
    rc, out = _gh_api(
        "GET", f"repos/{owner_repo}/commits/{ref}/check-runs?per_page=100"
    )
    if rc != 0:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    names = sorted({c.get("name", "") for c in data.get("check_runs", [])})
    return [n for n in names if n]


def _intersect_required(repo_contexts: List[str], ceiling: List[str]) -> List[str]:
    """Exact-match intersection: return ceiling members that the repo
    actually publishes as check-runs. The protection PUT will block any
    PR forever on a required context that never publishes, so this MUST
    be the strict intersection — no prefix/substring heuristic.
    """
    repo_set = set(repo_contexts)
    return [c for c in ceiling if c in repo_set]


def _policy_body(
    contexts: List[str],
    enforce_admins: bool,
) -> dict:
    """The protection JSON we PUT. Shape matches GitHub's
    ``PUT /repos/<owner>/<repo>/branches/<branch>/protection`` schema.
    """
    return {
        "required_status_checks": {
            "strict": False,
            "contexts": contexts,
        },
        "enforce_admins": enforce_admins,
        "required_pull_request_reviews": None,
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


def _deletion_only_body() -> dict:
    """Minimal protection: make the branch un-deletable, nothing else.

    The baseline every `develop` should carry (clew incident 2026-06-17: an
    unprotected, freshly-recreated develop was auto-deleted when the
    develop→main release PR merged on a `deleteBranchOnMerge:true` repo,
    breaking the publish `sync-main` job). Deliberately sets NO
    `required_status_checks` and `enforce_admins:false` so CI's own direct
    push to develop (docs-HTML commit-back, version bumps) is NOT blocked —
    that is the tension the full policy creates. Required fields are sent as
    null per the GitHub protection schema.
    """
    return {
        "required_status_checks": None,
        "enforce_admins": False,
        "required_pull_request_reviews": None,
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


def _all_distributions() -> List[str]:
    """Every ECOSYSTEM distribution name (for fleet-wide rollout)."""
    from scitex_dev._ecosystem._core import ECOSYSTEM

    return list(ECOSYSTEM.keys())


def _is_deletion_protected(owner_repo: str, branch: str) -> bool:
    """True if ``branch`` already has protection with deletions disabled.

    Used so the fleet-wide deletion-only baseline is IDEMPOTENT and
    NON-DOWNGRADING: a branch that already carries protection where
    ``allow_deletions`` is off already meets the baseline goal (un-deletable),
    so the rollout skips it rather than overwriting a possibly-stronger policy
    (e.g. a repo with required_status_checks) with the minimal one. A 404 (no
    protection) or deletions-enabled returns False → the baseline is applied.
    """
    rc, out = _gh_api("GET", f"repos/{owner_repo}/branches/{branch}/protection")
    if rc != 0:
        return False
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return False
    allow_del = data.get("allow_deletions", {})
    # GitHub returns {"enabled": bool}; treat a missing/odd shape as not-safe.
    return allow_del.get("enabled") is False if isinstance(allow_del, dict) else False


def _resolve_owner_repo(distribution: str) -> Optional[str]:
    """Map a distribution name to the ``<owner>/<repo>`` ``gh api`` slug.

    Reads from the ECOSYSTEM registry so retired / renamed repos honour
    the central source of truth.
    """
    from scitex_dev._ecosystem._core import ECOSYSTEM

    info = ECOSYSTEM.get(distribution)
    if not info:
        return None
    return info.get("github_repo")


def _apply_one(
    distribution: str,
    targets: List[str],
    *,
    deletion_only: bool,
    execute: bool,
    json_out: bool,
) -> int:
    """Apply protection to one distribution's target branches.

    Returns an exit code (0 ok, 1 a PUT failed, 2 unknown distribution).
    ``deletion_only`` uses the minimal un-deletable baseline (no required
    checks / enforce_admins) so CI pushes are not blocked; otherwise the full
    brand-wide policy, with required contexts computed live from the repo.
    """
    owner_repo = _resolve_owner_repo(distribution)
    if owner_repo is None:
        click.echo(f"error: '{distribution}' not in ECOSYSTEM", err=True)
        return 2

    contexts: List[str] = []
    if not deletion_only:
        published = _list_published_check_names(owner_repo, ref="develop")
        contexts = _intersect_required(published, _DEFAULT_REQUIRED_CONTEXTS)

    exit_code = 0
    for tgt in targets:
        if not _branch_exists(owner_repo, tgt):
            if json_out:
                click.echo(
                    json.dumps(
                        {
                            "distribution": distribution,
                            "branch": tgt,
                            "action": "skip",
                            "reason": "no-branch",
                        }
                    )
                )
            else:
                click.echo(
                    f"skip  {distribution}: branch '{tgt}' does not exist on origin",
                    err=True,
                )
            continue

        # Idempotent / non-downgrading baseline: if the branch is already
        # un-deletable, leave its (possibly stronger) policy untouched.
        if deletion_only and _is_deletion_protected(owner_repo, tgt):
            if json_out:
                click.echo(
                    json.dumps(
                        {
                            "distribution": distribution,
                            "branch": tgt,
                            "action": "skip",
                            "reason": "already-protected",
                        }
                    )
                )
            else:
                click.echo(f"skip  {distribution}@{tgt}: already deletion-protected")
            continue

        if deletion_only:
            body = _deletion_only_body()
        else:
            body = _policy_body(contexts, enforce_admins=(tgt == "develop"))

        if not execute:
            if json_out:
                click.echo(
                    json.dumps(
                        {
                            "distribution": distribution,
                            "branch": tgt,
                            "action": "dry-run",
                            "body": body,
                        }
                    )
                )
            else:
                click.echo(
                    f"DRY-RUN {distribution}@{tgt}: "
                    f"PUT repos/{owner_repo}/branches/{tgt}/protection"
                    + (" (deletion-only)" if deletion_only else "")
                )
            continue

        rc, out = _gh_api("PUT", f"repos/{owner_repo}/branches/{tgt}/protection", body)
        if rc != 0:
            if json_out:
                click.echo(
                    json.dumps(
                        {
                            "distribution": distribution,
                            "branch": tgt,
                            "action": "error",
                            "rc": rc,
                            "stderr": out,
                        }
                    )
                )
            else:
                click.echo(
                    f"error  {distribution}@{tgt}: PUT failed (rc={rc}): {out}",
                    err=True,
                )
            exit_code = 1
            continue
        if json_out:
            click.echo(
                json.dumps(
                    {
                        "distribution": distribution,
                        "branch": tgt,
                        "action": "set",
                        "ok": True,
                    }
                )
            )
        else:
            click.echo(f"ok    {distribution}@{tgt}: protection set")
    return exit_code


def register(ecosystem):
    @ecosystem.command(
        "set-branch-protection",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem set-branch-protection scitex-dev\n"
            "  $ scitex-dev ecosystem set-branch-protection scitex-dev --branch develop --execute\n"
            "  $ scitex-dev ecosystem set-branch-protection scitex-io --dry-run\n"
            "\n"
            "Applies the brand-wide branch-protection policy (lead msg\n"
            "a3c59d1a) to DISTRIBUTION's `develop` and/or `main` branch.\n"
            "Required contexts are computed live from the repo's published\n"
            "workflows so we never demand a check the repo cannot publish.\n"
            "--dry-run is the default; pass --execute to actually PUT.\n"
        ),
    )
    @click.argument("distribution")
    @click.option(
        "--branch",
        type=click.Choice(["develop", "main", "both"]),
        default="both",
        help="Which branch to protect. Default: both.",
    )
    @click.option(
        "--deletion-only",
        is_flag=True,
        help="Apply only the minimal un-deletable baseline (no required checks / "
        "enforce-admins) so CI's own pushes to develop are not blocked. This is "
        "the fleet-wide standard; omit for the full brand-wide policy.",
    )
    @click.option(
        "--execute",
        "-y",
        "--yes",
        "execute",
        is_flag=True,
        help="Actually PUT the protection rule. Without this, prints the "
        "planned PUT body and exits.",
    )
    @click.option(
        "--json",
        "json_out",
        is_flag=True,
        help="Emit one JSON object per branch instead of human-readable text.",
    )
    def ecosystem_set_branch_protection(
        distribution, branch, deletion_only, execute, json_out
    ):
        """Apply branch protection to DISTRIBUTION (or 'all' for the fleet).

        Pass `all` as DISTRIBUTION to roll out across every ECOSYSTEM repo.
        With --deletion-only this is the standard baseline that keeps every
        `develop` un-deletable without blocking CI's commit-back push.
        """
        targets = ["develop", "main"] if branch == "both" else [branch]
        dists = _all_distributions() if distribution == "all" else [distribution]

        exit_code = 0
        for dist in dists:
            rc = _apply_one(
                dist,
                targets,
                deletion_only=deletion_only,
                execute=execute,
                json_out=json_out,
            )
            exit_code = max(exit_code, rc)
        raise SystemExit(exit_code)

    @ecosystem.command(
        "unset-branch-protection",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem unset-branch-protection scitex-dev\n"
            "  $ scitex-dev ecosystem unset-branch-protection scitex-dev --execute\n"
            "\n"
            "Rollback for `set-branch-protection`. Deletes the protection\n"
            "rule on DISTRIBUTION's `develop` and/or `main` branch. --dry-run\n"
            "is the default; pass --execute to actually DELETE.\n"
        ),
    )
    @click.argument("distribution")
    @click.option(
        "--branch",
        type=click.Choice(["develop", "main", "both"]),
        default="both",
        help="Which branch to unprotect. Default: both.",
    )
    @click.option(
        "--execute",
        "-y",
        "--yes",
        "execute",
        is_flag=True,
        help="Actually DELETE the protection rule.",
    )
    @click.option("--json", "json_out", is_flag=True)
    def ecosystem_unset_branch_protection(distribution, branch, execute, json_out):
        """Remove branch protection on DISTRIBUTION (rollback for set-)."""
        owner_repo = _resolve_owner_repo(distribution)
        if owner_repo is None:
            click.echo(f"error: '{distribution}' not in ECOSYSTEM", err=True)
            raise SystemExit(2)

        targets = ["develop", "main"] if branch == "both" else [branch]
        exit_code = 0
        for tgt in targets:
            if not _branch_exists(owner_repo, tgt):
                if json_out:
                    click.echo(
                        json.dumps(
                            {"branch": tgt, "action": "skip", "reason": "no-branch"}
                        )
                    )
                else:
                    click.echo(
                        f"skip  {distribution}: branch '{tgt}' does not exist on origin",
                        err=True,
                    )
                continue
            if not execute:
                if json_out:
                    click.echo(json.dumps({"branch": tgt, "action": "dry-run"}))
                else:
                    click.echo(
                        f"DRY-RUN {distribution}@{tgt}: "
                        f"DELETE repos/{owner_repo}/branches/{tgt}/protection"
                    )
                continue
            rc, out = _gh_api("DELETE", f"repos/{owner_repo}/branches/{tgt}/protection")
            if rc != 0:
                if json_out:
                    click.echo(
                        json.dumps(
                            {
                                "branch": tgt,
                                "action": "error",
                                "rc": rc,
                                "stderr": out,
                            }
                        )
                    )
                else:
                    click.echo(
                        f"error  {distribution}@{tgt}: DELETE failed (rc={rc}): {out}",
                        err=True,
                    )
                exit_code = 1
                continue
            if json_out:
                click.echo(json.dumps({"branch": tgt, "action": "unset", "ok": True}))
            else:
                click.echo(f"ok    {distribution}@{tgt}: protection removed")
        raise SystemExit(exit_code)
