"""Read the declared CCT CLI's literal shell text without running commands."""

from __future__ import annotations

import re
import shlex

CLI = "claude-code-telegrammer"


def _literal(token):
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1]
    if token.startswith('"') and token.endswith('"'):
        value, cursor = [], 1
        while cursor < len(token) - 1:
            char = token[cursor]
            if char in ("$", "`"):
                return None
            if char == "\\" and cursor + 1 < len(token) - 1:
                cursor += 1
                char = token[cursor]
                if char not in ('"', "\\", "$", "`", "\n"):
                    value.append("\\")
                if char == "\n":
                    cursor += 1
                    continue
            value.append(char)
            cursor += 1
        return "".join(value)
    if any(char in token for char in ("$", "`", "\\", "'", '"')):
        return None
    return token


def _segment(tokens):
    values = [_literal(token) for token in tokens]
    if CLI not in values:
        return [], False
    # The node contract uses timeout for bounded foreground commands.
    if values[:1] == ["timeout"] and len(values) >= 3:
        if values[1] is None or not re.fullmatch(r"\d+(?:\.\d+)?[smhd]?", values[1]):
            return [], True
        values = values[2:]
    if values[:1] != [CLI]:
        return [], values[:1] not in (["echo"], ["printf"])
    if values[1:2] != ["send"]:
        return [], False
    # Match the packaged parser's first-occurrence flag semantics. Later
    # duplicates are not the outbound message and cannot create a refusal.
    if "--text" not in values:
        return [], True
    index = values.index("--text")
    text = values[index + 1] if index + 1 < len(values) else None
    if text is None or text.startswith("--"):
        return [], True
    return [text], False


def literal_cli_texts(command):
    """Only the packaged CLI name is recognized; aliases/expansion are unknown."""
    lexer = shlex.shlex(command, posix=False, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        return [], True
    texts, segment, unknown = [], [], False
    for token in [*tokens, ";"]:
        if token.startswith("#"):
            break
        if token and all(char in ";&|()" for char in token):
            found, unresolved = _segment(segment)
            texts.extend(found)
            unknown |= unresolved
            segment = []
        else:
            segment.append(token)
    if segment:
        found, unresolved = _segment(segment)
        texts.extend(found)
        unknown |= unresolved
    return texts, unknown
