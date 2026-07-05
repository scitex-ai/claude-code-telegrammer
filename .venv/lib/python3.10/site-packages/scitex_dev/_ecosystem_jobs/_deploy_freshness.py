#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``deploy-freshness`` cron body — ecosystem-level drift detector.

Lives under ``_ecosystem_jobs/`` (not ``_cli/cron/``) because it is a
CROSS-PACKAGE control-plane job, not one of scitex-dev's own
package-internal crons. Installed via the federated path:
``scitex-dev ecosystem cron`` discovers it through the
``scitex_dev.jobs`` entry-point group that scitex-dev itself
registers (treating scitex-dev as a leaf of itself — the dual-mode
principle applied to scitex-dev).

Two drift kinds, one sweep
--------------------------
A managed ``service`` / ``timer`` unit can fall out of date in two
distinct ways. ``deploy-freshness`` detects BOTH on the same tick and
routes each to the cheapest repair:

1. **Wheel drift (PyPI-version path).** The unit runs a *non-editable*
   (wheel) install whose ``importlib.metadata`` version trails the
   latest release on PyPI. This is the original bug: the operator
   pulled scitex-todo develop on ``/work`` to get UI updates, but the
   systemd ``--user`` unit on port 8051 was installed against the PyPI
   wheel from before the pull, and kept serving the stale code
   invisibly. Repair (``--apply``): ``pip install -U <pkg>`` +
   ``systemctl --user restart <unit>``.

