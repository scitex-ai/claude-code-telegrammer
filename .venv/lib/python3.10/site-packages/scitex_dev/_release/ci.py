#!/usr/bin/env python3
# Timestamp: 2026-03-27
# File: scitex_dev/ci.py

"""GitHub Actions CI checking for the SciTeX ecosystem.

Provides convenience APIs to check workflow status, wait for completion,
and verify PyPI publish across all ecosystem packages.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from .._core.config import DevConfig, load_config


@dataclass
class WorkflowRun:
    """A single GitHub Actions workflow run."""

    id: int
    name: str
    status: str  # queued, in_progress, completed
    conclusion: str | None  # success, failure, cancelled, None if running
    branch: str
    url: str

    @property
    def ok(self) -> bool:
        return self.conclusion == "success"

    @property
    def failed(self) -> bool:
        return self.conclusion == "failure"

    @property
    def running(self) -> bool:
        return self.status in ("queued", "in_progress")


@dataclass
class CIStatus:
    """CI status for a single package."""

    package: str
    repo: str
    runs: list[WorkflowRun] = field(default_factory=list)
    error: str | None = None

    @property
    def latest(self) -> WorkflowRun | None:
        return self.runs[0] if self.runs else None

    @property
    def ok(self) -> bool:
        return self.latest is not None and self.latest.ok

    @property
    def failed(self) -> bool:
        return self.latest is not None and self.latest.failed


def _gh_json(args: list[str], timeout: int = 15) -> list[dict[str, Any]]:
    """Run gh CLI and return JSON output."""
    import json

    result = subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else []


def get_workflow_runs(
    repo: str,
    workflow: str | None = None,
    limit: int = 3,
) -> list[WorkflowRun]:
    """Get recent workflow runs for a repository.

    Parameters
    ----------
    repo : str
        GitHub repo in "owner/name" format.
    workflow : str | None
        Workflow filename filter (e.g. "publish-pypi.yml"). None = all.
    limit : int
        Max runs to return.

    Returns
    -------
    list[WorkflowRun]
    """
    args = [
        "run",
        "list",
        "-R",
        repo,
        "--limit",
        str(limit),
        "--json",
        "databaseId,name,status,conclusion,headBranch,url",
    ]
    if workflow:
        args.extend(["-w", workflow])

    try:
        data = _gh_json(args)
    except Exception:
        return []

    return [
        WorkflowRun(
            id=r["databaseId"],
            name=r.get("name", ""),
            status=r.get("status", "unknown"),
            conclusion=r.get("conclusion"),
            branch=r.get("headBranch", ""),
            url=r.get("url", ""),
        )
        for r in data
    ]


def check_ci(
    packages: list[str] | None = None,
    config: DevConfig | None = None,
) -> dict[str, CIStatus]:
    """Check CI status for ecosystem packages.

    Parameters
    ----------
    packages : list[str] | None
        Package names. None = all ecosystem packages.
    config : DevConfig | None
        Configuration.

    Returns
    -------
    dict[str, CIStatus]
        {package_name: CIStatus}
    """
    if config is None:
        config = load_config()

    targets = (
        [p for p in config.packages if p.name in packages]
        if packages
        else config.packages
    )

    results: dict[str, CIStatus] = {}
    for pkg in targets:
        repo = pkg.github_repo
        if not repo:
            results[pkg.name] = CIStatus(
                package=pkg.name, repo="", error="no github_repo configured"
            )
            continue

        try:
            runs = get_workflow_runs(repo, limit=3)
            results[pkg.name] = CIStatus(package=pkg.name, repo=repo, runs=runs)
        except Exception as e:
            results[pkg.name] = CIStatus(package=pkg.name, repo=repo, error=str(e))

    return results


def check_pypi_publish(
    repo: str,
    workflow: str = "publish-pypi.yml",
) -> WorkflowRun | None:
    """Check the latest publish-pypi.yml workflow run.

    Parameters
    ----------
    repo : str
        GitHub repo in "owner/name" format.
    workflow : str
        Workflow filename.

    Returns
    -------
    WorkflowRun | None
        Latest run, or None if no runs found.
    """
    runs = get_workflow_runs(repo, workflow=workflow, limit=1)
    return runs[0] if runs else None


def wait_for_workflow(
    repo: str,
    workflow: str = "publish-pypi.yml",
    timeout: int = 600,
    poll_interval: int = 30,
) -> WorkflowRun | None:
    """Wait for a workflow to complete.

    Parameters
    ----------
    repo : str
        GitHub repo in "owner/name" format.
    workflow : str
        Workflow filename.
    timeout : int
        Max seconds to wait (default 600 = 10 min).
    poll_interval : int
        Seconds between polls (default 30).

    Returns
    -------
    WorkflowRun | None
        Final run state, or None on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = check_pypi_publish(repo, workflow)
        if run and not run.running:
            return run
        time.sleep(poll_interval)
    return None


