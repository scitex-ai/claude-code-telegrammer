"""PS-211 / PS-212 — layered testing convention: tests/smoke/ + tests/e2e/.

The scitex-* ecosystem standardizes on four test directories:

  tests/<pkg>/       — unit tests (1:1 mirror of src/<pkg>/)        PS-201..207
  tests/integration/ — Python-level cross-module / cross-package
  tests/smoke/       — fast (<60s) subprocess-driven CLI happy-path tests
                       pytest marker `smoke`; runs on every PR.            PS-211
  tests/e2e/         — slow end-to-end workflows against real subsystems
                       pytest marker `e2e`; gated by `RUN_E2E=1` env var
                       and skipped by default.                              PS-212

Both PS-211 and PS-212 are WARN-only initially so packages can adopt the
convention gradually. Promote to E once the ecosystem has converged.

Opt-out for packages with no CLI / no end-to-end story: add

    [tool.scitex_dev]
    no_cli = true     # exempts PS-211
    no_e2e = true     # exempts PS-212

to pyproject.toml. (`no_cli` implies `no_e2e` since e2e workflows almost
always drive the CLI.)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# pyproject.toml opt-out flags
# ---------------------------------------------------------------------------

_TOOL_BLOCK_RE = re.compile(
    r"^\[tool\.scitex[_-]dev\](.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
_NO_CLI_RE = re.compile(r"^\s*no_cli\s*=\s*true\s*$", re.MULTILINE | re.IGNORECASE)
_NO_E2E_RE = re.compile(r"^\s*no_e2e\s*=\s*true\s*$", re.MULTILINE | re.IGNORECASE)


def _read_tool_flags(repo: Path) -> tuple[bool, bool]:
    """Return (no_cli, no_e2e) flags from [tool.scitex_dev] in pyproject.toml."""
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return False, False
    try:
        txt = pyproject.read_text(errors="ignore")
    except OSError:
        return False, False
    m = _TOOL_BLOCK_RE.search(txt)
    if m is None:
        return False, False
    block = m.group(1)
    no_cli = bool(_NO_CLI_RE.search(block))
    no_e2e = no_cli or bool(_NO_E2E_RE.search(block))
    return no_cli, no_e2e


# ---------------------------------------------------------------------------
# pytest marker registration in pyproject.toml
# ---------------------------------------------------------------------------

_MARKERS_BLOCK_RE = re.compile(
    r"^markers\s*=\s*\[(.*?)^\]",
    re.MULTILINE | re.DOTALL,
)


def _registered_markers(repo: Path) -> set[str]:
    """Return the set of pytest marker names registered in pyproject.toml.

    Looks for `markers = [...]` under `[tool.pytest.ini_options]`. Only the
    marker name (token before `:`) is extracted.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return set()
    try:
        txt = pyproject.read_text(errors="ignore")
    except OSError:
        return set()
    out: set[str] = set()
    for m in _MARKERS_BLOCK_RE.finditer(txt):
        for line in m.group(1).splitlines():
            line = line.strip().strip(",").strip()
            if not line or line.startswith("#"):
                continue
            # Strip surrounding quotes, then take the part before `:`.
            stripped = line.strip("\"'")
            name = stripped.split(":", 1)[0].strip()
            if name:
                out.add(name)
    return out


# ---------------------------------------------------------------------------
# Layer-directory probes
# ---------------------------------------------------------------------------


def _has_test_files(dir_path: Path) -> bool:
    if not dir_path.is_dir():
        return False
    return any(
        p.name.startswith("test_") and p.suffix == ".py" for p in dir_path.iterdir()
    )


# ---------------------------------------------------------------------------
# Rule checks
# ---------------------------------------------------------------------------


def check_ps211_smoke_layer(repo: Path, Violation: type, out: list[Any]) -> None:
    """PS-211 — tests/smoke/ + `smoke` marker registration.

    A package satisfies PS-211 when BOTH:
      - tests/smoke/ contains at least one test_*.py, AND
      - `smoke` is in [tool.pytest.ini_options].markers (so `-m smoke` works
        without `PytestUnknownMarkWarning`).

    Exempt: pyproject.toml declares `[tool.scitex_dev] no_cli = true`.
    """
    no_cli, _ = _read_tool_flags(repo)
    if no_cli:
        return

    smoke_dir = repo / "tests" / "smoke"
    has_smoke_tests = _has_test_files(smoke_dir)
    has_marker = "smoke" in _registered_markers(repo)

    if not has_smoke_tests:
        out.append(
            Violation(
                "PS-211",
                str(smoke_dir),
                (
                    "missing tests/smoke/ layer (fast <60s subprocess-driven CLI "
                    "happy-path tests). Add at least one tests/smoke/test_*.py "
                    "and register the `smoke` pytest marker in pyproject.toml. "
                    "If this package has no CLI, opt out with "
                    "`[tool.scitex_dev]\\nno_cli = true` in pyproject.toml."
                ),
            )
        )
        return

    if not has_marker:
        out.append(
            Violation(
                "PS-211",
                str(repo / "pyproject.toml"),
                (
                    "tests/smoke/ exists but the `smoke` pytest marker is not "
                    "registered in `[tool.pytest.ini_options].markers`. Add "
                    '`"smoke: fast CLI happy-path tests (<60s, runs on every PR)"` '
                    "so `pytest -m smoke` works without PytestUnknownMarkWarning."
                ),
            )
        )


def check_ps212_e2e_layer(repo: Path, Violation: type, out: list[Any]) -> None:
    """PS-212 — tests/e2e/ + `e2e` marker registration + RUN_E2E gating.

    A package satisfies PS-212 when BOTH:
      - tests/e2e/ contains at least one test_*.py, AND
      - `e2e` is in [tool.pytest.ini_options].markers.

    Exempt: `no_cli = true` or `no_e2e = true` under `[tool.scitex_dev]`.
    """
    _, no_e2e = _read_tool_flags(repo)
    if no_e2e:
        return

    e2e_dir = repo / "tests" / "e2e"
    has_e2e_tests = _has_test_files(e2e_dir)
    has_marker = "e2e" in _registered_markers(repo)

    if not has_e2e_tests:
        out.append(
            Violation(
                "PS-212",
                str(e2e_dir),
                (
                    "missing tests/e2e/ layer (slow end-to-end workflows against "
                    "real subsystems). Add at least one tests/e2e/test_*.py, "
                    "register the `e2e` pytest marker in pyproject.toml, and "
                    "gate execution via the `RUN_E2E=1` env var (skipped by "
                    "default). If this package has no end-to-end story, opt out "
                    "with `[tool.scitex_dev]\\nno_e2e = true` in pyproject.toml."
                ),
            )
        )
        return

    if not has_marker:
        out.append(
            Violation(
                "PS-212",
                str(repo / "pyproject.toml"),
                (
                    "tests/e2e/ exists but the `e2e` pytest marker is not "
                    "registered in `[tool.pytest.ini_options].markers`. Add "
                    '`"e2e: end-to-end workflows (slow, gated by RUN_E2E=1)"` '
                    "so `pytest -m e2e` works without PytestUnknownMarkWarning."
                ),
            )
        )
