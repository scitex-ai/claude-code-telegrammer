"""Read literal native tool arguments without evaluating JavaScript."""

from __future__ import annotations

import re

_TOKEN = re.compile(
    r"\s+|//[^\n]*|/\*.*?\*/|"
    r'"(?:\\.|[^"\\])*"|'
    r"'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|"
    r"[A-Za-z_$][A-Za-z0-9_$]*|[^\s]",
    re.DOTALL,
)
_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*\Z")


def _string(token):
    if not token or token[0] not in "\"'`":
        return None
    body = token[1:-1]
    if token[0] == "`" and "${" in body:
        return None
    escapes = {
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "b": "\b",
        "f": "\f",
        "v": "\v",
        "0": "\0",
        "'": "'",
        '"': '"',
        "\\": "\\",
        "/": "/",
        "`": "`",
    }
    value, cursor = [], 0
    while cursor < len(body):
        char = body[cursor]
        if char != "\\":
            value.append(char)
            cursor += 1
            continue
        cursor += 1
        if cursor == len(body):
            return None
        char = body[cursor]
        if char in ("u", "x"):
            length = 4 if char == "u" else 2
            digits = body[cursor + 1 : cursor + length + 1]
            if len(digits) != length or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                return None
            value.append(chr(int(digits, 16)))
            cursor += length + 1
            continue
        if char in ("\n", "\r"):
            cursor += 1 + (char == "\r" and body[cursor + 1 : cursor + 2] == "\n")
            continue
        if char not in escapes or (
            char == "0" and body[cursor + 1 : cursor + 2].isdigit()
        ):
            return None
        value.append(escapes[char])
        cursor += 1
    try:
        return "".join(value).encode("utf-16", "surrogatepass").decode("utf-16")
    except UnicodeError:
        return None


def _fields(tokens, start):
    """Only direct property literals; spread/computed/shorthand remain unknown."""
    fields = {}
    cursor = start + 1
    while cursor < len(tokens):
        if tokens[cursor] == "}":
            return fields
        key = tokens[cursor]
        key = key if _IDENTIFIER.fullmatch(key) else _string(key)
        if key is None or cursor + 1 >= len(tokens) or tokens[cursor + 1] != ":":
            return None
        cursor += 2
        begin = cursor
        stack = []
        pairs = {")": "(", "]": "[", "}": "{"}
        while cursor < len(tokens):
            token = tokens[cursor]
            if not stack and token in (",", "}"):
                break
            if token in ("(", "[", "{"):
                stack.append(token)
            elif token in pairs and (not stack or stack.pop() != pairs[token]):
                return None
            cursor += 1
        if cursor == len(tokens) or stack:
            return None
        fields[key] = _string(tokens[begin]) if cursor - begin == 1 else None
        if tokens[cursor] == "}":
            return fields
        cursor += 1
    return None


def literal_tool_calls(code):
    """Return named calls/fields plus unresolved syntax; never execute aliases.

    Comments and strings are data. Unsupported regex/division syntax refuses
    static interpretation, rather than treating apparent calls inside it as
    outbound messages. The packaged final outbound predicate still owns egress.
    """
    tokens = [
        match.group()
        for match in _TOKEN.finditer(code)
        if not match.group().isspace() and not match.group().startswith(("//", "/*"))
    ]
    if any(token in ("/", '"', "'", "`") for token in tokens):
        return [], True
    calls, unknown = [], False
    for index, token in enumerate(tokens):
        if token != "tools" or index + 2 >= len(tokens):
            continue
        if index and tokens[index - 1] == ".":
            continue
        following = index + 3
        if tokens[index + 1] == ".":
            name = tokens[index + 2]
        elif tokens[index + 1] == "[":
            name = _string(tokens[index + 2])
            if index + 3 >= len(tokens) or tokens[index + 3] != "]" or name is None:
                unknown = True
                continue
            following += 1
        else:
            continue
        fields = None
        if (
            following + 1 < len(tokens)
            and tokens[following] == "("
            and tokens[following + 1] == "{"
        ):
            fields = _fields(tokens, following + 1)
        calls.append((name, fields))
    return calls, unknown
