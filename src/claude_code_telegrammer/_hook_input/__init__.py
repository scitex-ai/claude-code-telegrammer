"""Normalize observed hook input to the package-owned outgoing-text predicate."""

from __future__ import annotations

from dataclasses import dataclass

from .._telegram_rules import HOOK_INPUT_VERSION
from ._javascript import literal_tool_calls
from ._shell import literal_cli_texts

__all__ = ["HOOK_INPUT_VERSION", "HookInput", "normalize_hook_input"]
_PREFIXES = ("mcp__claude-code-telegrammer__", "mcp__claude_code_telegrammer__")
_TEXT_FIELDS = {"reply": "text", "edit_message": "text", "send_document": "caption"}
_DIRECT = {
    prefix + verb: field for prefix in _PREFIXES for verb, field in _TEXT_FIELDS.items()
}
_SHELL_TOOLS = ("Bash", "exec_command", "functions.exec_command")


@dataclass(frozen=True)
class HookInput:
    """Static text evidence; unknown remains fail-open, never claimed enforced."""

    state: str
    texts: tuple[str, ...] = ()


def _direct(name, fields):
    key = _DIRECT[name]
    if not isinstance(fields, dict):
        return [], True
    if key not in fields and key == "caption":
        return [], False
    value = fields.get(key)
    return ([value], False) if isinstance(value, str) else ([], True)


def _code(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("code"), str):
        return value["code"]
    return None


def normalize_hook_input(document):
    """Known direct MCP and literal native/Bash rails; no execution or coercion."""
    if not isinstance(document, dict) or not isinstance(document.get("tool_name"), str):
        return HookInput("unknown")
    name, value = document["tool_name"], document.get("tool_input")
    if name in _DIRECT:
        texts, unknown = _direct(name, value)
    elif name in _SHELL_TOOLS:
        key = "command" if name == "Bash" else "cmd"
        command = value.get(key) if isinstance(value, dict) else None
        if not isinstance(command, str):
            return HookInput("unknown")
        texts, unknown = literal_cli_texts(command)
    elif name == "functions.exec":
        code = _code(value)
        if code is None:
            return HookInput("unknown")
        calls, unknown = literal_tool_calls(code)
        texts = []
        for tool, fields in calls:
            if tool in _DIRECT:
                found, unresolved = _direct(tool, fields)
            elif tool == "exec_command":
                command = fields.get("cmd") if isinstance(fields, dict) else None
                found, unresolved = (
                    literal_cli_texts(command)
                    if isinstance(command, str)
                    else ([], True)
                )
            else:
                continue
            texts.extend(found)
            unknown |= unresolved
    else:
        return HookInput("not_applicable")
    return HookInput(
        "unknown" if unknown else "observed" if texts else "not_applicable",
        tuple(texts),
    )
