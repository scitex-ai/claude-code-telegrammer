#!/usr/bin/env python3
# Timestamp: 2026-03-27
# File: scitex_dev/deploy.py

"""Deployment helpers for custom host operations."""

from __future__ import annotations

import subprocess
from typing import Any


def deploy_scitex_hub(
    host: str = "nas",
    branch: str = "develop",
    confirm: bool = False,
) -> dict[str, Any]:
    """Deploy scitex-hub on a remote host.

    Stops Docker, pulls code, builds Vite, restarts Docker.
    Docker must be stopped before Vite build to avoid OOM.

    Parameters
    ----------
    host : str
        SSH host name (default "nas").
    branch : str
        Git branch to pull (default "develop").
    confirm : bool
        If False (default), preview commands only.

    Returns
    -------
    dict
        {host, commands, outputs, status}
    """
    commands = [
        f"cd ~/proj/scitex-cloud && git pull origin {branch}",
        "cd ~/proj/scitex-cloud && docker compose stop",
        "cd ~/proj/scitex-cloud && npm install && npx vite build",
        "cd ~/proj/scitex-cloud && docker compose up -d",
    ]

    if not confirm:
        return {
            "host": host,
            "commands": [f'ssh {host} "{cmd}"' for cmd in commands],
            "action": "dry_run",
            "status": "dry_run",
        }

    outputs = []
    for cmd in commands:
        try:
            result = subprocess.run(
                ["ssh", host, cmd],
                capture_output=True,
                text=True,
                timeout=300,
            )
            outputs.append(
                {
                    "command": cmd,
                    "returncode": result.returncode,
                    "stdout": result.stdout.strip()[-500:] if result.stdout else "",
                    "stderr": result.stderr.strip()[-500:] if result.stderr else "",
                    "status": "ok" if result.returncode == 0 else "error",
                }
            )
            if result.returncode != 0:
                return {
                    "host": host,
                    "outputs": outputs,
                    "failed_at": cmd,
                    "status": "error",
                }
        except subprocess.TimeoutExpired:
            outputs.append({"command": cmd, "status": "timeout"})
            return {
                "host": host,
                "outputs": outputs,
                "failed_at": cmd,
                "status": "timeout",
            }

    return {
        "host": host,
        "outputs": outputs,
        "status": "ok",
    }


def verify_production(
    url: str = "https://scitex.ai",
    timeout: int = 10,
) -> dict[str, Any]:
    """Check if production URL is responding.

    Parameters
    ----------
    url : str
        URL to check.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    dict
        {url, status_code, status}
    """
    import urllib.request

    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {
                "url": url,
                "status_code": resp.status,
                "status": "ok" if resp.status == 200 else "warning",
            }
    except Exception as e:
        return {
            "url": url,
            "status_code": None,
            "error": str(e),
            "status": "error",
        }


# EOF
