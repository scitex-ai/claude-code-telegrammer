"""The shipped stdlib predicate works without package imports or HOME hooks."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

RULE = Path(__file__).resolve().parents[2] / "src" / "claude_code_telegrammer" / "_telegram_rules.py"


@pytest.mark.parametrize(("text", "allowed"), [
    ("PR #106", False),
    ("PR #106（Storage 容量超過処理）", True),
    ("#106(Description) then #106", True),
    ("#106 then #106(Description)", False),
    ("Literal `#106` and https://example.test/#107", True),
])
def test_standalone_packaged_predicate(tmp_path, text, allowed):
    # Arrange
    command = [sys.executable, "-I", str(RULE), "--text-stdin"]

    # Act
    result = subprocess.run(
        command, input=text,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=5, check=True,
    )

    verdict = json.loads(result.stdout)

    # Assert
    assert verdict["ok"] is allowed