def wait_all_pypi(
    packages: list[str] | None = None,
    config: DevConfig | None = None,
    timeout: int = 600,
    poll_interval: int = 30,
) -> dict[str, WorkflowRun | None]:
    """Wait for all PyPI publish workflows to complete.

    Parameters
    ----------
    packages : list[str] | None
        Package names. None = all with github_repo.
    config : DevConfig | None
        Configuration.
    timeout : int
        Max seconds to wait per package.
    poll_interval : int
        Seconds between polls.

    Returns
    -------
    dict[str, WorkflowRun | None]
        {package_name: final WorkflowRun or None on timeout}
    """
    if config is None:
        config = load_config()

    targets = (
        [p for p in config.packages if p.name in packages]
        if packages
        else config.packages
    )

    results: dict[str, WorkflowRun | None] = {}
    for pkg in targets:
        if not pkg.github_repo:
            continue
        results[pkg.name] = wait_for_workflow(
            pkg.github_repo,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    return results


def get_failing_packages(
    packages: list[str] | None = None,
    config: DevConfig | None = None,
) -> list[str]:
    """Return package names with failing CI.

    Parameters
    ----------
    packages : list[str] | None
        Package names. None = all.
    config : DevConfig | None
        Configuration.

    Returns
    -------
    list[str]
        Names of packages whose latest CI run failed.
    """
    statuses = check_ci(packages, config)
    return [name for name, st in statuses.items() if st.failed]


def verify_pypi_config(
    repo: str,
    workflow: str = "publish-pypi.yml",
) -> dict[str, Any]:
    """Check if a publish-pypi.yml workflow exists in the repo.

    Parameters
    ----------
    repo : str
        GitHub repo in "owner/name" format.
    workflow : str
        Expected workflow filename.

    Returns
    -------
    dict
        {repo, workflow_exists, workflow_name, needs_first_publish}
    """
    try:
        data = _gh_json(
            [
                "api",
                f"repos/{repo}/actions/workflows",
                "--jq",
                ".workflows[] | {name, path, state}",
            ]
        )
    except Exception:
        data = []

    # Check if any workflow matches
    workflows = data if isinstance(data, list) else [data] if data else []
    found = any(
        workflow in str(w.get("path", "")) for w in workflows if isinstance(w, dict)
    )

    return {
        "repo": repo,
        "workflow_exists": found,
        "workflow_name": workflow,
        "needs_first_publish": not found,
    }


def verify_all_pypi_configs(
    packages: list[str] | None = None,
    config: DevConfig | None = None,
) -> dict[str, dict[str, Any]]:
    """Check PyPI publish workflow config for all packages.

    Parameters
    ----------
    packages : list[str] | None
        Package names. None = all.
    config : DevConfig | None
        Configuration.

    Returns
    -------
    dict
        {package_name: {repo, workflow_exists, needs_first_publish}}
    """
    if config is None:
        config = load_config()

    targets = (
        [p for p in config.packages if p.name in packages]
        if packages
        else config.packages
    )

    results: dict[str, dict[str, Any]] = {}
    for pkg in targets:
        if not pkg.github_repo:
            results[pkg.name] = {
                "repo": "",
                "workflow_exists": False,
                "needs_first_publish": True,
            }
            continue
        results[pkg.name] = verify_pypi_config(pkg.github_repo)

    return results


def create_github_release(
    repo: str,
    tag: str,
    generate_notes: bool = True,
    confirm: bool = False,
) -> dict[str, Any]:
    """Create a GitHub release for a tag.

    Parameters
    ----------
    repo : str
        GitHub repo in "owner/name" format.
    tag : str
        Tag name (e.g. "v0.4.1").
    generate_notes : bool
        Auto-generate release notes from commits.
    confirm : bool
        If False (default), preview only.

    Returns
    -------
    dict
        {repo, tag, action, url, status}
    """
    if not confirm:
        return {
            "repo": repo,
            "tag": tag,
            "action": "would_create",
            "status": "dry_run",
        }

    args = ["release", "create", tag, "-R", repo]
    if generate_notes:
        args.append("--generate-notes")

    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return {
                "repo": repo,
                "tag": tag,
                "action": "created",
                "url": result.stdout.strip(),
                "status": "ok",
            }
        return {
            "repo": repo,
            "tag": tag,
            "action": "failed",
            "error": result.stderr.strip(),
            "status": "error",
        }
    except Exception as e:
        return {
            "repo": repo,
            "tag": tag,
            "action": "failed",
            "error": str(e),
            "status": "error",
        }


# EOF
