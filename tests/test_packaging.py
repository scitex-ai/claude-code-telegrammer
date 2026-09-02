#!/usr/bin/env python3
"""Packaging regression: the built wheel must CONTAIN the server it launches.

0.6.0 shipped a launcher and nothing to launch. The dist-info RECORD had no
``telegram-server.ts`` anywhere, so ``claude-code-telegrammer send`` and the
MCP server were structurally dead on every non-editable install — and said so
only at first use, months after the release that broke them.

Reading pyproject.toml would not have caught it and does not catch it now: the
fault was in what hatchling actually EMITS, not in what the config appears to
say. These tests therefore build a real wheel and read the real archive.

When no PEP 517 backend is importable the tests SKIP with that stated reason
rather than passing vacuously — a green run that never built anything is worth
exactly nothing here.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TS_ROOT = REPO_ROOT / "ts"
PACKAGED_TS = "claude_code_telegrammer/ts"

_HAVE_HATCHLING = importlib.util.find_spec("hatchling") is not None
_HAVE_BUILD = importlib.util.find_spec("build") is not None

_NO_BACKEND_REASON = (
    "no PEP 517 backend importable in this interpreter "
    f"({sys.executable}): install `hatchling` (the backend this project "
    "declares) or `build` to run the wheel-contents regression"
)

requires_backend = pytest.mark.skipif(
    not (_HAVE_HATCHLING or _HAVE_BUILD), reason=_NO_BACKEND_REASON
)

# Building once and sharing the archive across the assertions keeps the suite
# from paying for a wheel per test; hatchling emits a fresh one each call.
_BUILD_SCRIPT = """
import sys
import hatchling.build as backend

sys.stdout.write(backend.build_wheel(sys.argv[1]))
"""


def _build_wheel(outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    if _HAVE_HATCHLING:
        # The declared backend, called through its PEP 517 hook: no build
        # isolation, no network, and no second opinion about which backend
        # this project uses.
        completed = subprocess.run(
            [sys.executable, "-c", _BUILD_SCRIPT, str(outdir)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=600,
            check=False,
        )
    else:
        completed = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(outdir)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=600,
            check=False,
        )
    if completed.returncode != 0:
        pytest.skip(
            "the wheel build failed in this environment, so wheel contents "
            f"could not be checked: rc={completed.returncode}\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    wheels = sorted(outdir.glob("*.whl"))
    if not wheels:
        pytest.skip(f"the build produced no wheel in {outdir}")
    return wheels[-1]


@pytest.fixture(scope="module")
def wheel_names(tmp_path_factory) -> list[str]:
    """Entry names of a freshly built wheel, built from this checkout."""
    if not (_HAVE_HATCHLING or _HAVE_BUILD):
        pytest.skip(_NO_BACKEND_REASON)
    wheel = _build_wheel(tmp_path_factory.mktemp("wheel"))
    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


@requires_backend
def test_wheel_contains_the_telegram_server_entry(wheel_names: list[str]) -> None:
    """The exact file whose absence killed 0.6.0."""
    # Arrange
    expected = f"{PACKAGED_TS}/telegram-server.ts"
    # Act
    present = expected in wheel_names
    # Assert
    assert present, f"{expected} missing from the wheel; entries={len(wheel_names)}"


@requires_backend
def test_wheel_contains_the_telegram_poller_entry(wheel_names: list[str]) -> None:
    """The poller is spawned by the server and must travel with it."""
    # Arrange
    expected = f"{PACKAGED_TS}/telegram-poller.ts"
    # Act
    present = expected in wheel_names
    # Assert
    assert present, f"{expected} missing from the wheel"


@requires_backend
def test_wheel_ships_every_top_level_runtime_ts_file(wheel_names: list[str]) -> None:
    """A new ts/*.ts file cannot be forgotten into another dead wheel.

    force-include lists paths individually (it must — see pyproject.toml), so
    the cost of that precision is a file that someone adds and nobody maps.
    This converts that omission from a silent runtime death into a red test.
    """
    # Arrange
    on_disk = {p.name for p in TS_ROOT.glob("*.ts")}
    # Act
    missing = sorted(
        name for name in on_disk if f"{PACKAGED_TS}/{name}" not in wheel_names
    )
    # Assert
    assert not missing, f"ts/*.ts present on disk but absent from the wheel: {missing}"


@requires_backend
def test_wheel_ships_every_ts_lib_module(wheel_names: list[str]) -> None:
    """telegram-server.ts imports ./lib/*.js; a partial lib is a broken server."""
    # Arrange
    on_disk = {p.name for p in (TS_ROOT / "lib").glob("*.ts")}
    # Act
    missing = sorted(
        name for name in on_disk if f"{PACKAGED_TS}/lib/{name}" not in wheel_names
    )
    # Assert
    assert not missing, f"ts/lib modules absent from the wheel: {missing}"


@requires_backend
def test_wheel_ships_the_bun_package_manifest(wheel_names: list[str]) -> None:
    """package.json is what `bun install` reads next to the packaged server."""
    # Arrange
    expected = f"{PACKAGED_TS}/package.json"
    # Act
    present = expected in wheel_names
    # Assert
    assert present, f"{expected} missing from the wheel"


@requires_backend
@pytest.mark.skipif(
    not (TS_ROOT / "node_modules").is_dir(),
    reason=(
        "ts/node_modules does not exist in this checkout, so an empty result "
        "would prove nothing about whether the build excludes it; run "
        "`bun install` in ts/ to make this check meaningful"
    ),
)
def test_wheel_does_not_ship_bun_node_modules(wheel_names: list[str]) -> None:
    """Third-party bun packages have no business inside a Python wheel.

    This needs the positive control the skipif enforces. Measured 2026-09-02:
    hatchling's `exclude` does NOT apply to force-included paths and neither
    does ts/.gitignore, so a whole-directory `"ts" = ...` mapping shipped a
    planted ts/node_modules/probe-pkg straight into the archive.
    """
    # Arrange
    control = TS_ROOT / "node_modules"
    # Act
    leaked = sorted(name for name in wheel_names if "node_modules" in name)
    # Assert
    assert not leaked, (
        f"node_modules leaked into the wheel from {control}: {leaked[:10]}"
    )
