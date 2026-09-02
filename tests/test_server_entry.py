#!/usr/bin/env python3
"""Server-entry resolution — the three mechanisms and the loud failure.

No mocks and no monkeypatching: every case builds a REAL package layout in a
real temp directory from a byte-for-byte copy of the module under test, and
resolves it in a REAL subprocess with a REAL environment. Patching would have
let the tests agree with a resolver that could not survive an actual install,
which is precisely the fault being fixed here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "src" / "claude_code_telegrammer"

# Resolve, then report either the path or the failure message as JSON. One
# script covers every case, so the cases differ only in the layout and the
# environment they run against.
_PROBE = """
import json
from claude_code_telegrammer._server_entry import (
    ServerEntryNotFound,
    resolve_server_entry,
)

try:
    resolved = resolve_server_entry()
except ServerEntryNotFound as exc:
    print(json.dumps({"error": str(exc)}))
else:
    print(json.dumps({"path": str(resolved)}))
"""

_CLI_PROBE = (
    "from claude_code_telegrammer._cli import main; raise SystemExit(main(['mcp']))"
)


def _make_checkout(root: Path) -> Path:
    """Lay out ``<root>/src/claude_code_telegrammer/`` with the real module.

    Returns the ``src`` directory, which is what goes on ``PYTHONPATH``. The
    ``__init__.py`` is minimal on purpose: the real one reads installed
    distribution metadata that a synthetic tree has no reason to carry, while
    the module under test is copied byte-for-byte so it cannot drift.
    """
    package = root / "src" / "claude_code_telegrammer"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        '__version__ = "0.0.0+test"\n', encoding="utf-8"
    )
    shutil.copy2(PACKAGE_SRC / "_server_entry.py", package / "_server_entry.py")
    return root / "src"


def _write_entry(path: Path, marker: str) -> Path:
    """Create a real ``telegram-server.ts`` whose content names its origin."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'// {marker}\nconsole.log("{marker}");\n', encoding="utf-8")
    return path


def _child_env(src_dir: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    # The ambient environment of whoever runs the suite must not decide the
    # outcome; each case sets the override itself when that is the case.
    env.pop("CCT_SERVER_ENTRY", None)
    env["PYTHONPATH"] = str(src_dir)
    env.update(extra or {})
    return env


def _resolve(src_dir: Path, extra: dict[str, str] | None = None) -> dict:
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        env=_child_env(src_dir, extra),
        cwd=str(src_dir),
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"probe crashed rc={completed.returncode}\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    return json.loads(completed.stdout.strip())


def _run_cli(src_dir: Path, extra: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, "-c", _CLI_PROBE],
        capture_output=True,
        text=True,
        env=_child_env(src_dir, extra),
        cwd=str(src_dir),
        timeout=120,
        check=False,
    )


def _checkout_with_no_entry(root: Path) -> Path:
    return _make_checkout(root)


def _checkout_with_source_entry(root: Path) -> tuple[Path, Path]:
    src_dir = _make_checkout(root)
    entry = _write_entry(root / "ts" / "telegram-server.ts", "source-tree")
    return src_dir, entry


def _checkout_with_packaged_and_source(root: Path) -> tuple[Path, Path]:
    src_dir, _ = _checkout_with_source_entry(root)
    packaged = _write_entry(
        src_dir / "claude_code_telegrammer" / "ts" / "telegram-server.ts",
        "packaged-resource",
    )
    return src_dir, packaged


def test_source_checkout_resolves_the_repo_ts_directory(tmp_path: Path) -> None:
    """A development checkout keeps working: <repo>/ts/telegram-server.ts."""
    # Arrange
    src_dir, entry = _checkout_with_source_entry(tmp_path)
    # Act
    result = _resolve(src_dir)
    # Assert
    assert result == {"path": str(entry)}


