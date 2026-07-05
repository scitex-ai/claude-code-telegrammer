#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core ecosystem-wide credential rotation logic.

Public surface
--------------
- ``CREDENTIALS_PATH`` — local source (``~/.claude/.credentials.json``)
- ``CREDENTIALS_SLOT`` — un-prefixed GH Actions secret slot name
- ``SHA256_VAR``       — sidecar repo variable name
- ``validate_source``  — read+parse+expiry check; returns SourceState
- ``rotate_all``       — iterate the ECOSYSTEM registry and update each
                         repo whose sha256 sidecar differs from local

Design notes
------------
- ``gh`` is invoked directly via ``subprocess.run`` so we don't pull a
  hard dep on ``scitex-git``. The single-repo sac command can stay on
  scitex-git; this multiplexer is its own concern.
- The credential body is NEVER logged. Only sha256, byte count, and
  the secret slot name are surfaced.
- Errors are returned per-repo (``status='error'``) rather than raising,
  so one broken remote doesn't abort the rotation across 50+ repos.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .._ecosystem import ECOSYSTEM, get_local_path

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
CREDENTIALS_SLOT = "CLAUDE_CODE_CREDENTIALS_JSON"
SHA256_VAR = f"{CREDENTIALS_SLOT}_SHA256"


@dataclass(frozen=True)
class SourceState:
    """Outcome of validating the local credentials file."""

    content: str
    sha256: str
    byte_count: int


@dataclass
class RotateResult:
    """Per-repo rotation outcome."""

    package: str
    repo: str | None
    status: str  # unchanged | rotated | skipped | error | dry-run
    message: str = ""

    def is_error(self) -> bool:
        return self.status == "error"


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)


def validate_source(
    path: Path = CREDENTIALS_PATH,
    *,
    now_ms: Callable[[], int] = _now_ms,
) -> SourceState | None:
    """Return SourceState, or None if rotation should be a silent no-op.

    Silent-no-op (returns None) is reserved for the operator-on-a-fresh-
    -laptop / expired-token cases that should NOT spam every hour:

    - source file is missing
    - ``claudeAiOauth.expiresAt`` (or ``expires_at``) is in the past

    Raises ``ValueError`` for cases that DO deserve a loud error:

    - file present but doesn't parse as JSON
    - file parses but has no ``claudeAiOauth`` key
    """
    if not path.is_file():
        return None  # silent: no creds yet, operator hasn't logged in

    content = path.read_text()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc

    oauth = payload.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        raise ValueError(f"{path} has no .claudeAiOauth key")

    # Accept either camelCase or snake_case for forward compat with
    # whatever rev of the Claude Code client wrote the file.
    expires = oauth.get("expiresAt", oauth.get("expires_at"))
    if isinstance(expires, (int, float)):
        # Heuristic: values > 1e12 are ms-since-epoch, otherwise seconds.
        cutoff_ms = expires if expires > 1e12 else expires * 1000
        if cutoff_ms <= now_ms():
            return None  # silent: token expired, operator must re-login

    return SourceState(
        content=content,
        sha256=_sha256_hex(content),
        byte_count=len(content.encode("utf-8")),
    )


