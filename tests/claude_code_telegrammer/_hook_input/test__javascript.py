"""Native source literals, data and unresolved syntax have distinct evidence."""

import pytest

from claude_code_telegrammer._hook_input._javascript import literal_tool_calls


@pytest.mark.parametrize(
    ("source", "text"),
    [
        ('await tools.reply({text: "#812（保存）", id: "1"})', "#812（保存）"),
        ('await tools["reply"]({"text": "#812 \\u0028save\\u0029"})', "#812 (save)"),
        ("await tools.reply({text: '#812 \\x28save\\x29'})", "#812 (save)"),
        (
            "await tools.reply({text: `#812 (save)\\nsecond line`})",
            "#812 (save)\nsecond line",
        ),
        ('await tools.reply({text: "\\ud83d\\ude80 #812 (save)"})', "🚀 #812 (save)"),
        ('await tools.reply({text: "old", text: "#812 (save)"})', "#812 (save)"),
    ],
)
def test_literal_arguments_preserve_javascript_string_semantics(source, text):
    # Arrange
    code = source

    # Act
    calls, unknown = literal_tool_calls(code)

    # Assert
    assert (unknown, calls[0][1]["text"]) == (False, text)


@pytest.mark.parametrize(
    "source",
    [
        '// tools.reply({text: "#812"})\ntext("hello")',
        '/* tools.reply({text: "#812"}) */ text("hello")',
        'const example = "tools.reply({text: \\"#812\\"})";',
        'other.tools.reply({text: "#812"})',
    ],
)
def test_comments_strings_and_foreign_object_properties_are_data(source):
    # Arrange
    code = source

    # Act
    result = literal_tool_calls(code)

    # Assert
    assert result == ([], False)


@pytest.mark.parametrize(
    "source",
    [
        "await tools.reply({text: variable})",
        'await tools.reply({text: "#812" + suffix})',
        "await tools.reply({text: `#812 ${description}`})",
        'await tools.reply({text: "\\ud800"})',
        'await tools.reply({text: "\\uZZZZ"})',
        'await tools.reply({text: "\\01"})',
        'await tools.reply({text: {nested: "#812"}})',
    ],
)
def test_dynamic_or_malformed_text_is_not_promoted_to_known_text(source):
    # Arrange
    code = source

    # Act
    calls, _ = literal_tool_calls(code)

    # Assert
    assert calls[0][1]["text"] is None


@pytest.mark.parametrize(
    "source",
    [
        'await tools.reply({...outgoing, text: "#812"})',
        'await tools.reply({[key]: "#812"})',
        "await tools.reply({text})",
        'await tools.reply({text: "#812"',
        'const send = tools.reply; await send({text: "#812"})',
    ],
)
def test_indirect_or_unclosed_call_has_no_known_field_mapping(source):
    # Arrange
    code = source

    # Act
    calls, _ = literal_tool_calls(code)

    # Assert
    assert calls[0][1] is None


@pytest.mark.parametrize(
    "source",
    [
        'const regex = /tools.reply({text: "#812"})/;',
        'await tools[name]({text: "#812"})',
        'await tools.reply({text: "unfinished})',
    ],
)
def test_unresolved_syntax_never_claims_static_enforcement(source):
    # Arrange
    code = source

    # Act
    calls, unknown = literal_tool_calls(code)

    # Assert
    assert (unknown, calls) == (True, [])
