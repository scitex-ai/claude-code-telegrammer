"""Ecosystem-wide Claude Code credential rotation.

Multiplexes ``~/.claude/.credentials.json`` to the GitHub Actions secret
slot ``CLAUDE_CODE_CREDENTIALS_JSON`` (with sha256 sidecar variable
``CLAUDE_CODE_CREDENTIALS_JSON_SHA256``) across every package in the
SciTeX ecosystem registry.

Distinct from the single-repo ``sac dev upload-credentials-to-github``
command — that one writes the package-prefixed ``SAC_…`` slot. This
module uses the canonical un-prefixed name shared by every scitex
package that consumes Claude Code OAuth.
"""

from __future__ import annotations

from ._rotate import (
    CREDENTIALS_PATH,
    CREDENTIALS_SLOT,
    SHA256_VAR,
    RotateResult,
    rotate_all,
    validate_source,
)

__all__ = [
    "CREDENTIALS_PATH",
    "CREDENTIALS_SLOT",
    "SHA256_VAR",
    "RotateResult",
    "rotate_all",
    "validate_source",
]
