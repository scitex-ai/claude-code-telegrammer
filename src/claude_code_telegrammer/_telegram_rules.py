#!/usr/bin/env python3
# Timestamp: "2026-08-12 (OP-PRIO-FMT rule 2 — extracted to one place)"
# Owner: claude_code_telegrammer._telegram_rules (packaged canonical predicate)
#
# THE RULE, IN ONE PLACE. Operator 2026-08-12:
#
#   「mcp も同じですね。同じルールなので、ルールは一つの場所に、
#     shell 用の hook と mcp のフィルタで同じルールを適用させて
#     ssot に、が良いかと」
#
# Two consumers, one rule:
#
#   1. the shell hook ``enforce_telegram_no_bare_issue.sh``, which
#      Claude Code fires as a PreToolUse gate on the reply tool; and
#   2. the MCP-side filter inside claude-code-telegrammer, which guards
#      the rails Claude Code never sees (the CLI ``send`` mode, and the
#      ``edit_message`` / ``send_document`` tools).
#
# Both call THIS module. Neither formats its own wording — the refusal
# text is returned from here, because the wording IS the fix
# instruction the operator reads on his phone, and two paths that
# format their own will drift. A rule enforced on one path and absent
# on the other is exactly how a bare number reaches him anyway.
#
# CALLING IT
#   in-process (Python):  from _telegram_rules import check_message
#   subprocess (any lang, e.g. the TypeScript MCP server):
#       echo -n "<message text>" | python3 _telegram_rules.py --text-stdin
#           -> stdout: {"ok": true}  |  {"ok": false, "token": "#589",
#                                        "excerpt": "...", "message": "..."}
#           -> exit 0 always (transport succeeded); read "ok".
#   hook adapter (Claude Code PreToolUse JSON on stdin):
#       python3 _telegram_rules.py --hook-json
#           -> exit 0 allow / exit 2 block (+ refusal text on stderr)
#
# ------------------------------------------------------------------
# OP-PRIO-FMT rule 2 (operator 2026-06-09, TIGHTENED 2026-08-11): a
# Telegram message MUST NOT carry an issue/PR number the operator
# cannot read. He reads on a phone: he cannot follow a link, and the
# number alone tells him nothing about what changed.
#
#   2026-08-11 「それだと何が何だか私にとってはわからないので、必ず
#   中身を私がわかるようにディスクリプティブな説明をつけて欲しい」
#   ... and the format, in his words: 「ナンバーの後に ( をつけて説明
#   する、っていうのをルールにしてください」
#
# WHY THIS WAS REWRITTEN. The 2026-06-09 implementation only blocked a
# message that reduced ENTIRELY to bare ``#NNN`` tokens. A number
# embedded in a sentence — the overwhelmingly common case — passed
# untouched. On 2026-08-11 an agent sent a line containing ``#970`` with
# no description, it went through, and the operator asked why the rule
# was not enforced. That is the recurring fleet shape: A GUARD WHOSE
# TRIGGER CONDITION IS NARROWER THAN ITS STATED RULE READS AS
# ENFORCEMENT WHILE ENFORCING ALMOST NOTHING.
#
# THE RULE NOW ENFORCED. Every ``#NNN`` token anywhere in the message
# must be immediately followed by a parenthetical description. Both the
# ASCII ``(`` and the full-width ``（`` are accepted — the operator
# writes Japanese and a Japanese IME produces the full-width form. A
# single run of spaces/tabs/ideographic-space between the number and the
# paren is allowed, and the parenthetical must be COMPLETE on the same
# clause — matching delimiters, closed before any line terminator — holding
# at least one non-space, non-numeric character (``#970 ()`` describes
# nothing, and neither does ``#970 (970)``). Dash/colon substitutes,
# unclosed parentheses and newline-split descriptions are refused
# (tightened 2026-10-03; prior revisions accepted unclosed/numeric-only).
#
#   #970（グループ判定がスペックを読む）    accept
#   #970 (group authority reads the spec)   accept
#   #970 の話ではなく…                      REFUSE
#   …見つかった #578、これは…                REFUSE
#
# FIVE DELIBERATE DECISIONS (documented so a reader can disagree with
# the choice rather than guess whether it was one). 1-3 are the
# original author's, verbatim; 4-5 were added 2026-08-12 to close two
# false positives that would have got the whole rule switched off.
#
#   1. URLs ARE NOT REFERENCES. A link is blanked out before scanning,
#      so ``…/pull/970`` (a path segment, no ``#`` at all) and a real
#      ``#`` fragment such as ``…/pull/970#issuecomment-123`` or
#      ``…/page#123`` never trip the rule. The operator cannot follow a
#      link on his phone either, but a URL is not a token pretending to
#      be a description — it is self-evidently a link, and rewriting it
#      is not what he asked for. Blanking preserves offsets (NUL fill)
#      so the refusal can still quote the right part of the message.
#
#   2. A REPEATED REFERENCE INHERITS THE FIRST DESCRIPTION. If ``#970
#      (…)`` is described once, a later bare ``#970`` in the SAME
#      message is accepted. The rule exists so the operator can read the
#      message and know what the number means; once the description is
#      on the page he is already reading, demanding it again would force
#      padding like ``#970（同じPR）`` — exactly the unreadable noise the
#      rule was written to remove. The allowance is strictly
#      LEFT-TO-RIGHT, because he reads top to bottom: a bare ``#970``
#      BEFORE its description is still refused.
#
#   3. A REPO NAME IS NOT A DESCRIPTION. ``scitex-dev #578`` is refused
#      exactly like a naked ``#578``; ``owner/repo#578`` likewise. The
#      repo says where to look, not what happened.
#
#   4. A ``#`` GLUED TO LETTERS IS A COLOUR, NOT A REFERENCE. ``#589abc``
#      is a hex colour and must never be refused. The digits must not be
#      followed by an ASCII alphanumeric. Deliberately ASCII-only, not
#      ``\\w``: Python's ``\\w`` matches CJK, so a ``\\w`` guard would
#      also swallow ``#970の話`` — a REAL bare reference written without
#      a space, which must still be refused. ``#fff`` never matched in
#      the first place (no digits). A six-digit ALL-NUMERIC colour
#      ``#123456`` is indistinguishable from an issue number and is
#      still treated as a reference; that is accepted as the rarer
#      case in an operator report, and ``CC_ALLOW_BARE_ISSUE=1`` covers
#      it. This matters more than it looks: a gate that fires on a hex
#      colour gets switched off by the first person it inconveniences,
#      and then the real rule is gone too.
#
#   5. CODE IS DATA, NOT PROSE. A number inside a fenced block or an
#      inline code span is being SHOWN, not cited — ``the token `#589`
#      is data`` is not a claim about PR 589. Code is blanked with the
#      same NUL fill as URLs, for the same two reasons: a code span
#      cannot bridge a number to a parenthesis outside it, and offsets
#      into the original text stay valid for the excerpt.
#
# FAIL-OPEN on any parse error or unexpected payload shape.
# Escape: CC_ALLOW_BARE_ISSUE=1.

