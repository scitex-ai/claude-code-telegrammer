#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/docker/_mounts.py
"""Docker volume mount configuration for development and production."""

from __future__ import annotations

from pathlib import Path

from scitex_container._compat import supports_return_as


@supports_return_as
def get_dev_mounts(repos: list[dict]) -> list[str]:
    """Generate Docker volume mount strings for development repositories.

    Each entry in ``repos`` should have at minimum a ``"host"`` key with the
    host-side path, and a ``"container"`` key with the container-side path.
    An optional ``"mode"`` key (``"ro"`` or ``"rw"``) defaults to ``"ro"``.

    Parameters
    ----------
    repos : list[dict]
        Repository mount specifications::

            [
                {"host": "../../scitex-python", "container": "/scitex-python"},
                {"host": "/abs/path/to/myrepo", "container": "/myrepo", "mode": "rw"},
            ]

        ``"host"`` paths may be absolute or relative; relative paths are
        returned as-is so that Docker Compose can resolve them relative to
        the compose file location.

    Returns
    -------
    list[str]
        Volume strings suitable for use in a Docker Compose ``volumes`` list
        or as ``-v`` arguments to ``docker run``::

            [
                "./../../scitex-python:/scitex-python:ro",
                "/abs/path/to/myrepo:/myrepo:rw",
            ]
    """
    mounts: list[str] = []

    for repo in repos:
        host_raw = repo.get("host", "")
        container = repo.get("container", "")
        mode = repo.get("mode", "ro")

        if not host_raw or not container:
            continue

        host_path = Path(host_raw)
        # Preserve relative paths as-is (Docker Compose resolves them);
        # for absolute paths use the string directly.
        if host_path.is_absolute():
            host_str = str(host_path)
        else:
            # Normalise without resolving (keep relative)
            host_str = str(host_path)

        mounts.append(f"{host_str}:{container}:{mode}")

    return mounts


# EOF