def test_packaged_resource_beats_the_source_tree(tmp_path: Path) -> None:
    """An installed wheel ships ts/ INSIDE the package, and that copy wins.

    This is the case 0.6.0 could not serve at all — its ``parents[2]``
    arithmetic pointed at ``site-packages/../ts`` and the wheel shipped no
    ``ts/`` in the first place. Both locations exist here and hold DIFFERENT
    files, so the assertion distinguishes the mechanisms instead of accepting
    either one.
    """
    # Arrange
    src_dir, packaged = _checkout_with_packaged_and_source(tmp_path)
    # Act
    result = _resolve(src_dir)
    # Assert
    assert result == {"path": str(packaged)}


def test_env_override_beats_the_packaged_resource(tmp_path: Path) -> None:
    """$CCT_SERVER_ENTRY outranks both the packaged copy and the source tree."""
    # Arrange
    src_dir, _ = _checkout_with_packaged_and_source(tmp_path)
    override = _write_entry(tmp_path / "elsewhere" / "telegram-server.ts", "override")
    # Act
    result = _resolve(src_dir, {"CCT_SERVER_ENTRY": str(override)})
    # Assert
    assert result == {"path": str(override)}


def test_env_override_resolves_to_the_file_it_actually_names(tmp_path: Path) -> None:
    """Pointing where it says: the resolved file is the overridden content."""
    # Arrange
    src_dir, _ = _checkout_with_packaged_and_source(tmp_path)
    override = _write_entry(tmp_path / "elsewhere" / "telegram-server.ts", "override")
    # Act
    resolved = Path(_resolve(src_dir, {"CCT_SERVER_ENTRY": str(override)})["path"])
    # Assert
    assert resolved.read_text(encoding="utf-8") == override.read_text(encoding="utf-8")


def test_blank_override_is_treated_as_unset(tmp_path: Path) -> None:
    """A whitespace-only value is an unset variable, not a declaration."""
    # Arrange
    src_dir, entry = _checkout_with_source_entry(tmp_path)
    # Act
    result = _resolve(src_dir, {"CCT_SERVER_ENTRY": "   "})
    # Assert
    assert result == {"path": str(entry)}


def test_override_pointing_at_nothing_does_not_fall_back(tmp_path: Path) -> None:
    """A declaration that cannot be honoured must fail, not evaporate.

    A working source-tree entry exists here. Silently using it would run a
    DIFFERENT server than the operator named, and nothing would say so.
    """
    # Arrange
    src_dir, _ = _checkout_with_source_entry(tmp_path)
    missing = tmp_path / "nowhere" / "telegram-server.ts"
    # Act
    result = _resolve(src_dir, {"CCT_SERVER_ENTRY": str(missing)})
    # Assert
    assert "path" not in result, f"fell back instead of failing: {result}"


def test_override_pointing_at_nothing_names_the_bad_path(tmp_path: Path) -> None:
    """The failure quotes the path the operator actually supplied."""
    # Arrange
    src_dir, _ = _checkout_with_source_entry(tmp_path)
    missing = tmp_path / "nowhere" / "telegram-server.ts"
    # Act
    result = _resolve(src_dir, {"CCT_SERVER_ENTRY": str(missing)})
    # Assert
    assert str(missing) in result["error"]


def test_missing_entry_reports_a_failure_rather_than_a_path(tmp_path: Path) -> None:
    """Nothing resolves, so nothing is returned — no invented path."""
    # Arrange
    src_dir = _checkout_with_no_entry(tmp_path)
    # Act
    result = _resolve(src_dir)
    # Assert
    assert "path" not in result, f"resolved something that does not exist: {result}"


def test_missing_entry_names_the_override_variable(tmp_path: Path) -> None:
    """The message names the override an operator can set to fix it."""
    # Arrange
    src_dir = _checkout_with_no_entry(tmp_path)
    # Act
    error = _resolve(src_dir)["error"]
    # Assert
    assert "CCT_SERVER_ENTRY" in error