from __future__ import annotations

import json
import os
import re
import sys

__all__ = ["ESCAPE_ENV", "HOOK_INPUT_VERSION", "Verdict", "check_message"]

HOOK_INPUT_VERSION = "cct.telegram-hook-input/v1"

#: Rare one-off override, honoured by every adapter.
ESCAPE_ENV = "CC_ALLOW_BARE_ISSUE"

# Blank every URL / code span to NULs before scanning. NUL (not space)
# so neither a link nor a code span can bridge a number to a
# parenthesis that follows it, and same-length so offsets into the
# ORIGINAL text stay valid for the excerpt.
_URL = re.compile(r"(?:https?://|ftp://|www\.)\S+", re.IGNORECASE)
_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_CODE_SPAN = re.compile(r"`[^`\n]*`")

# A reference is '#' + digits, NOT preceded by '&' (the HTML numeric
# entity '&#8212;' is a dash, not a PR) and NOT followed by an ASCII
# alphanumeric (decision 4 — hex colours).
_REFERENCE = re.compile(r"(?<!&)#(\d+)(?![0-9A-Za-z])")

# Line terminators that must never split a number from its description.
# Named (never literal) so no invisible character enters this source file.
_LS = chr(0x2028)
_PS = chr(0x2029)
_CLAUSE_BREAKS = ("\n", "\r", _LS, _PS)

# ...immediately followed by (optional horizontal space then) a COMPLETE
# same-clause parenthetical: matching ASCII or full-width delimiters, closed
# before any line terminator, holding at least one non-space, non-numeric
# character (full-width digits carry no meaning either; ``\d`` already
# covers them). Dash/colon substitutes, unclosed or empty parentheses and
# newline-split descriptions are refused by construction below.
_OPEN = re.compile(r"[ \t　]*(\(|（)")
_CLOSE_FOR = {"(": ")", "（": "）"}
_CONTENTLESS = re.compile(r"[\s\d._()[\]{}:;,#/\\-]")


class Verdict:
    """The single answer both adapters render.

    ``ok`` is the whole decision. ``message`` is the operator-facing
    refusal text — no caller composes its own, so the shell hook and
    the MCP filter cannot drift in what they tell the sender to do.
    """

    __slots__ = ("excerpt", "message", "ok", "token")

    def __init__(self, ok, token="", excerpt="", message=""):
        self.ok = ok
        self.token = token
        self.excerpt = excerpt
        self.message = message

    def as_dict(self):
        if self.ok:
            return {"ok": True}
        return {
            "ok": False,
            "token": self.token,
            "excerpt": self.excerpt,
            "message": self.message,
        }

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"Verdict(ok={self.ok!r}, token={self.token!r})"


_OK = Verdict(True)


def _strict_span(scan, pos):
    """(inner_text, end_index) of a complete same-clause parenthetical at pos.

    None when no opening paren follows, when any line terminator or a
    mismatched paren precedes the matching close, when the close never
    comes, or when the content is empty or numeric-only. Never invents or
    rewrites text; it only measures what is there.
    """
    opened = _OPEN.match(scan, pos)
    if not opened:
        return None
    close = _CLOSE_FOR[opened.group(1)]
    chars = []
    for char in scan[opened.end():]:
        if char in _CLAUSE_BREAKS:
            return None
        if char == close:
            inner = "".join(chars)
            if _CONTENTLESS.sub("", inner) == "":
                return None
            return inner, opened.end() + len("".join(chars)) + 1
        if char in "()（）":
            return None
        chars.append(char)
    return None


