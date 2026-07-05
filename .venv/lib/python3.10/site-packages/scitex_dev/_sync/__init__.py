"""Ecosystem package sync — local⇄remote propagation + tag pushes.

Module map:
- `_local`  — sync_all / sync_host / sync_local + ssh/rsync helpers
- `_remote` — pull_local / remote_commit / remote_diff (reverse direction)
- `_tags`   — sync_tags (push local v* tags to origin per package)
"""

from __future__ import annotations

from ._local import (
    _build_ssh_args,
    _build_sync_commands,
    _get_host_packages,
    sync_all,
    sync_host,
    sync_local,
)
from ._remote import pull_local, remote_commit, remote_diff
from ._tags import sync_tags

__all__ = [
    "sync_all",
    "sync_host",
    "sync_local",
    "sync_tags",
    "pull_local",
    "remote_commit",
    "remote_diff",
]
