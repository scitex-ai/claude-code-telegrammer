"""Exercise the real launcher in a clean private home without external hooks."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("args", [["send", "--chat-id", "synthetic", "--text", "PR #106"], ["mcp", "start"], ["health"]])
def test_launcher_owns_python_interpreter(tmp_path, args):
    # Arrange
    home = tmp_path / "home"
    home.mkdir()
    bun = tmp_path / "bun"
    bun.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, sys\n"
        "print(json.dumps({'argv':sys.argv[1:], 'python':os.environ['_CCT_PYTHON_EXECUTABLE']}))\n"
    )
    bun.chmod(0o700)
    env = {
        "PATH": "/usr/bin:/bin", "HOME": str(home), "BUN_BIN": str(bun),
        "PYTHONPATH": str(ROOT / "src"),
        "_CCT_PYTHON_EXECUTABLE": "/untrusted/missing-python",
    }

    # Act
    result = subprocess.run(
        [sys.executable, "-m", "claude_code_telegrammer._cli", *args],
        env=env, capture_output=True, text=True, timeout=5, check=True,
    )

    # Assert
    assert json.loads(result.stdout)["python"] == sys.executable


def test_launcher_preserves_send_payload(tmp_path):
    # Arrange
    bun = tmp_path / "bun"
    bun.write_text("#!" + sys.executable + "\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
    bun.chmod(0o700)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BUN_BIN": str(bun), "PYTHONPATH": str(ROOT / "src")}
    payload = "PR #106（Storage 容量超過処理）"

    # Act
    result = subprocess.run(
        [sys.executable, "-m", "claude_code_telegrammer._cli", "send", "--chat-id", "synthetic", "--text", payload],
        env=env, capture_output=True, text=True, timeout=5, check=True,
    )

    # Assert
    assert json.loads(result.stdout)[2:] == ["send", "--chat-id", "synthetic", "--text", payload]