def _blank(text):
    """NUL-fill URLs and code, preserving length and therefore offsets."""

    def nul(match):
        return "\x00" * len(match.group(0))

    scan = _URL.sub(nul, text)
    scan = _FENCE.sub(nul, scan)
    scan = _CODE_SPAN.sub(nul, scan)
    return scan


def _refusal(token, excerpt):
    return (
        "BLOCKED by enforce_telegram_no_bare_issue.sh: the message contains "
        f"{token}, which is not followed by a description.\n\n"
        f"  found: {excerpt}\n\n"
        "The operator reads on a phone. He cannot follow a link, and a bare "
        "number tells him nothing about what changed. His rule, 2026-08-11: "
        "put a parenthesis after the number and explain inside it.\n\n"
        f"  required:  {token}(what it is)   or   {token}（中身の説明）\n"
        f"  you wrote: {token}\n"
        f"  fix it to: {token}（グループ判定がスペックを読む問題を修正）\n\n"
        '  Bad : "#589"                        (no description)\n'
        '  Bad : "scitex-dev #589"             (a repo name is not one)\n'
        '  Bad : "PR #589"                     (a label is not one)\n'
        '  Bad : "#589 - auditd rules declared" (a dash is not the form '
        "he asked for)\n"
        '  Good: "#589 (auditd rules declared)"\n'
        '  Good: "#589（auditd ルールを宣言）"\n\n'
        "The PARENTHESIS is the required form — his words, 2026-08-11: "
        "「ナンバーの後に ( をつけて説明する、っていうのをルールにして"
        "ください」. A dash or a colon does NOT pass. Both ( and （ are "
        "accepted. A repo name is not a description. Once a number is "
        "described, later mentions of that SAME number in this message "
        "are fine. URLs, code spans and hex colours are exempt.\n\n"
        f"Rare one-off override: set env {ESCAPE_ENV}=1.\n"
    )


def check_message(text):
    """Return a :class:`Verdict` for one outgoing Telegram message.

    FAIL-OPEN: anything that is not a non-empty string is allowed, so a
    surprising payload shape is never reported as a rule violation.
    """
    if os.environ.get(ESCAPE_ENV) == "1":
        return _OK
    if not isinstance(text, str) or not text:
        return _OK

    scan = _blank(text)

    described = set()
    offender = None
    for match in _REFERENCE.finditer(scan):
        number = match.group(1)
        if _strict_span(scan, match.end()) is not None:
            described.add(number)  # this occurrence carries its description
            continue
        if number in described:
            continue  # described earlier in this same message
        offender = match
        break

    if offender is None:
        return _OK

    token = "#" + offender.group(1)
    start = max(0, offender.start() - 24)
    end = min(len(text), offender.end() + 24)
    excerpt = " ".join(text[start:end].split())
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt = excerpt + "..."
    return Verdict(
        False, token=token, excerpt=excerpt, message=_refusal(token, excerpt)
    )


# --- adapters -------------------------------------------------------
# Both are three lines of glue. All judgement lives in check_message.


def _main_hook_json(stream):
    """Claude Code PreToolUse adapter: hook JSON in, rc 0/2 out."""
    try:
        data = json.load(stream)
    except (OSError, TypeError, UnicodeError, ValueError):
        sys.stderr.write(
            "UNKNOWN Telegram hook input: unreadable JSON; outbound guard remains required.\n"
        )
        return 0
    # Text-stdin stays a standalone stdlib predicate. Only hook mode loads
    # the adjacent packaged input adapter, including when invoked by file path.
    if not __package__:
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from claude_code_telegrammer._hook_input import normalize_hook_input
    except ImportError:
        sys.stderr.write(
            "UNKNOWN Telegram hook input: matched package unavailable; outbound guard remains required.\n"
        )
        return 0

    normalized = normalize_hook_input(data)
    for text in normalized.texts:
        verdict = check_message(text)
        if not verdict.ok:
            sys.stderr.write(verdict.message)
            return 2
    if normalized.state == "unknown":
        sys.stderr.write(
            "UNKNOWN Telegram hook input: not statically resolved; outbound guard remains required.\n"
        )
    return 0


def _main_text_stdin(stream):
    """Language-agnostic adapter: raw text in, one JSON line out."""
    verdict = check_message(stream.read())
    sys.stdout.write(json.dumps(verdict.as_dict(), ensure_ascii=False) + "\n")
    return 0


def main(argv):
    mode = argv[1] if len(argv) > 1 else "--hook-json"
    if mode == "--text-stdin":
        return _main_text_stdin(sys.stdin)
    if mode == "--hook-json":
        return _main_hook_json(sys.stdin)
    sys.stderr.write(f"usage: {argv[0]} [--hook-json|--text-stdin]\n")
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
