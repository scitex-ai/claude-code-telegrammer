"""Observed transport inputs reach one predicate without executing tool code."""

import pytest

from claude_code_telegrammer._hook_input import normalize_hook_input
from claude_code_telegrammer._telegram_rules import check_message


@pytest.mark.parametrize(
    "prefix", ["mcp__claude-code-telegrammer__", "mcp__claude_code_telegrammer__"]
)
@pytest.mark.parametrize(
    ("verb", "field"),
    [("reply", "text"), ("edit_message", "text"), ("send_document", "caption")],
)
def test_configured_mcp_rails_keep_exact_outbound_text(prefix, verb, field):
    # Arrange
    document = {
        "tool_name": prefix + verb,
        "tool_input": {field: "#812（保存先の修正） then #812"},
    }

    # Act
    result = normalize_hook_input(document)

    # Assert
    assert (result.state, result.texts) == (
        "observed",
        ("#812（保存先の修正） then #812",),
    )


@pytest.mark.parametrize(
    "document",
    [
        None,
        {"tool_name": 1},
        {
            "tool_name": "mcp__claude_code_telegrammer__reply",
            "tool_input": {"text": ["#812"]},
        },
        {"tool_name": "mcp__claude_code_telegrammer__edit_message", "tool_input": {}},
        {"tool_name": "Bash", "tool_input": {"command": None}},
        {"tool_name": "functions.exec", "tool_input": {"code": ["#812"]}},
    ],
)
def test_malformed_transport_is_unknown_without_text_coercion(document):
    # Arrange
    incoming = document

    # Act
    result = normalize_hook_input(incoming)

    # Assert
    assert (result.state, result.texts) == ("unknown", ())


@pytest.mark.parametrize(
    "document",
    [
        {
            "tool_name": "mcp__claude_code_telegrammer__send_document",
            "tool_input": {"file_path": "/synthetic/document.pdf"},
        },
        {"tool_name": "unrelated_reply", "tool_input": {"text": "#812"}},
        {"tool_name": "Bash", "tool_input": {"command": "printf '%s' '#812'"}},
        {
            "tool_name": "functions.exec",
            "tool_input": 'text("tools.mcp__claude_code_telegrammer__reply({text:\\"#812\\"})")',
        },
    ],
)
def test_data_and_unrelated_tools_are_not_outbound_messages(document):
    # Arrange
    incoming = document

    # Act
    result = normalize_hook_input(incoming)

    # Assert
    assert (result.state, result.texts) == ("not_applicable", ())


@pytest.mark.parametrize(
    "document",
    [
        {
            "tool_name": "functions.exec",
            "tool_input": 'await tools.mcp__claude_code_telegrammer__reply({text: "#812", reply_to: "1"})',
        },
        {
            "tool_name": "functions.exec",
            "tool_input": {
                "code": "await tools.exec_command({cmd: \"timeout 7 claude-code-telegrammer send --chat-id 1 --text '#812'\"})"
            },
        },
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "claude-code-telegrammer send --chat-id 1 --text '#812'"
            },
        },
        {
            "tool_name": "exec_command",
            "tool_input": {"cmd": "claude-code-telegrammer send --text '#812'"},
        },
        {
            "tool_name": "functions.exec_command",
            "tool_input": {"cmd": "claude-code-telegrammer send --text '#812'"},
        },
    ],
)
def test_native_and_shell_literal_egress_uses_canonical_refusal(document):
    # Arrange
    incoming = document

    # Act
    result = normalize_hook_input(incoming)
    verdict = check_message(result.texts[0])

    # Assert
    assert (result.state, verdict.ok, verdict.token) == ("observed", False, "#812")


def test_known_message_is_retained_when_other_call_is_dynamic():
    # Arrange
    document = {
        "tool_name": "functions.exec",
        "tool_input": 'await tools.mcp__claude_code_telegrammer__reply({text: "#812"}); await tools.mcp__claude_code_telegrammer__edit_message({text: variable})',
    }

    # Act
    result = normalize_hook_input(document)

    # Assert
    assert (result.state, result.texts) == ("unknown", ("#812",))