2. **Editable-source drift (this module's second path).** On the dev
   box, packages like scitex-todo are installed *editable* (PEP 660)
   from a git checkout (e.g. ``~/proj/scitex-todo`` on ``develop``). A
   ``git pull`` updates the source on disk but NOT the version string,
   so the version-vs-PyPI compare in path (1) can't see that the
   running unit is serving stale code. Here drift is detected
   structurally instead: the unit is editable (PEP 610
   ``direct_url.json`` with ``dir_info.editable == true``) AND the
   latest git commit in the source dir is NEWER than the unit's
   ``ActiveEnterTimestamp`` (when systemd last (re)started it). Repair
   (``--apply``): ``systemctl --user restart <unit>`` ONLY — no
   ``pip``; the new source is already in place, the running process is
   just holding the old import.

   We deliberately do NOT ``git pull`` for the operator. The pull is
   the operator's deliberate act (they choose when to take new code);
   only the *restart* — the mechanical step that is easy to forget —
   is automated.

Routing: a unit's owning distribution is editable XOR wheel. The
editable check runs first; if (and only if) the distribution is NOT
editable do we fall through to the unchanged PyPI-version path, so
every non-editable install keeps behaving exactly as before.

Schedule
--------
``*/30 * * * *`` (every 30 min). Fast enough to catch drift before the
operator notices, infrequent enough not to thrash PyPI.

Robustness
----------
Drift detection runs on every tick; repair is gated behind ``--apply``
(the production crontab line passes ``--apply``). Each per-service step
is failure-isolated:

* PyPI 503 → logged + skipped, the next tick retries.
* ``pip install`` failure → logged + the service stays on the stale
  version (no auto-rollback ceremony — operator inspects manually if
  the audit log shows repeated failures).
* a ``git`` / ``systemctl show`` hiccup on an editable unit → logged +
  skipped, the sweep continues with the next unit.
* ``systemctl restart`` failure → logged + counted, the loop keeps
  reconciling the rest of the services.

Exit code is non-zero only when the whole sweep itself errors (the
``discover_jobs`` call raises, config-level mis-setup, etc.) — never
on a per-service hiccup the next tick will sort out.

Seams (PA-306 / STX-NM)
-----------------------
``http_runner``, ``pip_runner``, ``systemctl_runner``, ``which``,
``metadata_lookup``, ``direct_url_lookup``, ``git_runner`` and
``source_mtime`` are keyword arguments — tests pass real fakes and
``tmp_path``-rooted log files without ``unittest.mock`` or
``monkeypatch``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Paths / defaults
# ---------------------------------------------------------------------------


def _default_log_path() -> Path:
    """Return ``~/.scitex/dev/logs/cron-deploy-freshness.log`` (env-aware)."""
    import os

    base = os.environ.get("SCITEX_DIR") or os.path.join(
        os.path.expanduser("~"), ".scitex"
    )
    return Path(base) / "dev" / "logs" / "cron-deploy-freshness.log"


_PYPI_JSON_URL = "https://pypi.org/pypi/{name}/json"
_HTTP_TIMEOUT_S = 10.0
_PIP_TIMEOUT_S = 180.0
_SYSTEMCTL_TIMEOUT_S = 30.0
_GIT_TIMEOUT_S = 15.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceOutcome:
    """Per-service outcome of one ``deploy-freshness`` sweep."""

    job_name: str
    binary: str | None
    package: str | None
    installed_version: str | None
    latest_version: str | None
    drift: bool
    action: str  # ok / would-update / updated / skipped / error
    detail: str = ""
    mode: str = "wheel"  # wheel | editable — which drift path ran


@dataclass(frozen=True)
class DeployFreshnessResult:
    """Aggregate outcome of one ``deploy-freshness`` cron tick."""

    log_path: str
    services_checked: int = 0
    drift_count: int = 0
    updated_count: int = 0
    error_count: int = 0
    outcomes: tuple[ServiceOutcome, ...] = field(default_factory=tuple)
    error: str | None = None


# ---------------------------------------------------------------------------
# Default runners (test-fakable)
# ---------------------------------------------------------------------------


def _default_http_runner(url: str, timeout: float) -> tuple[int, bytes]:
    """Real ``urllib`` GET. Tests pass their own fake."""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.getcode(), resp.read()


def _default_pip_runner(args: list[str]) -> subprocess.CompletedProcess:
    """Real ``pip`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["pip", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=_PIP_TIMEOUT_S,
    )


def _default_systemctl_runner(
    args: list[str],
    *,
    timeout: float = _SYSTEMCTL_TIMEOUT_S,
) -> subprocess.CompletedProcess:
    """Real ``systemctl --user`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _default_direct_url_lookup(dist_name: str) -> str | None:
    """Return the PEP 610 ``direct_url.json`` text for ``dist_name``, or None.

    Reads via ``importlib.metadata.distribution(...).read_text(...)``. A
    *wheel* (PyPI) install has no ``direct_url.json`` and this returns
    ``None``; an editable / VCS / local install has one. Tests pass
    their own fake.
    """
    try:
        dist = metadata.distribution(dist_name)
    except metadata.PackageNotFoundError:
        return None
    try:
        return dist.read_text("direct_url.json")
    except Exception:  # noqa: BLE001 — best-effort metadata read
        return None


def _default_git_runner(srcdir: str) -> str | None:
    """Return the ISO commit time of the latest commit in ``srcdir``.

    Shells ``git -C <srcdir> log -1 --format=%cI``. Returns ``None`` when
    ``srcdir`` is not a git work tree (the caller falls back to
    ``source_mtime``), or on any git failure. Tests pass their own fake.
    """
    try:
        r = subprocess.run(
            ["git", "-C", srcdir, "log", "-1", "--format=%cI"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    out = (r.stdout or "").strip()
    return out or None


def _default_source_mtime(srcdir: str) -> float | None:
    """Return the max mtime of tracked ``*.py`` under ``<srcdir>/src``.

    Fallback freshness signal for an editable install whose source dir
    is NOT a git work tree (``git_runner`` returned ``None``). Returns a
    POSIX timestamp (float), or ``None`` when no ``*.py`` is found.
    Tests pass their own fake.
    """
    root = Path(srcdir) / "src"
    if not root.is_dir():
        # Fall back to the whole source dir if there is no src/ layout.
        root = Path(srcdir)
    if not root.is_dir():
        return None
    newest: float | None = None
    try:
        for py in root.rglob("*.py"):
            try:
                m = py.stat().st_mtime
            except OSError:
                continue
            if newest is None or m > newest:
                newest = m
    except OSError:
        return None
    return newest


# ---------------------------------------------------------------------------
# Helpers — pure, test-friendly
# ---------------------------------------------------------------------------


def _extract_binary(command: str) -> str | None:
    """Return the first token of ``command`` (the executable path/name)."""
    import shlex

    tokens = shlex.split(command or "")
    if not tokens:
        return None
    return tokens[0]


def _binary_basename(binary: str) -> str:
    """Return the basename of ``binary``."""
    return Path(binary).name


def _resolve_owning_distribution(
    binary: str,
    *,
    metadata_lookup=metadata.entry_points,
) -> tuple[str, str] | None:
    """Return ``(distribution_name, installed_version)`` for the console
    script ``binary``, or ``None`` if no console-script entry matches.
    """
    name = _binary_basename(binary)
    try:
        eps = metadata_lookup(group="console_scripts")
    except TypeError:
        eps = [ep for ep in metadata_lookup() if ep.group == "console_scripts"]
    for ep in eps:
        if ep.name != name:
            continue
        dist = getattr(ep, "dist", None)
        if dist is None:
            continue
        try:
            return (dist.metadata["Name"], dist.version)
        except Exception:  # noqa: BLE001
            continue
    return None


def _fetch_latest_pypi_version(
    package: str,
    *,
    http_runner: Callable[[str, float], tuple[int, bytes]] | None = None,
) -> str | None:
    """Return ``info.version`` of ``package`` from PyPI JSON, or None.

    Fail-open: any HTTP / JSON / network failure returns ``None``.
    """
    runner = http_runner or _default_http_runner
    url = _PYPI_JSON_URL.format(name=package)
    try:
        status, body = runner(url, _HTTP_TIMEOUT_S)
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    if status != 200:
        return None
    try:
        doc = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    info = doc.get("info")
    if not isinstance(info, dict):
        return None
    version = info.get("version")
    return version if isinstance(version, str) else None


def _version_tuple(text: str) -> tuple[int, ...]:
    """Lossy SemVer-ish parse — leading numeric components."""
    import re

    parts: list[int] = []
    for chunk in re.split(r"[^0-9]+", text or ""):
        if not chunk:
            continue
        try:
            parts.append(int(chunk))
        except ValueError:
            break
    return tuple(parts)


def _is_drifted(installed: str, latest: str) -> bool:
    """Return True when ``installed`` < ``latest`` per the tuple parse."""
    a = _version_tuple(installed)
    b = _version_tuple(latest)
    if not a or not b:
        return False
    return a < b


# ---------------------------------------------------------------------------
# Editable-source helpers — pure, test-friendly
# ---------------------------------------------------------------------------


def _editable_source_dir(direct_url_text: str | None) -> str | None:
    """Return the editable source dir from ``direct_url.json`` text, or None.

    PEP 610 shape for an editable install::

        {"url": "file:///home/op/proj/scitex-todo",
         "dir_info": {"editable": true}}

    Returns the local filesystem path (``file://`` stripped) ONLY when
    ``dir_info.editable`` is truthy. A wheel install (``None`` text), a
    non-editable VCS/local install (``dir_info.editable`` absent/false),
    or malformed JSON all return ``None`` — i.e. "not an editable
    install", which routes the unit to the PyPI-version path.
    """
    if not direct_url_text:
        return None
    try:
        doc = json.loads(direct_url_text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    dir_info = doc.get("dir_info")
    if not isinstance(dir_info, dict) or not dir_info.get("editable"):
        return None
    url = doc.get("url")
    if not isinstance(url, str) or not url:
        return None
    return _file_url_to_path(url)


def _file_url_to_path(url: str) -> str:
    """Convert a ``file://`` URL to a local path; pass other strings through."""
    if url.startswith("file://"):
        from urllib.parse import unquote, urlparse

        parsed = urlparse(url)
        return unquote(parsed.path)
    return url


def _parse_iso_to_utc(text: str | None) -> datetime | None:
    """Parse a git ``%cI`` ISO-8601 timestamp into an aware UTC datetime.

    ``git log --format=%cI`` emits e.g. ``2026-06-25T00:36:43+09:00``.
    Returns ``None`` on empty / unparseable input.
    """
    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_systemd_timestamp_to_utc(text: str | None) -> datetime | None:
    """Parse a systemd ``ActiveEnterTimestamp`` value into aware UTC.

    ``systemctl show -p ActiveEnterTimestamp`` emits the human form, e.g.
    ``Wed 2026-06-25 00:36:43 JST`` (weekday, date, time, tz-abbrev). A
    unit that has never been active emits an empty value (``n/a`` or
    nothing) → returns ``None`` (treated as "no start time known", which
    is conservatively NOT drift on its own).

    The trailing tz-abbrev (``JST`` / ``UTC`` / ``AEST`` …) is not
    portably parseable by ``datetime`` (abbreviations are ambiguous), so
    we drop it and parse only the wall-clock fields, interpreting them in
    the LOCAL timezone of the box running the cron (the same box systemd
    reports from), then normalise to UTC. The compare stays
    apples-to-apples because the git ``%cI`` time carries its own
    explicit offset and we normalise both sides to UTC.
    """
    if not text:
        return None
    raw = text.strip()
    if not raw or raw.lower() in {"n/a", "0", "-"}:
        return None
    # Strip a leading weekday token ("Wed ") if present.
    parts = raw.split()
    if parts and len(parts[0]) == 3 and parts[0].isalpha():
        parts = parts[1:]
    # Drop a trailing tz-abbrev token (non-numeric, e.g. "JST").
    if parts and not any(ch.isdigit() for ch in parts[-1]):
        parts = parts[:-1]
    if len(parts) < 2:
        return None
    stamp = f"{parts[0]} {parts[1]}"
    try:
        naive = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    # Interpret in the box's local timezone, then convert to UTC.
    local = naive.astimezone()
    return local.astimezone(timezone.utc)


def _read_active_enter_timestamp(
    unit: str,
    *,
    systemctl_runner: Callable[..., subprocess.CompletedProcess],
) -> datetime | None:
    """Return the unit's ``ActiveEnterTimestamp`` as aware UTC, or None.

    Shells (via the injected runner) ``systemctl --user show <unit> -p
    ActiveEnterTimestamp``, whose stdout is ``ActiveEnterTimestamp=<val>``.
    Any failure / unparseable value returns ``None``.
    """
    r = systemctl_runner(["show", unit, "-p", "ActiveEnterTimestamp"])
    if getattr(r, "returncode", 1) != 0:
        return None
    out = (getattr(r, "stdout", "") or "").strip()
    # Expect a single "ActiveEnterTimestamp=<value>" line.
    value = out
    if "=" in out:
        value = out.split("=", 1)[1].strip()
    return _parse_systemd_timestamp_to_utc(value)


def _source_commit_time(
    srcdir: str,
    *,
    git_runner: Callable[[str], str | None],
    source_mtime: Callable[[str], float | None],
) -> datetime | None:
    """Return the freshness time of editable source ``srcdir`` as UTC.

    Primary: latest git commit time (``git_runner`` → ``%cI`` ISO).
    Fallback (not a git work tree): the max mtime of tracked ``*.py``
    under ``<srcdir>/src`` (``source_mtime``). Returns ``None`` when
    neither yields a usable time.
    """
    iso = git_runner(srcdir)
    dt = _parse_iso_to_utc(iso)
    if dt is not None:
        return dt
    mtime = source_mtime(srcdir)
    if mtime is None:
        return None
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Per-service check — editable path
# ---------------------------------------------------------------------------


def _check_editable_service(
    *,
    job,
    binary: str,
    package: str,
    installed: str,
    srcdir: str,
    apply: bool,
    systemctl_runner: Callable[..., subprocess.CompletedProcess],
    git_runner: Callable[[str], str | None],
    source_mtime: Callable[[str], float | None],
) -> ServiceOutcome:
    """Drift check for an EDITABLE unit (source-time vs unit-start-time).

    Drift = the source's latest commit is NEWER than the unit's
    ``ActiveEnterTimestamp``. Repair (``--apply``) is a restart ONLY —
    the editable source is already on disk; no ``pip`` is run.
    """
    from ..jobs._systemd import systemd_unit_name

    unit = systemd_unit_name(job)

    def _editable(action: str, *, drift: bool, detail: str) -> ServiceOutcome:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=None,  # N/A for editable — no PyPI compare
            drift=drift,
            action=action,
            detail=detail,
            mode="editable",
        )

    src_time = _source_commit_time(
        srcdir, git_runner=git_runner, source_mtime=source_mtime
    )
    if src_time is None:
        return _editable(
            "skipped",
            drift=False,
            detail=f"editable {srcdir}: no git commit time / source mtime",
        )

    started = _read_active_enter_timestamp(unit, systemctl_runner=systemctl_runner)
    if started is None:
        return _editable(
            "skipped",
            drift=False,
            detail=(
                f"editable {srcdir}: could not read {unit} "
                f"ActiveEnterTimestamp (unit inactive / systemctl error)"
            ),
        )

    if src_time <= started:
        return _editable(
            "ok",
            drift=False,
            detail=(
                f"editable {srcdir}: source {src_time.isoformat()} "
                f"<= unit-start {started.isoformat()}"
            ),
        )

    # Source is newer than the running unit → stale editable code.
    if not apply:
        return _editable(
            "would-update",
            drift=True,
            detail=(
                f"editable {srcdir}: source {src_time.isoformat()} "
                f"> unit-start {started.isoformat()} (dry-run; would restart "
                f"{unit}, no pip)"
            ),
        )

    try:
        rr = systemctl_runner(["restart", unit])
    except Exception as exc:  # noqa: BLE001
        return _editable(
            "error",
            drift=True,
            detail=f"editable {srcdir}: systemctl restart {unit} raised: {exc}",
        )
    if getattr(rr, "returncode", 1) != 0:
        tail = (getattr(rr, "stderr", "") or getattr(rr, "stdout", "") or "").strip()
        return _editable(
            "error",
            drift=True,
            detail=(
                f"editable {srcdir}: systemctl restart {unit} "
                f"rc={rr.returncode}: {tail[:200]}"
            ),
        )

    return _editable(
        "updated",
        drift=True,
        detail=(
            f"editable {srcdir}: source {src_time.isoformat()} newer than "
            f"unit-start {started.isoformat()} -> restarted {unit} (no pip)"
        ),
    )


# ---------------------------------------------------------------------------
# Per-service check — top-level router
# ---------------------------------------------------------------------------


def check_one_service(
    *,
    job,
    apply: bool,
    http_runner: Callable[[str, float], tuple[int, bytes]] | None = None,
    pip_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    systemctl_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    metadata_lookup=None,
    which: Callable[[str], str | None] = shutil.which,
    direct_url_lookup: Callable[[str], str | None] | None = None,
    git_runner: Callable[[str], str | None] | None = None,
    source_mtime: Callable[[str], float | None] | None = None,
) -> ServiceOutcome:
    """Check one JobSpec for drift; return a structured outcome.

    Routes to one of two drift paths by install kind:

    * **editable** (PEP 610 ``direct_url.json`` with
      ``dir_info.editable``) → source-commit-time vs unit
      ``ActiveEnterTimestamp``; repair is a restart only (no pip).
    * **wheel** (everything else, the default) → installed version vs
      latest PyPI; repair is ``pip install -U`` + restart. Unchanged
      from the original behaviour.
    """
    binary = _extract_binary(job.command)
    if binary is None:
        return ServiceOutcome(
            job_name=job.name,
            binary=None,
            package=None,
            installed_version=None,
            latest_version=None,
            drift=False,
            action="skipped",
            detail="JobSpec.command has no first token",
        )

    owner = _resolve_owning_distribution(
        binary, metadata_lookup=metadata_lookup or metadata.entry_points
    )
    if owner is None:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=None,
            installed_version=None,
            latest_version=None,
            drift=False,
            action="skipped",
            detail=(
                "no console-script entry maps to "
                f"{_binary_basename(binary)!r} (not pip-installed?)"
            ),
        )

    package, installed = owner

    # --- Editable-source path (PEP 610). Runs first; only NON-editable
    #     installs fall through to the unchanged PyPI-version path. ---
    du_lookup = direct_url_lookup or _default_direct_url_lookup
    srcdir = _editable_source_dir(du_lookup(package))
    if srcdir is not None:
        return _check_editable_service(
            job=job,
            binary=binary,
            package=package,
            installed=installed,
            srcdir=srcdir,
            apply=apply,
            systemctl_runner=systemctl_runner or _default_systemctl_runner,
            git_runner=git_runner or _default_git_runner,
            source_mtime=source_mtime or _default_source_mtime,
        )

    # --- Wheel path (PyPI version compare). Unchanged behaviour. ---
    latest = _fetch_latest_pypi_version(package, http_runner=http_runner)
    if latest is None:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=None,
            drift=False,
            action="skipped",
            detail="could not fetch latest PyPI version (network / JSON)",
        )

    drifted = _is_drifted(installed, latest)
    if not drifted:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=False,
            action="ok",
        )

    if not apply:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="would-update",
            detail=f"installed={installed} latest={latest} (dry-run)",
        )

    pip = pip_runner or _default_pip_runner
    sysctl = systemctl_runner or _default_systemctl_runner

    if which("pip") is None:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="error",
            detail="pip not on PATH; cannot apply update",
        )

    try:
        r = pip(["install", "-U", package])
    except Exception as exc:  # noqa: BLE001
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="error",
            detail=f"pip install -U {package} raised: {exc}",
        )
    if r.returncode != 0:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="error",
            detail=f"pip install -U {package} rc={r.returncode}: "
            f"{(r.stderr or r.stdout).strip()[:200]}",
        )

    from ..jobs._systemd import systemd_unit_name

    unit = systemd_unit_name(job)
    try:
        rr = sysctl(["restart", unit])
    except Exception as exc:  # noqa: BLE001
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="error",
            detail=f"systemctl restart {unit} raised: {exc}",
        )
    if rr.returncode != 0:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="error",
            detail=f"systemctl restart {unit} rc={rr.returncode}: "
            f"{(rr.stderr or rr.stdout).strip()[:200]}",
        )

    return ServiceOutcome(
        job_name=job.name,
        binary=binary,
        package=package,
        installed_version=installed,
        latest_version=latest,
        drift=True,
        action="updated",
        detail=f"{installed} -> {latest} + restarted {unit}",
    )


# ---------------------------------------------------------------------------
# Top-level body
# ---------------------------------------------------------------------------


def _append_audit_line(log_path: Path, line: str) -> None:
    """Append one structured audit line. Best-effort write."""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")
    except OSError:
        pass


def run_once(
    *,
    apply: bool = False,
    jobs_provider=None,
    log_path: Path | None = None,
    http_runner: Callable[[str, float], tuple[int, bytes]] | None = None,
    pip_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    systemctl_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    metadata_lookup=None,
    which: Callable[[str], str | None] = shutil.which,
    direct_url_lookup: Callable[[str], str | None] | None = None,
    git_runner: Callable[[str], str | None] | None = None,
    source_mtime: Callable[[str], float | None] | None = None,
    now: Callable[[], float] | None = None,
) -> DeployFreshnessResult:
    """One deploy-freshness sweep across every kind=service+timer JobSpec."""
    log = (log_path or _default_log_path()).expanduser()
    import time

    clock = now or time.time
    timestamp = datetime.fromtimestamp(clock(), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%MZ"
    )

    if jobs_provider is None:
        from ..jobs import jobs_of_kind

        def jobs_provider():  # noqa: E306
            return list(jobs_of_kind("service")) + list(jobs_of_kind("timer"))

    try:
        services = jobs_provider()
    except Exception as exc:  # noqa: BLE001
        msg = f"discover_jobs failed: {exc.__class__.__name__}: {exc}"
        _append_audit_line(log, f"[deploy-freshness {timestamp}] ERROR: {msg}")
        return DeployFreshnessResult(log_path=str(log), error=msg)

    outcomes: list[ServiceOutcome] = []
    drift = 0
    updated = 0
    errors = 0
    for job in services:
        outcome = check_one_service(
            job=job,
            apply=apply,
            http_runner=http_runner,
            pip_runner=pip_runner,
            systemctl_runner=systemctl_runner,
            metadata_lookup=metadata_lookup,
            which=which,
            direct_url_lookup=direct_url_lookup,
            git_runner=git_runner,
            source_mtime=source_mtime,
        )
        outcomes.append(outcome)
        if outcome.drift:
            drift += 1
        if outcome.action == "updated":
            updated += 1
        if outcome.action == "error":
            errors += 1
        line = (
            f"[deploy-freshness {timestamp}] job={outcome.job_name} "
            f"mode={outcome.mode} pkg={outcome.package} "
            f"installed={outcome.installed_version} "
            f"latest={outcome.latest_version} action={outcome.action}"
        )
        if outcome.detail:
            line += f" detail={outcome.detail!r}"
        _append_audit_line(log, line)

    summary = (
        f"[deploy-freshness {timestamp}] SUMMARY checked={len(services)} "
        f"drift={drift} updated={updated} errors={errors} apply={apply}"
    )
    _append_audit_line(log, summary)

    return DeployFreshnessResult(
        log_path=str(log),
        services_checked=len(services),
        drift_count=drift,
        updated_count=updated,
        error_count=errors,
        outcomes=tuple(outcomes),
    )


# EOF
