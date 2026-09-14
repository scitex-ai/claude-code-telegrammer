#!/usr/bin/env python3
"""Packaging regression: the built wheel must CONTAIN the server it launches.

0.6.0 shipped a launcher and nothing to launch. The dist-info RECORD had no
``telegram-server.ts`` anywhere, so ``claude-code-telegrammer send`` and the
MCP server were structurally dead on every non-editable install — and said so
only at first use, months after the release that broke them.

Reading pyproject.toml would not have caught it and does not catch it now: the
fault was in what hatchling actually EMITS, not in what the config appears to
say. These tests therefore build a real wheel and read the real archive.

TWO ARTIFACTS, BECAUSE THERE ARE TWO BUILD PATHS. The fast path builds a wheel
straight from the checkout; the RELEASE path (``python -m build``) builds an
sdist and then builds the wheel from THAT. They are not the same archive — a
symlink under ``src/`` shipped five shell modules on the first path and none on
the second — so the sdist round trip is built and compared too. Testing only
the convenient one is how a green suite certifies an artifact nobody shipped.

A build that RUNS AND FAILS is a failure, never a skip. Only a missing PEP 517
backend skips, with that stated reason: a green run that never built anything
is worth exactly nothing here, and a ``pytest.skip`` on a non-zero build turned
the one fault class this file exists to catch — a force-include table that
cannot produce a wheel — into six silent passes.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TS_ROOT = REPO_ROOT / "ts"
SHELL_LIB_ROOT = REPO_ROOT / "lib"
PACKAGED_TS = "claude_code_telegrammer/ts"
PACKAGED_SHELL_LIB = "claude_code_telegrammer/lib"

_HAVE_HATCHLING = importlib.util.find_spec("hatchling") is not None
_HAVE_BUILD = importlib.util.find_spec("build") is not None

_NO_BACKEND_REASON = (
    "no PEP 517 backend importable in this interpreter "
    f"({sys.executable}): install `hatchling` (the backend this project "
    "declares) or `build` to run the wheel-contents regression"
)

_NO_HATCHLING_REASON = (
    "hatchling is not importable in this interpreter "
    f"({sys.executable}): the sdist round trip calls the declared backend's "
    "build_sdist/build_wheel hooks directly, which needs it"
)

requires_backend = pytest.mark.skipif(
    not (_HAVE_HATCHLING or _HAVE_BUILD), reason=_NO_BACKEND_REASON
)

requires_hatchling = pytest.mark.skipif(not _HAVE_HATCHLING, reason=_NO_HATCHLING_REASON)

# Building once and sharing the archive across the assertions keeps the suite
# from paying for a wheel per test; hatchling emits a fresh one each call.
_WHEEL_SCRIPT = """
import sys
import hatchling.build as backend

sys.stdout.write(backend.build_wheel(sys.argv[1]))
"""

_SDIST_SCRIPT = """
import sys
import hatchling.build as backend

