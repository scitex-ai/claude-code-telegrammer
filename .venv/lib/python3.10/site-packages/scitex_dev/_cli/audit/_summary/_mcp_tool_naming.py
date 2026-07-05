"""§2 / §5 — MCP tool-name discipline + skills-pair presence.

Extracted from `_mcp_audit.py` to keep the orchestrator under the
per-file line budget. Mirrors the existing §6 split (`_mcp_parity.py`).

Re-exported from `_mcp_audit` so external importers (and the test suite,
which imports the names directly from `_mcp_audit`) keep working
unchanged.
"""

from __future__ import annotations

import re

from ._audit import Violation
from ._mcp_names import _short_name


# Banned synonyms — same "Avoid" column as the CLI catalog.
_TOOL_NAME_SYNONYMS: dict[str, str] = {
    "ls": "list",
    "rm": "delete",
    "drop": "delete",
    "destroy": "delete",
    "enumerate": "list",
    "display": "show",
    "print": "show",
    "cat": "show",
    "view": "show",
    "new": "create",
    "make": "create",
    "edit": "update",
    "modify": "update",
}

# Verbs whose object is implicit (passed as a parameter) — `io_save`, `audio_speak`,
# `stats_run` — bare `<pkg>_<verb>` is acceptable per the §2 examples table.
_OBJECT_FROM_PARAM_VERBS = {
    "save",
    "load",
    "read",
    "write",
    "fetch",
    "download",
    "upload",
    "speak",
    "say",
    "play",
    "render",
    "compose",
    "plot",
    "build",
    "run",
    "execute",
    "exec",
    "compile",
    "convert",
    "import",
    "export",
    "send",
    "publish",
    "deploy",
    "ship",
    "init",
    "start",
    "stop",
    "validate",
    "check",
    "test",
    "lint",
    "format",
    "audit",
    "sync",
    "pull",
    "push",
    "commit",
    "open",
    "close",
    "reset",
    "restore",
}

# Verbs that need a noun in the tool name (object isn't implicit).
_VERBS_NEED_NOUN = {
    "list",
    "show",
    "get",
    "find",
    "search",
    "describe",
    "inspect",
    "delete",
    "remove",
    "purge",
    "create",
    "add",
    "update",
    "edit",
    "rename",
    "move",
}


_VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _check_tool_naming(
    package: str, tool_names: list[str], out: list[Violation]
) -> None:
    """§2 — `<pkg>_<verb>_<noun>` snake_case + no banned synonyms / shapes."""
    short = _short_name(package)
    expected_prefix = f"{short}_"

    for raw in tool_names:
        # snake_case sanity
        if not _VALID_NAME.match(raw):
            out.append(
                Violation(
                    f"{package}::{raw}",
                    "§2",
                    f"tool name '{raw}' not snake_case (expected lowercase + underscores only)",
                )
            )
            continue

        # Double-prefix detection (e.g. dev_dev_bulk_rename after a bad mount)
        if raw.startswith(f"{short}_{short}_"):
            out.append(
                Violation(
                    f"{package}::{raw}",
                    "§1",
                    f"double-prefix '{short}_{short}_*' — likely a Convention A "
                    "standalone whose tools already include the package prefix",
                )
            )
            continue

        # The tool name as visible from the umbrella must start with `<short>_`.
        # Standalone-source names omit it under Convention A (mount adds it);
        # we only check the prefix when the name is already prefixed.
        if "_" not in raw:
            out.append(
                Violation(
                    f"{package}::{raw}",
                    "§2",
                    f"tool name '{raw}' has no verb_noun split — single-token "
                    "tools are forbidden; use `<verb>_<noun>` even for read tools",
                )
            )
            continue

        # If the name is prefixed, strip and inspect the verb_noun tail.
        body = raw[len(expected_prefix) :] if raw.startswith(expected_prefix) else raw
        parts = body.split("_")
        # Bare-verb name `<pkg>_<verb>` is allowed when the verb naturally takes
        # its object as a parameter (`io_save`, `audio_speak`). Only flag when
        # the verb belongs to the "needs-noun" set (`list`, `show`, `delete`, …).
        if len(parts) < 2:
            verb = parts[0]
            # Only flag when the verb genuinely needs a noun (`list`, `show`,
            # `delete`, …). Bare `<pkg>_<verb>` is fine when the verb takes
            # its object as a parameter (`io_save`, `audio_speak`, `audio_transcribe`).
            if verb in _VERBS_NEED_NOUN:
                out.append(
                    Violation(
                        f"{package}::{raw}",
                        "§2",
                        f"tool name '{raw}' uses bare verb '{verb}' which needs "
                        f"a noun — use '{expected_prefix}{verb}_<noun>' "
                        f"(e.g. '{expected_prefix}{verb}_packages')",
                    )
                )
            continue

        verb = parts[0]
        if verb in _TOOL_NAME_SYNONYMS:
            preferred = _TOOL_NAME_SYNONYMS[verb]
            out.append(
                Violation(
                    f"{package}::{raw}",
                    "§2",
                    f"banned synonym verb '{verb}' — use '{preferred}' "
                    f"(rename to '{expected_prefix}{preferred}_{'_'.join(parts[1:])}')",
                )
            )

        # Double-underscore typo class
        if "__" in raw:
            out.append(
                Violation(
                    f"{package}::{raw}",
                    "§2",
                    f"tool name '{raw}' has '__' — typo class, use single underscore",
                )
            )


def _check_skills_pair(
    package: str, tool_names: set[str], out: list[Violation]
) -> None:
    """§5 — `<pkg>_skills_list` and `<pkg>_skills_get` must exist."""
    short = _short_name(package)
    for required in (f"{short}_skills_list", f"{short}_skills_get"):
        # Tools may be registered with or without the prefix depending on
        # convention; accept either.
        bare = required[len(short) + 1 :]
        if required not in tool_names and bare not in tool_names:
            out.append(
                Violation(
                    package,
                    "§5",
                    f"missing required skills tool '{required}' "
                    f"(or '{bare}' under Convention A standalone source)",
                )
            )
