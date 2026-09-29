# File: src/claude_code_telegrammer/_telegram_hooks.py
"""claude-code-telegrammer's own Telegram guardrail DECLARATIONS.

CCT declares the rules that protect its own surface -- operator-facing
Telegram delivery -- it does not install them. scitex-dev discovers this
provider through the ``scitex_dev.hooks`` entry-point group and applies the
rows centrally, the same split every other ``scitex_dev.*`` group uses. The
leaf never installs anything itself.

The ``scitex_dev.hooks`` import is LAZY (inside ``provide_hooks``) so a
scitex-dev that predates the hooks contract does not break the entry point's
import-time metadata (same idiom as scitex-agent-container's
``_claude_hooks_plugin`` and its ``scitex_dev.jobs`` provider).

DECLARE-THEN-MOVE. Rules 1-3 are enforced in-process by the TypeScript
delivery path, which has no Python binding by construction, so they are
declared with ``implemented_in`` naming the TS file that enforces them
today. Rule 4's script lives at the repo-root ``hooks/`` tree, outside the
Python package, so it is likewise declared with ``implemented_in``; moving
the implementation under the package (the wheel already force-includes
``ts/`` the same way) is the follow-on, deliberately not bundled here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from scitex_dev.hooks import HookRule

_PROVIDER = "claude-code-telegrammer"


def provide_hooks() -> tuple[HookRule, ...]:
    """Hook rules CCT declares about its own delivery surface."""
    from scitex_dev.hooks import HookRule

    return (
        HookRule(
            id="telegrammer.reply-directive-on-delivery",
            rule=(
                "Every CCT delivery carries the reply directive: the "
                "operator is answered over CCT/Telegram, never only "
                "in-session."
            ),
            reason=(
                "Operator order 2026-09-28: agents repeatedly failed to "
                "answer over CCT on memory and spec prompts alone, and the "
                "operator reads on a phone with no terminal access. The "
                "content string is the only carrier guaranteed to reach "
                "every harness, so the directive rides there, appended to "
                "every delivery (commit dfc5d76)."
            ),
            event="notification",
            severity="advise",
            matches=("cct-delivery",),
            provider=_PROVIDER,
            implemented_in=(
                "claude-code-telegrammer:ts/lib/handle-update.ts"
            ),
            bypass="CCT_REPLY_DIRECTIVE=0",
        ),
        HookRule(
            id="telegrammer.long-target-truncation-512",
            rule=(
                "Cut a long in-reply-to target at 1024 chars, mark it "
                "truncated_from=<N>, and direct the reader to get_history "
                "for the rest."
            ),
            reason=(
                "The operator answers one-word replies against the target "
                "quoted in the delivery; an unbounded quote blows the "
                "phone screen and the context that must hold the reply. "
                "Truncation with a recovery pointer keeps the reference "
                "usable instead of silently dropping it."
            ),
            event="notification",
            severity="advise",
            matches=("cct-delivery",),
            provider=_PROVIDER,
            implemented_in=(
                "claude-code-telegrammer:ts/telegram-server.ts"
            ),
        ),
        HookRule(
            id="telegrammer.no-bare-issue-number",
            rule=(
                "Every #NNN in an operator-facing message carries an "
                "immediate label in the same clause; bare numbers are "
                "rejected before Telegram delivery."
            ),
            reason=(
                "He reads on a phone, cannot follow a link, and the number "
                "alone says nothing about what changed. The validator "
                "rejects rather than rewrites: guessing a title would put "
                "words in the operator's mouth."
            ),
            event="notification",
            severity="deny",
            matches=("cct-delivery",),
            provider=_PROVIDER,
            implemented_in=(
                "claude-code-telegrammer:ts/lib/outbound-style.ts"
            ),
        ),
        HookRule(
            id="telegrammer.background-subagents",
            rule=(
                "A telegram-role agent runs every subagent (Task) call with "
                "run_in_background=true; a foreground Task call is blocked."
            ),
            reason=(
                "The Telegram agent's message loop must never block on a "
                "subagent: a foregrounded Task stalls inbound delivery for "
                "the whole run, which is exactly the silence the operator "
                "reads as a dead agent. Role-gated so worker agents are "
                "unaffected."
            ),
            event="pre-tool-use",
            severity="deny",
            matches=("Task",),
            provider=_PROVIDER,
            implemented_in=(
                "claude-code-telegrammer:hooks/"
                "enforce_background_subagents.sh"
            ),
        ),
    )


__all__ = [
    "provide_hooks",
]