def test_missing_entry_names_the_packaged_candidate_path(tmp_path: Path) -> None:
    """The concrete packaged path is named, not just the label.

    A label alone tells an operator nothing about WHERE the mechanism looked,
    which is the whole reason 0.6.0's one-line error was undiagnosable.
    """
    # Arrange
    src_dir = _checkout_with_no_entry(tmp_path)
    packaged = src_dir / "claude_code_telegrammer" / "ts" / "telegram-server.ts"
    # Act
    error = _resolve(src_dir)["error"]
    # Assert
    assert str(packaged) in error


def test_missing_entry_names_the_source_tree_candidate_path(tmp_path: Path) -> None:
    """The concrete source-tree path is named too."""
    # Arrange
    src_dir = _checkout_with_no_entry(tmp_path)
    source_tree = tmp_path / "ts" / "telegram-server.ts"
    # Act
    error = _resolve(src_dir)["error"]
    # Assert
    assert str(source_tree) in error


def test_missing_entry_says_what_to_do_about_it(tmp_path: Path) -> None:
    """A loud failure that offers no remedy is only half loud."""
    # Arrange
    src_dir = _checkout_with_no_entry(tmp_path)
    # Act
    error = _resolve(src_dir)["error"]
    # Assert
    assert "reinstall" in error


@pytest.mark.skipif(
    not (REPO_ROOT / "ts" / "telegram-server.ts").is_file(),
    reason="not a source checkout: ts/telegram-server.ts is absent here",
)
def test_this_repository_resolves_its_own_server_entry() -> None:
    """The real repository resolves to its own ts/telegram-server.ts.

    Guards the synthetic layouts above against drifting from the real one.
    """
    # Arrange
    expected = REPO_ROOT / "ts" / "telegram-server.ts"
    # Act
    result = _resolve(REPO_ROOT / "src")
    # Assert
    assert result == {"path": str(expected)}


def test_cli_exits_two_when_the_entry_cannot_be_resolved(tmp_path: Path) -> None:
    """The CLI turns the failure into the documented exit-2 contract."""
    # Arrange
    src_dir = _checkout_with_no_entry(tmp_path)
    shutil.copy2(
        PACKAGE_SRC / "_cli.py", src_dir / "claude_code_telegrammer" / "_cli.py"
    )
    # Act
    completed = _run_cli(src_dir, {"BUN_BIN": sys.executable})
    # Assert
    assert completed.returncode == 2, (
        f"rc={completed.returncode}\nstdout={completed.stdout}\nstderr={completed.stderr}"
    )


def test_cli_stderr_lists_the_paths_it_tried(tmp_path: Path) -> None:
    """The CLI surfaces the resolver's full attempt list, not a summary."""
    # Arrange
    src_dir = _checkout_with_no_entry(tmp_path)
    shutil.copy2(
        PACKAGE_SRC / "_cli.py", src_dir / "claude_code_telegrammer" / "_cli.py"
    )
    # Act
    completed = _run_cli(src_dir, {"BUN_BIN": sys.executable})
    # Assert
    assert "tried, in order" in completed.stderr, completed.stderr


def test_cli_reports_the_entry_fault_before_resolving_bun(tmp_path: Path) -> None:
    """A packaging fault must not hide behind a missing-bun message.

    0.6.0 resolved bun FIRST, so on a host without bun — every fresh container
    — the operator was told to install bun by a CLI that would have died on
    the missing server entry immediately afterwards.
    """
    # Arrange
    src_dir = _checkout_with_no_entry(tmp_path)
    shutil.copy2(
        PACKAGE_SRC / "_cli.py", src_dir / "claude_code_telegrammer" / "_cli.py"
    )
    # Act: no BUN_BIN, and a PATH with no bun on it, so both faults are live
    completed = _run_cli(
        src_dir, {"PATH": str(tmp_path / "empty-bin"), "HOME": str(tmp_path)}
    )
    # Assert
    assert "bun" not in completed.stderr.lower(), completed.stderr
