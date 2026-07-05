"""Audit umbrella `scitex` pyproject.toml pins against PyPI latest.

The umbrella package may declare its peer dependencies in either of
two PEP 508 styles:

* `"scitex-io>=0.2.0"` — **minimum-compatible version** (normal Python
  convention). PS-170 does NOT flag this. Reproducibility of a release
  snapshot is the lockfile's responsibility (`uv.lock`,
  `requirements.lock`, the release-pipeline pin file), not the
  pyproject.toml "what versions this code is compatible with" field.

* `"scitex-io==0.2.0"` — **explicit snapshot pin**. PS-170 verifies the
  pinned version against PyPI's current latest and flags drift so the
  umbrella's snapshot doesn't ship referencing a leaf that is behind
  its latest release. This is the original release-tag-driven
  `git push origin v*` automation invariant.

(Earlier versions of this rule required `==` and flagged every `>=`
declaration. That was too strict — see operator decision 2026-05-28
Telegram msg 6793: "umbrella `>=` peers is normal Python practice,
relax PS-170". The drift detection on explicit `==` pins is preserved
because it catches a real bug class.)

Run via:

    scitex-dev audit-umbrella-pins [PATH]

PATH defaults to the cwd. PS-170 drift is **warn-only by default**
(exit 0) so an upstream leaf release that briefly outruns the
umbrella's ``==`` pin does not cascade into red CI on the umbrella's
own `tests` workflow + every downstream consumer audit. Pass
``--strict`` to restore the old fail-on-drift behaviour (use this in
the release-pipeline pre-publish gate). See the 2026-06-09 (scitex-dev
0.17.8) entry in CHANGELOG for the motivating incident — 0.17.7
shipped with PS-170 severity=error and ~12 ecosystem CI reds piled up
in the operator inbox in a single morning.

Network access required for the drift check — queries
https://pypi.org/pypi/<pkg>/json.

The audit only fires on the umbrella package (pyproject.toml `name =
"scitex"`); on any other package it exits 0 silently so it's safe to
wire into a shared CI matrix step.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import click

UMBRELLA_NAME = "scitex"
# Match any of: scitex-X, figrecipe, newb, socialia (the publishable
# ecosystem leaves). Optional extras spec, then a PEP 508 operator and
# version. Both fields are optional (a bare `"scitex-io"` is valid
# PEP 508).
_PIN_LINE_RE = re.compile(
    r'"(scitex-[a-z0-9-]+|figrecipe|newb|socialia)(\[[^\]]*\])?'
    r"(==|>=|~=|<=|<|>|!=)?"
    r'([0-9][0-9A-Za-z.\-]*)?"'
)
_NAME_RE = re.compile(r'^\s*name\s*=\s*"([^"]+)"', re.MULTILINE)


def _default_pypi_latest(pkg: str, timeout: float = 10.0) -> Optional[str]:
    """Real PyPI lookup. Returns None on any network / parse failure."""
    url = f"https://pypi.org/pypi/{pkg}/json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.load(resp)
        return data.get("info", {}).get("version")
    except (urllib.error.URLError, json.JSONDecodeError, KeyError):
        return None


# Module-level alias for backwards compatibility with anything that
# imported `_pypi_latest` from this module before the DI refactor.
_pypi_latest = _default_pypi_latest


def audit_umbrella_pins(
    repo: Path,
    *,
    _pypi_query: Optional[Callable[[str], Optional[str]]] = None,
) -> list[str]:
    """Return a list of violation strings. Empty list = clean.

    Only fires on the umbrella package (pyproject.toml ``name = "scitex"``).
    On any other package, returns ``[]`` silently.

    Behaviour by declared pin style:

    * ``"scitex-X>=A.B.C"`` (or any non-``==`` operator, or no operator
      at all) — accepted as a minimum-compatible declaration; not
      flagged, no PyPI lookup. The lockfile owns reproducibility.

    * ``"scitex-X==A.B.C"`` — explicit snapshot pin. PyPI's current
      latest for ``scitex-X`` is fetched; mismatch is flagged as
      ``PS-170`` (drift). PyPI lookup failure (network / timeout) is
      flagged as ``PS-170W`` (warning, the caller decides whether to
      block CI on it via ``--allow-network-error``).

    The ``_pypi_query`` kwarg is a DI seam for tests: pass a stub
    callable ``(pkg: str) -> Optional[str]`` to avoid real network in
    unit tests. PA-306 (no mocks) satisfied by dependency injection;
    no ``unittest.mock`` or ``monkeypatch`` needed.
    """
    # Resolve the PyPI lookup callable AT CALL TIME so tests can swap
    # `_default_pypi_latest` at module level (the CLI path has no DI seam
    # of its own). Avoids a stale module-import-time capture.
    if _pypi_query is None:
        _pypi_query = _default_pypi_latest
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return []
    txt = pyproject.read_text(errors="ignore")
    name_match = _NAME_RE.search(txt)
    if not name_match or name_match.group(1).strip() != UMBRELLA_NAME:
        return []  # only audit the umbrella

    seen: set[str] = set()
    violations: list[str] = []
    for match in _PIN_LINE_RE.finditer(txt):
        pkg = match.group(1)
        extras = match.group(2) or ""
        op = match.group(3) or ""
        ver = match.group(4) or ""
        key = pkg + extras
        if key in seen:
            continue
        seen.add(key)

        # Only drift-check explicit `==` pins. Any other operator
        # (>=, ~=, <=, <, >, !=) or no operator at all is a
        # minimum-compatible declaration -- not a release-snapshot pin
        # -- so PS-170 has nothing to verify against (no "latest" is
        # implied). Reproducibility for release snapshots lives in the
        # lockfile.
        if op != "==":
            continue

        latest = _pypi_query(pkg)
        if latest is None:
            # PyPI query failed -- don't block CI on transient network,
            # but flag as warning. The CLI caller decides whether to
            # treat this as a hard failure (`--allow-network-error`
            # downgrades it to exit 0).
            violations.append(
                f"PS-170W: could not resolve PyPI latest for {pkg!r} "
                f"(network/timeout). Pin declared as =={ver}."
            )
            continue
        if ver != latest:
            violations.append(
                f"PS-170: {pkg}{extras}=={ver} but PyPI latest is "
                f"{latest}. Bump the umbrella pin."
            )

    return violations


@click.command(
    "audit-umbrella-pins",
    epilog=(
        "Example:\n"
        "  $ scitex-dev ecosystem audit-umbrella-pins .\n"
        "  $ scitex-dev ecosystem audit-umbrella-pins /home/me/proj/scitex-python --strict\n"
        "  $ scitex-dev ecosystem audit-umbrella-pins . --strict --allow-network-error\n"
    ),
)
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.cwd,
)
@click.option(
    "--allow-network-error",
    is_flag=True,
    help=(
        "Only meaningful with --strict: treat PyPI lookup failures as "
        "warnings (exit 0) instead of hard failures (exit 1)."
    ),
)
@click.option(
    "--strict",
    is_flag=True,
    help=(
        "Treat PS-170 drift as ERROR (exit 1). Default is WARN-ONLY: "
        "drift is printed to stderr and the command exits 0, so an "
        "upstream scitex-* leaf publishing a newer wheel before the "
        "umbrella's `==` pin has caught up does NOT cascade into a CI "
        "failure on every consumer / umbrella-tests workflow run. Use "
        "--strict in the umbrella's release-pipeline pre-publish gate "
        "where stale pins MUST block a tag push."
    ),
)
def cli(path: Path, allow_network_error: bool, strict: bool) -> None:
    """Audit umbrella ``==`` pin freshness vs PyPI latest.

    Non-``==`` declarations (``>=``, ``~=``, no operator, etc.) are
    accepted as PEP 508 minimum-compatible declarations and are NOT
    flagged. Only explicit ``==`` pins are drift-checked against PyPI.

    **Severity (2026-06-09 — scitex-dev 0.17.8):** PS-170 drift is
    warn-only by default. The earlier error-by-default behaviour cascaded
    into 12+ ecosystem CI failures every time a single leaf released a
    new patch wheel ahead of the umbrella pin bump. The drift is still
    surfaced (printed to stderr with a ``WARN:`` prefix), but exit is 0
    so consumer CI stays green. Pass ``--strict`` to restore the old
    fail-on-drift behaviour for release-pipeline use.

    Example::

        $ scitex-dev ecosystem audit-umbrella-pins .
        $ scitex-dev ecosystem audit-umbrella-pins . --strict
    """
    violations = audit_umbrella_pins(path)
    if not violations:
        click.echo(f"SUCC: {path}/pyproject.toml: all umbrella pins fresh")
        sys.exit(0)

    hard_violations = [v for v in violations if not v.startswith("PS-170W")]
    prefix = "ERRO" if strict else "WARN"
    for v in violations:
        click.echo(f"{prefix}: {path}/pyproject.toml: {v}", err=True)

    # Default (no --strict): drift is informational. Exit 0 so an
    # upstream patch release does not turn into a fleet-wide CI red.
    if not strict:
        sys.exit(0)
    # --strict: hard fail on drift; --allow-network-error downgrades
    # the network-flake case (PS-170W only) to exit 0.
    if hard_violations or not allow_network_error:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    cli()
