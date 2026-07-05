#!/usr/bin/env python3
# Timestamp: 2026-04-28
# File: scitex_dev/_release_publisher.py

"""Smart `git tag` → PyPI publish helper.

The 2026-04-28 footgun: 13 ecosystem packages use ``release: published``
in their publish-pypi.yml, while 58 use ``push: tags: ['v*']``. After
``git tag v<X> && git push --tags``:

- tag-trigger workflows publish immediately
- release-trigger workflows do NOTHING — the operator must also run
  ``gh release create v<X>`` to fire the publish

Operators (and agents) forget the second step. This module bundles the
right sequence per repo into one call, idempotently.

Public API
----------

- ``publish_release(repo, version, notes=None, dry_run=False)``
  — detects the trigger, pushes the tag if needed, creates the GH
  release if needed. Returns a structured ``PublishResult`` with the
  steps it ran.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PublishResult:
    repo: Path
    version: str
    trigger: str | None  # "release" | "tags" | None
    steps_run: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"publish v{self.version} on {self.repo} (trigger={self.trigger})"]
        for s in self.steps_run:
            lines.append(f"  RAN     {s}")
        for s in self.skipped:
            lines.append(f"  SKIP    {s}")
        for s, why in self.failed:
            lines.append(f"  FAIL    {s}: {why}")
        return "\n".join(lines)


def _detect_trigger(repo: Path) -> str | None:
    wf = repo / ".github" / "workflows" / "publish-pypi.yml"
    if not wf.is_file():
        return None
    try:
        text = wf.read_text(encoding="utf-8")
    except OSError:
        return None
    if re.search(r"^\s*release:\s*$", text, re.MULTILINE):
        return "release"
    if re.search(r"^\s*tags:\s*$", text, re.MULTILINE):
        return "tags"
    return None


def _git(
    repo: Path, *args: str, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def _gh_release_exists(slug: str, version: str) -> bool:
    r = subprocess.run(
        ["gh", "release", "view", f"v{version}", "-R", slug, "--json", "tagName"],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def _gh_repo_slug(repo: Path) -> str | None:
    r = _git(repo, "remote", "get-url", "origin")
    if r.returncode != 0:
        return None
    url = r.stdout.strip()
    m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def publish_release(
    repo: Path, version: str, notes: str | None = None, dry_run: bool = False
) -> PublishResult:
    """Tag (if missing), push, and create GH release (if needed)."""
    trigger = _detect_trigger(repo)
    rep = PublishResult(repo=repo, version=version, trigger=trigger)

    # 1. Ensure the tag exists locally.
    has_tag = _git(repo, "tag", "--list", f"v{version}").stdout.strip()
    if not has_tag:
        if dry_run:
            rep.steps_run.append(f"would: git tag v{version}")
        else:
            r = _git(repo, "tag", f"v{version}")
            if r.returncode != 0:
                rep.failed.append(("git tag", r.stderr.strip()))
                return rep
            rep.steps_run.append(f"git tag v{version}")
    else:
        rep.skipped.append(f"tag v{version} already exists")

    # 2. Push tags.
    if dry_run:
        rep.steps_run.append("would: git push --tags")
    else:
        r = _git(
            repo,
            "-c",
            "core.hooksPath=/dev/null",
            "push",
            "--tags",
        )
        # `--tags` with already-pushed tags returns 0 ("Everything up-to-date");
        # rejected because-tag-exists-on-remote is also benign for our purpose.
        rep.steps_run.append("git push --tags")

    # 3. If trigger is `release`, create the GH release (idempotent).
    if trigger == "release":
        slug = _gh_repo_slug(repo)
        if not slug:
            rep.failed.append(("gh release", "could not derive owner/repo slug"))
            return rep
        if _gh_release_exists(slug, version):
            rep.skipped.append(f"gh release v{version} already exists")
        else:
            if dry_run:
                rep.steps_run.append(f"would: gh release create v{version}")
            else:
                args = [
                    "gh",
                    "release",
                    "create",
                    f"v{version}",
                    "-R",
                    slug,
                    "--title",
                    f"v{version}",
                ]
                if notes:
                    args += ["--notes", notes]
                else:
                    args += ["--generate-notes"]
                r = subprocess.run(args, capture_output=True, text=True)
                if r.returncode != 0:
                    rep.failed.append(("gh release create", r.stderr.strip()))
                else:
                    rep.steps_run.append(f"gh release create v{version}")
    else:
        rep.skipped.append(
            f"trigger={trigger}; tag-push alone fires the publish workflow"
        )

    return rep


__all__ = ["PublishResult", "publish_release"]
