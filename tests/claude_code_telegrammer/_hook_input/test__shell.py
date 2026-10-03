"""Only literal declared CLI send arguments are observed shell egress."""

import pytest

from claude_code_telegrammer._hook_input._shell import literal_cli_texts


@pytest.mark.parametrize(
    ("source", "text"),
    [
        ("claude-code-telegrammer send --text '#812（保存）'", "#812（保存）"),
        ('timeout 7 claude-code-telegrammer send --text "#812 (save)"', "#812 (save)"),
        (
            'timeout 0.5s claude-code-telegrammer send --text "#812 (save)\\n"',
            "#812 (save)\\n",
        ),
        ('claude-code-telegrammer send --text "\\$812 (literal)"', "$812 (literal)"),
        ("claude-code-telegrammer send --text '#812' # trailing comment", "#812"),
    ],
)
def test_literal_shell_strings_keep_actual_outbound_content(source, text):
    # Arrange
    command = source

    # Act
    result = literal_cli_texts(command)

    # Assert
    assert result == ([text], False)


@pytest.mark.parametrize(
    "source",
    [
        "printf '%s' 'claude-code-telegrammer send --text #812'",
        "echo claude-code-telegrammer send --text '#812'",
        "# claude-code-telegrammer send --text '#812'",
        "claude-code-telegrammer status",
    ],
)
def test_displayed_command_or_unrelated_cli_verb_is_not_egress(source):
    # Arrange
    command = source

    # Act
    result = literal_cli_texts(command)

    # Assert
    assert result == ([], False)


@pytest.mark.parametrize(
    "source",
    [
        'claude-code-telegrammer send --text "$MESSAGE"',
        'claude-code-telegrammer send --text "$(read_message)"',
        'claude-code-telegrammer send --text "`read_message`"',
        "claude-code-telegrammer send --text",
        "claude-code-telegrammer send --text '#812",
        "claude-code-telegrammer send --text=message",
        "env claude-code-telegrammer send --text '#812'",
        "timeout $DEADLINE claude-code-telegrammer send --text '#812'",
        "timeout --signal=TERM claude-code-telegrammer send --text '#812'",
    ],
)
def test_unresolved_shell_never_executes_or_claims_observed_text(source):
    # Arrange
    command = source

    # Act
    result = literal_cli_texts(command)

    # Assert
    assert result == ([], True)


def test_duplicate_flag_uses_actual_cli_first_value():
    # Arrange
    command = "claude-code-telegrammer send --text '#812 (save)' --text '#813'"

    # Act
    result = literal_cli_texts(command)

    # Assert
    assert result == (["#812 (save)"], False)


def test_flag_as_first_text_value_keeps_actual_parser_refusal_unknown():
    # Arrange
    command = "claude-code-telegrammer send --text --text '#812'"

    # Act
    result = literal_cli_texts(command)

    # Assert
    assert result == ([], True)
