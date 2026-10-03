"""The shipped stdlib predicate works without package imports or HOME hooks."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

RULE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "claude_code_telegrammer"
    / "_telegram_rules.py"
)


@pytest.mark.parametrize(
    ("text", "allowed"),
    [
        ("PR #106", False),
        ("PR #106（Storage 容量超過処理）", True),
        ("#106(Description) then #106", True),
        ("#106 then #106(Description)", False),
        ("Literal `#106` and https://example.test/#107", True),
        ("PR #106 - dash is not the form", False),
        ("PR #106: colon is not the form", False),
        ("PR #106 (unclosed", False),
        ("PR #106 ()", False),
        ("PR #106 (106)", False),
        (
            "PR #106"
            + chr(0xFF08)
            + chr(0xFF11)
            + chr(0xFF12)
            + chr(0xFF13)
            + chr(0xFF09),
            False,
        ),
        ("PR #106\n(Storage quota response)", False),
        ("PR #106\r(Storage quota response)", False),
        ("PR #106 (a\rb)", False),
        (
            "PR #106" + chr(0x2028) + "(Storage quota response)",
            False,
        ),
        (
            "PR #106 (a" + chr(0x2028) + "b)",
            False,
        ),
        (
            "PR #106 (a" + chr(0x2029) + "b)",
            False,
        ),
        (
            "PR #106 (see ```\ncode\n``` here)",
            False,
        ),
        (
            "PR #106 (see `cmd` here)",
            True,
        ),
        ("PR #106（日本語の説明）", True),
        ("PR #106 (Storage quota response) then PR #107", False),
    ],
)
def test_standalone_packaged_predicate(tmp_path, text, allowed):
    # Arrange
    command = [sys.executable, "-I", str(RULE), "--text-stdin"]

    # Act
    result = subprocess.run(
        command,
        input=text,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )

    verdict = json.loads(result.stdout)

    # Assert
    assert verdict["ok"] is allowed


@pytest.mark.parametrize(
    ("payload", "status", "diagnostic"),
    [
        (
            {
                "tool_name": "mcp__claude_code_telegrammer__reply",
                "tool_input": {"text": "#812"},
            },
            2,
            "BLOCKED",
        ),
        (
            {
                "tool_name": "mcp__claude-code-telegrammer__edit_message",
                "tool_input": {"text": "#812 (save) then #812"},
            },
            0,
            "",
        ),
        (
            {
                "tool_name": "mcp__claude_code_telegrammer__send_document",
                "tool_input": {"caption": "#812"},
            },
            2,
            "BLOCKED",
        ),
        (
            {
                "tool_name": "functions.exec",
                "tool_input": 'await tools.mcp__claude_code_telegrammer__reply({text: "#812"})',
            },
            2,
            "BLOCKED",
        ),
        (
            {
                "tool_name": "functions.exec",
                "tool_input": "await tools.exec_command({cmd: \"timeout 7 claude-code-telegrammer send --text '#812'\"})",
            },
            2,
            "BLOCKED",
        ),
        (
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": "claude-code-telegrammer send --text '#812（保存）'"
                },
            },
            0,
            "",
        ),
        (
            {
                "tool_name": "functions.exec",
                "tool_input": "await tools.mcp__claude_code_telegrammer__reply({text: message})",
            },
            0,
            "UNKNOWN",
        ),
        (
            {
                "tool_name": "mcp__claude_code_telegrammer__reply",
                "tool_input": {"text": {"private": "synthetic-private-canary"}},
            },
            0,
            "UNKNOWN",
        ),
        (None, 0, "UNKNOWN"),
    ],
)
def test_real_hook_process_keeps_refusal_and_unknown_distinct(
    tmp_path, payload, status, diagnostic
):
    # Arrange
    command = [sys.executable, "-I", str(RULE), "--hook-json"]

    # Act
    result = subprocess.run(
        command,
        input=json.dumps(payload),
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    # Assert
    assert (
        result.returncode,
        result.stdout,
        result.stderr.startswith(diagnostic),
        "synthetic-private-canary" in result.stderr,
    ) == (status, "", True, False)


def test_unreadable_json_is_unknown_without_echoing_payload(tmp_path):
    # Arrange
    command = [sys.executable, "-I", str(RULE), "--hook-json"]

    # Act
    result = subprocess.run(
        command,
        input="synthetic-private-canary {",
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    # Assert
    assert (
        result.returncode,
        result.stdout,
        result.stderr.startswith("UNKNOWN"),
        "synthetic-private-canary" in result.stderr,
    ) == (0, "", True, False)
