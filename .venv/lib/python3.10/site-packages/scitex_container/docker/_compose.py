#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/docker/_compose.py
"""Docker Compose management — rebuild, restart, status."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scitex_container._compat import supports_return_as


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_compose_file(env: str, project_dir: Path | None) -> Path:
    """Locate a docker-compose file for the given environment.

    Search order:
    1. ``project_dir`` if provided.
    2. Walk upward from cwd until a compose file is found.

    File names tried (in order):
    - ``docker-compose.{env}.yml``
    - ``docker-compose.yml``
    - ``compose.yml``

    Parameters
    ----------
    env : str
        Environment name (e.g. ``"dev"``, ``"prod"``).
    project_dir : Path or None
        Explicit project directory to search first.

    Returns
    -------
    Path
        Absolute path to the found compose file.

    Raises
    ------
    FileNotFoundError
        If no compose file is found.
    """
    candidates = [
        f"docker-compose.{env}.yml",
        "docker-compose.yml",
        "compose.yml",
    ]

    search_dirs: list[Path] = []
    if project_dir is not None:
        search_dirs.append(Path(project_dir).resolve())

    # Walk upward from cwd
    current = Path.cwd().resolve()
    while True:
        search_dirs.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent

    for directory in search_dirs:
        for candidate in candidates:
            path = directory / candidate
            if path.is_file():
                return path

    raise FileNotFoundError(
        f"No docker-compose file found for env='{env}'.\n"
        f"Searched directories (in order): {[str(d) for d in search_dirs]}\n"
        f"Tried filenames: {candidates}"
    )


def _run(cmd: list[str], cwd: Path) -> int:
    """Run a command and stream output to stdout/stderr.

    Parameters
    ----------
    cmd : list[str]
        Command and arguments.
    cwd : Path
        Working directory.

    Returns
    -------
    int
        Exit code.
    """
    proc = subprocess.run(cmd, cwd=str(cwd))
    return proc.returncode


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@supports_return_as
def rebuild(env: str = "dev", project_dir: str | Path | None = None) -> int:
    """Rebuild Docker containers without using the cache.

    Runs: ``docker compose -f <compose_file> build --no-cache``

    Parameters
    ----------
    env : str
        Environment name used to locate the compose file.
    project_dir : str or Path or None
        Explicit directory containing the compose file.  When ``None``, the
        function walks upward from the current working directory.

    Returns
    -------
    int
        Exit code of the docker compose command (0 = success).
    """
    _project_dir = Path(project_dir).resolve() if project_dir else None
    compose_file = _find_compose_file(env=env, project_dir=_project_dir)
    cwd = compose_file.parent

    cmd = ["docker", "compose", "-f", str(compose_file), "build", "--no-cache"]
    return _run(cmd, cwd=cwd)


@supports_return_as
def restart(env: str = "dev", project_dir: str | Path | None = None) -> int:
    """Restart Docker containers (down then up).

    Runs: ``docker compose -f <compose_file> down``
    then: ``docker compose -f <compose_file> up -d``

    Parameters
    ----------
    env : str
        Environment name used to locate the compose file.
    project_dir : str or Path or None
        Explicit directory containing the compose file.

    Returns
    -------
    int
        Exit code of the final ``up -d`` command (0 = success).
        If ``down`` fails its exit code is returned instead.
    """
    _project_dir = Path(project_dir).resolve() if project_dir else None
    compose_file = _find_compose_file(env=env, project_dir=_project_dir)
    cwd = compose_file.parent

    down_rc = _run(
        ["docker", "compose", "-f", str(compose_file), "down"],
        cwd=cwd,
    )
    if down_rc != 0:
        return down_rc

    return _run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d"],
        cwd=cwd,
    )


@supports_return_as
def status(env: str = "dev", project_dir: str | Path | None = None) -> dict:
    """Get Docker container status for the given compose environment.

    Runs: ``docker compose -f <compose_file> ps --format json``

    Parameters
    ----------
    env : str
        Environment name used to locate the compose file.
    project_dir : str or Path or None
        Explicit directory containing the compose file.

    Returns
    -------
    dict
        Status information::

            {
                "compose_file": "/path/to/docker-compose.yml",
                "containers": [
                    {
                        "name": "myapp_web_1",
                        "state": "running",
                        "image": "myapp:latest",
                        "raw": {...},   # original JSON from docker compose ps
                    },
                    ...
                ],
                "returncode": 0,
            }
    """
    import json

    _project_dir = Path(project_dir).resolve() if project_dir else None
    compose_file = _find_compose_file(env=env, project_dir=_project_dir)
    cwd = compose_file.parent

    proc = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "ps", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )

    containers: list[dict] = []
    if proc.returncode == 0 and proc.stdout.strip():
        raw_output = proc.stdout.strip()
        # docker compose ps --format json may output one JSON object per line
        # or a single JSON array depending on the version.
        try:
            parsed = json.loads(raw_output)
            if isinstance(parsed, list):
                raw_list = parsed
            else:
                raw_list = [parsed]
        except json.JSONDecodeError:
            # Try line-by-line
            raw_list = []
            for line in raw_output.splitlines():
                line = line.strip()
                if line:
                    try:
                        raw_list.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        for item in raw_list:
            containers.append(
                {
                    "name": item.get("Name", item.get("name", "")),
                    "state": item.get("State", item.get("state", "")),
                    "image": item.get("Image", item.get("image", "")),
                    "raw": item,
                }
            )

    return {
        "compose_file": str(compose_file),
        "containers": containers,
        "returncode": proc.returncode,
    }


# EOF