sys.stdout.write(backend.build_sdist(sys.argv[1]))
"""

# Build output and third-party payload, not source. Copying them into a scratch
# tree would be slow, and copying a node_modules would poison the very question
# the leak control asks.
_COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"
)


def _run_backend(script: str, outdir: Path, source_root: Path) -> str:
    """Call one PEP 517 hook in a subprocess and return the artifact name."""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(outdir)],
        capture_output=True,
        text=True,
        cwd=str(source_root),
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        # NOT a skip. The backend is present and refused to build this project
        # — which is exactly what a force-include entry naming a renamed, moved
        # or deleted file does. That is the defect, not an absent capability.
        pytest.fail(
            f"the PEP 517 build failed in {source_root}: "
            f"rc={completed.returncode}\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}",
            pytrace=False,
        )
    return completed.stdout.strip()


def _build_wheel(outdir: Path, source_root: Path = REPO_ROOT) -> Path:
    """Build a wheel straight from ``source_root`` and return its path."""
    outdir.mkdir(parents=True, exist_ok=True)
    if _HAVE_HATCHLING:
        # The declared backend, called through its PEP 517 hook: no build
        # isolation, no network, and no second opinion about which backend
        # this project uses.
        _run_backend(_WHEEL_SCRIPT, outdir, source_root)
    else:
        completed = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(outdir)],
            capture_output=True,
            text=True,
            cwd=str(source_root),
            timeout=600,
            check=False,
        )
        if completed.returncode != 0:
            pytest.fail(
                f"`python -m build --wheel` failed in {source_root}: "
                f"rc={completed.returncode}\n"
                f"stdout={completed.stdout}\nstderr={completed.stderr}",
                pytrace=False,
            )
    wheels = sorted(outdir.glob("*.whl"))
    if not wheels:
        # A backend that ran, returned zero and emitted nothing is a defect in
        # the packaging config, not a reason to stop asking questions.
        pytest.fail(f"the build produced no wheel in {outdir}", pytrace=False)
    return wheels[-1]


def _build_wheel_via_sdist(workdir: Path) -> Path:
    """Build the sdist, unpack it, and build the wheel FROM the unpacked tree.

    This is what ``python -m build`` — and therefore the release workflow —
    does by default, so this is the artifact PyPI receives.
    """
    sdist_dir = workdir / "sdist"
    sdist_dir.mkdir(parents=True, exist_ok=True)
    reported = _run_backend(_SDIST_SCRIPT, sdist_dir, REPO_ROOT)
    sdists = sorted(sdist_dir.glob("*.tar.gz"))
    if not sdists:
        pytest.fail(
            f"the backend reported sdist {reported!r} but produced none in {sdist_dir}",
            pytrace=False,
        )

    extracted = workdir / "extracted"
    extracted.mkdir(parents=True, exist_ok=True)
    with tarfile.open(sdists[-1]) as archive:
        if hasattr(tarfile, "data_filter"):
            archive.extractall(extracted, filter="data")
        else:  # pragma: no cover - Python without PEP 706 extraction filters
            archive.extractall(extracted)  # noqa: S202 - our own fresh sdist
    roots = [entry for entry in extracted.iterdir() if entry.is_dir()]
    if len(roots) != 1:
        pytest.fail(
            f"expected one top-level directory in the sdist, found {roots}",
            pytrace=False,
        )
    return _build_wheel(workdir / "wheel", source_root=roots[0])


def _namelist(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


@pytest.fixture(scope="module")
def wheel_names(tmp_path_factory) -> list[str]:
    """Entry names of a freshly built wheel, built from this checkout."""
    if not (_HAVE_HATCHLING or _HAVE_BUILD):
        pytest.skip(_NO_BACKEND_REASON)
    return _namelist(_build_wheel(tmp_path_factory.mktemp("wheel")))


@pytest.fixture(scope="module")
def release_wheel_names(tmp_path_factory) -> list[str]:
    """Entry names of the wheel the RELEASE path produces (sdist -> wheel)."""
    if not _HAVE_HATCHLING:
        pytest.skip(_NO_HATCHLING_REASON)
    return _namelist(_build_wheel_via_sdist(tmp_path_factory.mktemp("release")))


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
def test_wheel_ships_the_bun_lockfile(wheel_names: list[str]) -> None:
    """Without the lockfile the documented remedy resolves the SDK unpinned.

    docs/configuration.md tells wheel users to run `bun install` in the
    packaged ts/ directory, and package.json asks for
    `@modelcontextprotocol/sdk: ^1.12.1`. With no bun.lock beside it that caret
    range is resolved fresh over the network, so a future 1.x can break the
    packaged server's imports on new installs while CI — which resolves against
    the repo's lockfile — stays green. Two installs of one wheel version would
    then not be the same software.
    """
    # Arrange
    expected = f"{PACKAGED_TS}/bun.lock"
    # Act
    present = expected in wheel_names
    # Assert
    assert present, f"{expected} missing from the wheel"


@requires_backend
def test_wheel_ships_the_shell_library(wheel_names: list[str]) -> None:
    """lib/*.sh is the auto-responder's runtime, not a development extra."""
    # Arrange
    on_disk = {p.name for p in SHELL_LIB_ROOT.glob("*.sh")}
    # Act
    missing = sorted(
        name for name in on_disk if f"{PACKAGED_SHELL_LIB}/{name}" not in wheel_names
    )
    # Assert
    assert not missing, f"lib/*.sh absent from the wheel: {missing}"


@pytest.fixture
def node_modules_leak(tmp_path: Path) -> list[str]:
    """Wheel entries naming ``node_modules``, built with a PLANTED one present.

    THE CONTROL IS SUPPLIED HERE rather than waited for. The check used to be
    gated on an ambient ``ts/node_modules``, which no CI leg ever creates — the
    only job that runs pytest never runs ``bun install`` — so the guard whose
    rationale fills fifteen lines of pyproject.toml was switched off on every
    automated run, forever. Copying the tree and planting a package means an
    empty result proves the build EXCLUDED a file that was really there.
    """
    if not (_HAVE_HATCHLING or _HAVE_BUILD):
        pytest.skip(_NO_BACKEND_REASON)
    work = tmp_path / "checkout"
    shutil.copytree(REPO_ROOT, work, ignore=_COPY_IGNORE, symlinks=True)
    planted = work / "ts" / "node_modules" / "probe-pkg" / "package.json"
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text('{"name": "probe-pkg", "version": "0.0.0"}\n', encoding="utf-8")
    names = _namelist(_build_wheel(tmp_path / "out", source_root=work))
    return sorted(name for name in names if "node_modules" in name)


@requires_backend
def test_wheel_does_not_ship_bun_node_modules(node_modules_leak: list[str]) -> None:
    """Third-party bun packages have no business inside a Python wheel.

    Measured 2026-09-02: hatchling's `exclude` does NOT apply to force-included
    paths and neither does ts/.gitignore, so a whole-directory `"ts" = ...`
    mapping shipped the planted package straight into the archive.
    """
    # Arrange: the fixture planted ts/node_modules/probe-pkg and built a wheel
    leaked = node_modules_leak
    # Act
    count = len(leaked)
    # Assert
    assert count == 0, f"node_modules leaked into the wheel: {leaked}"


@requires_hatchling
def test_release_path_wheel_contains_the_telegram_server_entry(
    release_wheel_names: list[str],
) -> None:
    """The artifact PyPI receives must carry the server too, not just ours."""
    # Arrange
    expected = f"{PACKAGED_TS}/telegram-server.ts"
    # Act
    present = expected in release_wheel_names
    # Assert
    assert present, (
        f"{expected} missing from the sdist-round-trip wheel; "
        f"entries={len(release_wheel_names)}"
    )


@requires_hatchling
def test_release_path_wheel_matches_the_direct_build(
    wheel_names: list[str], release_wheel_names: list[str]
) -> None:
    """The wheel the tests read and the wheel PyPI gets must be one artifact.

    Measured 2026-09-02, before the force-include table named `lib`: the direct
    build carried claude_code_telegrammer/lib/*.sh through a symlink under src/
    and the release round trip carried none — 68 entries against 63. Every
    assertion above ran on the first archive; users installed the second.
    """
    # Arrange
    direct = set(wheel_names)
    release = set(release_wheel_names)
    # Act
    only_direct = sorted(direct - release)
    only_release = sorted(release - direct)
    # Assert
    assert not only_direct and not only_release, (
        "the release build and the direct build disagree — "
        f"only in the direct build: {only_direct}; "
        f"only in the release build: {only_release}"
    )