def _detect_repo_for_package(
    name: str,
    *,
    ecosystem: dict | None = None,
    local_path_lookup=None,
) -> str | None:
    """Return ``owner/repo`` for a package, preferring the local clone.

    ``ecosystem`` / ``local_path_lookup`` are injection hooks for tests so
    they don't need to monkey-patch module-level state.
    """
    if local_path_lookup is None:
        local_path_lookup = get_local_path
    if ecosystem is None:
        ecosystem = ECOSYSTEM
    local = local_path_lookup(name)
    if local is not None and (local / ".git").exists():
        try:
            out = subprocess.check_output(
                ["git", "-C", str(local), "remote", "get-url", "origin"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).strip()
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            out = ""
        if out:
            return _normalise_remote_url(out)
    # Fall back to the recorded registry URL.
    info = ecosystem.get(name) or {}
    repo = info.get("github_repo")
    return repo or None


def _normalise_remote_url(url: str) -> str:
    """git@github.com:o/r[.git] or https://github.com/o/r[.git] → o/r."""
    if url.startswith("git@"):
        path = url.split(":", 1)[1]
    elif "://" in url:
        path = url.split("://", 1)[1].split("/", 1)[1]
    else:
        path = url
    return path[:-4] if path.endswith(".git") else path


def _gh_get_variable(repo: str, name: str) -> str | None:
    """Return the value of a repo variable, or None if missing."""
    try:
        r = subprocess.run(
            ["gh", "variable", "get", name, "--repo", repo],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("'gh' CLI not found on PATH") from exc
    if r.returncode != 0:
        # gh returns non-zero both for "missing" and "real error"; treat
        # all as missing — the caller will then push a fresh value.
        return None
    out = r.stdout.strip()
    return out or None


def _gh_set_secret(repo: str, name: str, body: str) -> None:
    r = subprocess.run(
        ["gh", "secret", "set", name, "--repo", repo, "--body", body],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"gh secret set failed for {repo}: {r.stderr.strip() or r.stdout.strip()}"
        )


def _gh_set_variable(repo: str, name: str, value: str) -> None:
    r = subprocess.run(
        ["gh", "variable", "set", name, "--repo", repo, "--body", value],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"gh variable set failed for {repo}: {r.stderr.strip() or r.stdout.strip()}"
        )


def _rotate_one(
    package: str,
    source: SourceState,
    *,
    dry_run: bool,
    force: bool,
    ecosystem: dict | None = None,
    local_path_lookup=None,
) -> RotateResult:
    repo = _detect_repo_for_package(
        package, ecosystem=ecosystem, local_path_lookup=local_path_lookup
    )
    if not repo:
        return RotateResult(
            package=package, repo=None, status="skipped", message="no remote"
        )

    try:
        remote_sha = _gh_get_variable(repo, SHA256_VAR)
    except RuntimeError as exc:
        return RotateResult(
            package=package, repo=repo, status="error", message=str(exc)
        )

    if not force and remote_sha == source.sha256:
        return RotateResult(
            package=package,
            repo=repo,
            status="unchanged",
            message=f"sha256={source.sha256[:12]}…",
        )

    if dry_run:
        return RotateResult(
            package=package,
            repo=repo,
            status="dry-run",
            message=f"would rotate (local sha={source.sha256[:12]}…)",
        )

    try:
        _gh_set_secret(repo, CREDENTIALS_SLOT, source.content)
        _gh_set_variable(repo, SHA256_VAR, source.sha256)
    except RuntimeError as exc:
        return RotateResult(
            package=package, repo=repo, status="error", message=str(exc)
        )

    return RotateResult(
        package=package,
        repo=repo,
        status="rotated",
        message=f"sha256={source.sha256[:12]}…",
    )


def rotate_all(
    *,
    packages: Iterable[str] | None = None,
    only: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
    source_path: Path = CREDENTIALS_PATH,
    dry_run: bool = False,
    force: bool = False,
    ecosystem: dict | None = None,
    local_path_lookup=None,
) -> list[RotateResult]:
    """Rotate the credential across every (or a filtered set of) repo.

    Returns one ``RotateResult`` per package processed. Returns an
    empty list if the source is silently absent/expired — that is the
    "fresh laptop / expired token" exit-0 path, deliberately quiet.
    """
    if shutil.which("gh") is None:
        raise RuntimeError("'gh' CLI not found on PATH")

    source = validate_source(source_path)
    if source is None:
        return []

    eco = ecosystem if ecosystem is not None else ECOSYSTEM
    pkg_list = list(packages) if packages is not None else list(eco.keys())
    if only:
        only_set = set(only)
        pkg_list = [p for p in pkg_list if p in only_set]
    if exclude:
        excl = set(exclude)
        pkg_list = [p for p in pkg_list if p not in excl]

    return [
        _rotate_one(
            pkg,
            source,
            dry_run=dry_run,
            force=force,
            ecosystem=eco,
            local_path_lookup=local_path_lookup,
        )
        for pkg in pkg_list
    ]


# EOF
