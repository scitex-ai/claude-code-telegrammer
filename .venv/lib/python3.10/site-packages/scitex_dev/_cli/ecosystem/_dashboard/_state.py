"""Data layer for the ecosystem dashboard.

`gather_ecosystem_state(verbosity)` returns a list of `PackageState`,
one per ECOSYSTEM entry. Higher verbosity adds slower / networked
columns:

  -v   (1, default) PKG, CAT, VER, TAG, AHEAD, BRANCH, SKIP, AUDIT_E,
                    AUDIT_W, DRIFT_LOCAL
  -vv  (2)          + PYPI, DRIFT_PYPI, CI
  -vvv (3)          + RTD, SKILLS, MCP_TOOLS, PY_APIS, TESTS, COV, LOC,
                    SKIP_RULES_LIST

Verbosity 0 collapses to PKG, AUDIT_E, DRIFT_LOCAL, CI for the at-a-
glance "what's red?" view.

All filesystem + git lookups are local-fast (~1ms each, parallel).
PyPI / RTD / GH Actions are deferred behind `verbosity >= 2`; results
are cached on the returned record so the renderer can show partial
rows immediately and fill the rest as fetches complete.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_PROJ_ROOT = Path("~/proj").expanduser()


@dataclass
class PackageState:
    pkg: str
    category: str = ""
    local_path: str = ""
    exists_locally: bool = False

    # Versions
    version_pyproject: str = ""
    version_dynamic: bool = False  # uses setuptools-scm
    tag_latest: str = ""
    pypi_latest: str = ""
    pypi_lookup_done: bool = False  # True once PyPI was queried (200 or 404)

    # Drift summary (computed)
    drift_local: str = ""  # ✓ / V≠T / V<T / V>T
    drift_pypi: str = ""  # ✓ / T>P / T<P

    # Git
    branch: str = ""
    ahead: int = 0  # commits on local branch not pushed to origin
    uncommitted: int = -1  # working-tree files with uncommitted changes
    last_commit_iso: str = ""

    # Audit gate
    has_audit_gate: bool = False
    skip_rules: list[str] = field(default_factory=list)
    audit_errors: int = -1  # -1 = not run
    audit_warnings: int = -1

    # CI — latest conclusion of EACH workflow on develop, deduped by
    # workflow name. Lets the dashboard show "F<failed> (passed/total)"
    # over all workflows attached to the branch, not just the most
    # recent run of any workflow.
    ci_status: str = ""  # success / failure / in_progress / cancelled / ""
    ci_workflows_passed: int = -1
    ci_workflows_failed: int = -1
    ci_workflows_running: int = -1

    # GitHub Releases — separate from `tag_latest` (git tag local). A
    # tag without a Release means PyPI was published but no release
    # notes / asset was attached. Diff = a release-management gap.
    # `gh_release_lookup_done` distinguishes "not yet queried"
    # (renderer shows `N/C` dim) from "queried, no release exists"
    # (renderer shows `MISSING` red — there IS a local tag, so the
    # absence of a matching GH Release is a release-pipeline gap).
    # The 2026-05-27 failure (crossref-local 0.7.4 + openalex-local 0.7.6
    # on PyPI but no GH Release) is the canonical motivator.
    gh_release_latest: str = ""
    gh_release_lookup_done: bool = False

    # Per-package dev venv state ("real" / "symlink" / "missing").
    # Cheap (one `os.lstat`), always computed because it's the canary
    # for the per-package isolation rule (see
    # `_skills/general/02_package/10_dev-venv-isolation.md`).
    venv_state: str = ""

    # Deep (verbosity >= 3)
    rtd_status: str = ""
    skills_count: int = -1
    mcp_tools: int = -1
    py_apis: int = -1
    tests_count: int = -1  # file count (legacy; cheap, basic enricher)
    tests_collected: int = -1  # pytest --collect-only -q result (medium cost)
    tests_passed: int = -1  # actual pytest run (heavy; --with-test-run)
    tests_failed: int = -1  # actual pytest run (heavy; --with-test-run)
    coverage: float = -1.0
    loc: int = -1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PackageState":
        """Rebuild a state from a `to_dict()` payload.

        Unknown keys are dropped silently so payloads emitted by a
        newer/older scitex-dev still load.
        """
        from dataclasses import fields as _fields

        names = {f.name for f in _fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def _git(repo: Path, *args: str, default: str = "") -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), *args],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip()
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return default


def _read_pyproject_version(repo: Path) -> tuple[str, bool]:
    """Return (version_str, is_dynamic). Empty string if not found."""
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return "", False
    try:
        text = pp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", False
    # Static version
    m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if m:
        return m.group(1), False
    # Dynamic
    if re.search(r'^\s*dynamic\s*=\s*\[[^\]]*"version"', text, re.MULTILINE):
        return "(dynamic)", True
    return "", False


def _read_skip_rules(repo: Path) -> list[str]:
    """Extract the skip_rules tuple from tests/develop/test_audit.py.

    Source-of-truth scan, not import-and-call: the audit gate file is
    code we generate, so the literal pattern is stable.
    """
    f = repo / "tests" / "develop" / "test_audit.py"
    if not f.is_file():
        return []
    try:
        src = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    block = re.search(r"skip_rules\s*=\s*\(([^)]*)\)", src, re.DOTALL)
    if not block:
        return []
    return re.findall(r'"([^"]+)"', block.group(1))


def _has_audit_gate(repo: Path) -> bool:
    return (repo / "tests" / "develop" / "test_audit.py").is_file()


def _uncommitted_count(repo: Path) -> int:
    """Number of working-tree paths with uncommitted changes.

    Counts `git status --porcelain` lines (one per modified, added,
    deleted, renamed, or untracked file). Cheap (~5ms per repo).
    Returns -1 if git can't be queried.
    """
    out = _git(repo, "status", "--porcelain")
    if not out:
        return 0
    return sum(1 for line in out.splitlines() if line.strip())


def _venv_state(repo: Path) -> str:
    """Classify ``<repo>/.venv``:

    - ``"real"``    — real directory (CI-parity isolated venv).
    - ``"symlink"`` — symlink, typically to a shared `~/.venv` (anti-pattern;
                      violates the per-package isolation rule, see
                      `_skills/general/02_package/10_dev-venv-isolation.md`).
    - ``"missing"`` — no ``.venv`` at the repo root.
    """
    venv = repo / ".venv"
    if venv.is_symlink():
        return "symlink"
    if venv.is_dir():
        return "real"
    return "missing"


def _latest_tag(repo: Path) -> str:
    """Most recent vX.Y.Z tag (lexical fallback if no semver)."""
    tag = _git(repo, "describe", "--tags", "--abbrev=0", "--match", "v*")
    return tag


def _branch(repo: Path) -> str:
    return _git(repo, "branch", "--show-current")


def _ahead_of_origin(repo: Path) -> int:
    """How many commits HEAD is ahead of origin/<current_branch>."""
    br = _branch(repo)
    if not br:
        return 0
    out = _git(repo, "rev-list", "--count", f"origin/{br}..HEAD")
    try:
        return int(out)
    except ValueError:
        return 0


def _last_commit_iso(repo: Path) -> str:
    """ISO timestamp of the most recent edit, considering uncommitted work.

    Returns whichever is later between:
      - last-commit timestamp (`git log -1 --format=%cI`)
      - the max mtime of any file listed in `git status --porcelain`
        (so a dirty working tree shows the actual edit moment, not
        the last clean commit's moment)

    Costs ~5–10ms per repo (one `git log`, one `git status`, then
    `stat` only on the dirty files — typically 0–10 paths).
    """
    from datetime import datetime, timezone

    last_iso = _git(repo, "log", "-1", "--format=%cI")
    porcelain = _git(repo, "status", "--porcelain")
    if not porcelain:
        return last_iso

    # Parse `git status --porcelain` lines: "XY <path>" (and renames
    # "R  old -> new"). Take the path; stat it for mtime.
    latest_mtime = 0.0
    for line in porcelain.splitlines():
        rel = line[3:] if len(line) > 3 else ""
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        rel = rel.strip().strip('"')
        if not rel:
            continue
        try:
            mt = (repo / rel).stat().st_mtime
        except OSError:
            continue
        if mt > latest_mtime:
            latest_mtime = mt

    if latest_mtime == 0.0:
        return last_iso

    dirty_iso = (
        datetime.fromtimestamp(latest_mtime, tz=timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds")
    )
    # Whichever is the larger ISO string wins. Both are in lexically
    # comparable formats (yyyy-mm-ddTHH:MM:SS±HH:MM).
    return dirty_iso if (not last_iso or dirty_iso > last_iso) else last_iso


def _count_files(path: Path, pattern: str) -> int:
    """Count matching files; -1 if path doesn't exist."""
    if not path.is_dir():
        return -1
    return sum(1 for _ in path.rglob(pattern))


def _count_loc(src_dir: Path) -> int:
    """Quick wc-style line count across .py files. -1 if no src dir."""
    if not src_dir.is_dir():
        return -1
    total = 0
    for f in src_dir.rglob("*.py"):
        try:
            total += sum(1 for _ in f.open(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return total


def _src_root(repo: Path, import_name: str) -> Path:
    """Best-effort src root: src/<pkg> if it exists, else repo/<pkg>."""
    cand = repo / "src" / import_name
    if cand.is_dir():
        return cand
    return repo / import_name


def _enrich_deep(state: PackageState) -> None:
    """Verbosity-3 columns: skills count, tests count, LOC.

    Filesystem-only — fast. MCP tools / py APIs would need package
    import, which is heavier; deferred.
    """
    repo = Path(state.local_path)
    if not repo.is_dir():
        return
    import_name = state.pkg.replace("-", "_")
    src_root = _src_root(repo, import_name)
    skills_root = src_root / "_skills"
    state.skills_count = _count_files(skills_root, "*.md")
    state.tests_count = _count_files(repo / "tests", "test_*.py")
    state.loc = _count_loc(src_root)


def _enrich_tests_collect(state: PackageState) -> None:
    """Run ``pytest --collect-only -q`` inside the pkg's own venv.

    Populates ``tests_collected`` — the real number of pytest test items
    (test functions / parametrize cases), not the file count. Costs
    ~3-10s per pkg (pytest startup dominates). Uses
    ``<repo>/.venv/bin/python -m pytest`` so each pkg's own resolved
    deps decide what imports cleanly.

    Skips silently when the venv is a symlink or missing (those pkgs
    haven't been isolated yet; the dashboard already flags them via
    the `.venv` column).
    """
    repo = Path(state.local_path)
    if not repo.is_dir():
        return
    venv_python = repo / ".venv" / "bin" / "python"
    if state.venv_state != "real" or not venv_python.is_file():
        return
    tests_dir = repo / "tests"
    if not tests_dir.is_dir():
        return
    try:
        out = subprocess.check_output(
            [
                str(venv_python),
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "--no-header",
                str(tests_dir),
            ],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        out = exc.output or ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    # Last non-empty line is usually like "143 tests collected in 0.31s"
    # or "error during collection".
    m = re.search(r"(\d+)\s+tests?\s+collected", out)
    if m:
        state.tests_collected = int(m.group(1))


def _enrich_tests_from_pytest_cache(state: PackageState) -> None:
    """Read the previous pytest run's results from `.pytest_cache/`.

    Pytest persists every collected nodeid (`v/cache/nodeids`) and a
    dict of last-run failures (`v/cache/lastfailed`). We just read
    these files — no subprocess, no pytest invocation, no minutes of
    waiting. Costs <1ms per pkg.

    Effect on the dashboard's Test column: shows real
    `F<failed> (<passed>/<total>)` from the last actual run, refreshed
    automatically whenever the user (or CI) runs pytest locally.
    Falls back silently if `.pytest_cache/` is missing — pkg has
    never been pytest-run, so we let `_enrich_deep` fill the
    file-count fallback.
    """
    import json as _json

    repo = Path(state.local_path)
    if not repo.is_dir():
        return
    cache_dir = repo / ".pytest_cache" / "v" / "cache"
    nodeids_path = cache_dir / "nodeids"
    if not nodeids_path.is_file():
        return
    try:
        nodeids = _json.loads(nodeids_path.read_text())
    except (OSError, _json.JSONDecodeError):
        return
    if not isinstance(nodeids, list):
        return
    total = len(nodeids)

    failed = 0
    lastfailed_path = cache_dir / "lastfailed"
    if lastfailed_path.is_file():
        try:
            lf = _json.loads(lastfailed_path.read_text())
            if isinstance(lf, dict):
                failed = len(lf)
        except (OSError, _json.JSONDecodeError):
            failed = 0

    state.tests_failed = failed
    state.tests_passed = max(0, total - failed)


def _enrich_tests_run(state: PackageState) -> None:
    """Run pytest for real (heavy). Populates passed/failed.

    Off by default. Enable via the dashboard's `--with-test-run` flag
    or the corresponding enricher key. Cost: 30-300s per pkg depending
    on test suite size; some pkgs (scitex-cloud, scitex-scholar) may
    take much longer.
    """
    repo = Path(state.local_path)
    if not repo.is_dir():
        return
    venv_python = repo / ".venv" / "bin" / "python"
    if state.venv_state != "real" or not venv_python.is_file():
        return
    tests_dir = repo / "tests"
    if not tests_dir.is_dir():
        return
    # Run with `--cov` so the same invocation populates coverage.xml,
    # which we parse below. pytest-cov is in every peer's [dev] extras
    # (cross-cutting test dep); if the plugin isn't installed, --cov is
    # silently ignored and we just don't get a coverage number.
    import_name = state.pkg.replace("-", "_")
    cov_target = repo / "src" / import_name
    cov_args = (
        ["--cov", str(cov_target), "--cov-report=xml:.coverage.xml"]
        if cov_target.is_dir()
        else []
    )
    try:
        proc = subprocess.run(
            [
                str(venv_python),
                "-m",
                "pytest",
                "-q",
                "--no-header",
                "--tb=no",
                *cov_args,
                str(tests_dir),
            ],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(repo),
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    # Summary line shape: "5 failed, 138 passed, 2 skipped in 3.45s"
    passed = re.search(r"(\d+)\s+passed", out)
    failed = re.search(r"(\d+)\s+failed", out)
    state.tests_passed = int(passed.group(1)) if passed else 0
    state.tests_failed = int(failed.group(1)) if failed else 0

    # Parse coverage.xml — pytest-cov writes a Cobertura XML with the
    # overall `line-rate` attribute (0.0 - 1.0) on the root element.
    # Also persist the parsed value to the coverage cache so subsequent
    # dashboard refreshes don't have to re-run pytest (which is the
    # whole point of --with-tests=run being opt-in).
    cov_xml = repo / ".coverage.xml"
    if cov_xml.is_file():
        rate = _parse_coverage_xml(cov_xml)
        if rate is not None:
            state.coverage = rate
            from . import _coverage_cache

            fp = _coverage_cache.target_fingerprint(repo)
            if fp is not None:
                _coverage_cache.save(
                    state.pkg,
                    target_fp=fp,
                    coverage=rate,
                    source="tests-run",
                )


def _parse_coverage_xml(cov_xml: Path) -> float | None:
    """Parse Cobertura `line-rate` attribute (0..1) from a coverage.xml.

    Returns None if the file is malformed or missing the attribute.
    """
    import xml.etree.ElementTree as _ET

    try:
        root = _ET.parse(cov_xml).getroot()
        rate = root.get("line-rate")
        if rate is None:
            return None
        return float(rate)
    except (OSError, _ET.ParseError, ValueError):
        return None


def _enrich_coverage(state: "PackageState") -> None:
    """Cheap coverage enricher — local coverage.xml + cache + Codecov.

    Cascade (fastest first):
      1. <repo>/coverage.xml or <repo>/.coverage.xml exists → parse +
         cache the line-rate. Wins on freshness when pytest just ran.
      2. Coverage cache hit (keyed by git HEAD SHA) → use cached value.
         Survives dashboard refreshes without re-running anything.
      3. Codecov public JSON API → fetch latest branch coverage from
         the package's published CI uploads. Cached locally so we hit
         the network at most once per HEAD-SHA.
      4. Still nothing → leave state.coverage at -1 ("N/C").

    Dirty trees are never cached (per `_coverage_cache.target_fingerprint`).
    Cost: steps 1+2 are O(1) file stats; step 3 is one HTTPS GET per
    pkg with a 5 s timeout, parallelised by the dashboard's thread
    pool. The result is cached so subsequent dashboards skip the GET.
    """
    repo = Path(state.local_path)
    if not repo.is_dir():
        return

    # 1. Fresh local coverage.xml wins.
    for fname in ("coverage.xml", ".coverage.xml"):
        cov_xml = repo / fname
        if cov_xml.is_file():
            rate = _parse_coverage_xml(cov_xml)
            if rate is not None:
                state.coverage = rate
                from . import _coverage_cache

                fp = _coverage_cache.target_fingerprint(repo)
                if fp is not None:
                    _coverage_cache.save(
                        state.pkg,
                        target_fp=fp,
                        coverage=rate,
                        source=fname,
                    )
                return

    # 2. Cache lookup by commit SHA.
    from . import _coverage_cache

    fp = _coverage_cache.target_fingerprint(repo)
    cached = _coverage_cache.load(state.pkg, target_fp=fp)
    if cached is not None:
        state.coverage = cached
        return

    # 3. Codecov fallback. The package's CI uploads coverage.xml on
    # every test run; the API serves the latest commit's totals.
    rate = _fetch_codecov_rate(state.pkg, repo)
    if rate is not None:
        state.coverage = rate
        if fp is not None:
            _coverage_cache.save(
                state.pkg,
                target_fp=fp,
                coverage=rate,
                source="codecov",
            )


def _fetch_codecov_rate(pkg: str, repo: Path) -> float | None:
    """Fetch latest branch coverage from Codecov's public API.

    Returns a float in ``[0, 1]`` on success, ``None`` on any failure
    (network, 404, parse error). Public API needs no auth for public
    repos. Service URL pattern:
      https://codecov.io/api/v2/github/<owner>/repos/<pkg>/branches/<branch>
    """
    import json as _json
    import urllib.request as _urlreq

    owner = _git_owner(repo)
    branch = _git_current_branch(repo) or "develop"
    if not owner:
        return None
    url = f"https://codecov.io/api/v2/github/{owner}/repos/{pkg}/branches/{branch}"
    req = _urlreq.Request(url, headers={"Accept": "application/json"})
    try:
        with _urlreq.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                return None
            raw = resp.read().decode("utf-8", errors="replace")
        # Codecov occasionally embeds raw control chars (commit messages)
        # that strict json rejects — sanitize C0 controls before parsing.
        raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", raw)
        data = _json.loads(raw)
    except Exception:
        return None
    # Codecov payload shape: {..., "head_commit": {"totals": {"coverage": <0-100>}}}
    totals = (data.get("head_commit") or {}).get("totals") or {}
    cov = totals.get("coverage")
    if cov is None:
        return None
    try:
        return float(cov) / 100.0
    except (TypeError, ValueError):
        return None


def _git_owner(repo: Path) -> str | None:
    """Parse `origin`'s GitHub owner from .git/config."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    url = (proc.stdout or "").strip()
    # git@github.com:<owner>/<repo>.git or https://github.com/<owner>/<repo>.git
    m = re.search(r"github\.com[:/]([^/]+)/[^/]+?(?:\.git)?$", url)
    return m.group(1) if m else None


def _git_current_branch(repo: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    branch = (proc.stdout or "").strip()
    return branch or None


def _enrich_audit_bulk(
    states: list[PackageState], *, jobs: int = 8, severity: str = "warn"
) -> None:
    """Bulk audit with JSON cache.

    Step 1 — for each pkg, compute its target fingerprint (git HEAD,
    or None when the working tree is dirty) and look up the cache. On
    hit, fill state.audit_errors / audit_warnings from the cache and
    drop the pkg from the to-run list.

    Step 2 — for the remaining (cache-miss) pkgs, run a single
    `scitex-dev ecosystem audit-all <pkgs...>` subprocess and parse the
    summary lines (same shape as before).

    Step 3 — write results back to the cache for every pkg that had a
    clean working tree.

    Net effect: subsequent dashboards return in milliseconds for
    unchanged packages, only paying the audit cost on the ones whose
    HEAD has moved since the last run.
    """
    import os as _os

    from ...audit import _cache as audit_cache

    eligible = [s for s in states if s.exists_locally]
    if not eligible:
        return

    by_pkg = {s.pkg: s for s in eligible}

    # Step 1: cache lookup.
    target_fps: dict[str, str | None] = {}
    to_run: list[str] = []
    for s in eligible:
        tfp = audit_cache.target_fingerprint(Path(s.local_path))
        target_fps[s.pkg] = tfp
        cached = audit_cache.load(s.pkg, "audit-all", target_fp=tfp)
        if cached is not None:
            s.audit_errors = int(cached.get("errors", 0))
            s.audit_warnings = int(cached.get("warnings", 0))
        else:
            to_run.append(s.pkg)

    if not to_run:
        return  # everything served from cache

    # Step 2: run audit-all only for the cache-miss subset.
    try:
        proc = subprocess.run(
            [
                "scitex-dev",
                "ecosystem",
                "audit-all",
                *to_run,
                "--severity",
                severity,
                "-j",
                str(jobs),
            ],
            capture_output=True,
            text=True,
            timeout=900,
            env={
                **_os.environ,
                "SCITEX_DEV_NO_AUDIT_DISCLAIMER": "1",
            },
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return

    counts: dict[str, tuple[int, int]] = {p: (0, 0) for p in to_run}
    for line in proc.stdout.splitlines():
        s = line.lstrip()
        m_e = re.match(r"(?:error|fail)\s+(\S+):\s+(\d+)\s+error", s)
        m_w = re.match(r"warn\s+(\S+):\s+(\d+)\s+(?:warning|violation)", s)
        if m_e:
            pkg, n = m_e.group(1), int(m_e.group(2))
            if pkg in counts:
                e, w = counts[pkg]
                counts[pkg] = (e + n, w)
        elif m_w:
            pkg, n = m_w.group(1), int(m_w.group(2))
            if pkg in counts:
                e, w = counts[pkg]
                counts[pkg] = (e, w + n)

    # Step 3: populate states + write cache for clean-tree pkgs.
    for pkg, (e, w) in counts.items():
        st = by_pkg.get(pkg)
        if st is None:
            continue
        st.audit_errors = e
        st.audit_warnings = w
        tfp = target_fps.get(pkg)
        if tfp is not None:
            audit_cache.save(pkg, "audit-all", target_fp=tfp, errors=e, warnings=w)


def _enrich_ci_bulk(
    states: list[PackageState], *, owner: str = "ywatanabe1989"
) -> None:
    """Single GraphQL call fetching latest check-suite conclusion for
    every repo at once, via aliased fields.

    Replaces 66 sequential `gh run list` invocations (each ~500ms) with
    one ~500ms-total GraphQL round-trip. Same rate-limit cost as one
    REST call (GraphQL counts 1 point per query, not per alias) — so
    we go from 66 rate-limit charges per refresh to 1.
    """
    import json as _json

    eligible = [s for s in states if s.exists_locally]
    if not eligible:
        return

    aliases: list[tuple[str, PackageState]] = []
    parts: list[str] = []
    for i, s in enumerate(eligible):
        alias = f"p{i}"
        aliases.append((alias, s))
        parts.append(
            f'{alias}: repository(owner: "{owner}", name: "{s.pkg}") {{'
            f'  object(expression: "develop") {{'
            f"    ... on Commit {{"
            f"      checkSuites(last: 1) {{ nodes {{ conclusion status }} }}"
            f"    }}"
            f"  }}"
            f"}}"
        )
    query = "query { " + " ".join(parts) + " }"

    try:
        proc = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={query}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return
    if proc.returncode != 0:
        return

    try:
        data = _json.loads(proc.stdout).get("data") or {}
    except _json.JSONDecodeError:
        return

    for alias, st in aliases:
        node = (data.get(alias) or {}).get("object") or {}
        suites = (node.get("checkSuites") or {}).get("nodes") or []
        if not suites:
            continue
        latest = suites[0]
        # GraphQL returns enums in upper-case (SUCCESS, FAILURE, …);
        # the renderer keys on lower-case (success, failure, in_progress).
        conclusion = (latest.get("conclusion") or "").lower()
        status = (latest.get("status") or "").lower()
        if conclusion in {"success", "failure", "cancelled"}:
            st.ci_status = conclusion
        elif status in {"in_progress", "queued", "requested", "pending"}:
            st.ci_status = "in_progress"
        elif conclusion:
            st.ci_status = conclusion


def _enrich_audit(state: PackageState) -> None:
    """Run `audit-all` per package and parse error / warn counts.

    Slow — one subprocess per package (~5–15s each). Only at verbosity≥3.
    Counts come from the canonical `error <pkg>: N error(s)` /
    `warn <pkg>: N warning(s)` summary lines.
    """
    if not state.exists_locally:
        return
    try:
        proc = subprocess.run(
            ["scitex-dev", "ecosystem", "audit-all", state.pkg],
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **__import__("os").environ,
                "SCITEX_DEV_NO_AUDIT_DISCLAIMER": "1",
            },
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return
    errs = warns = 0
    for line in proc.stdout.splitlines():
        s = line.lstrip()
        m_e = re.match(r"(?:error|fail)\s+\S+:\s+(\d+)\s+error", s)
        m_w = re.match(r"warn\s+\S+:\s+(\d+)\s+(?:warning|violation)", s)
        if m_e:
            errs += int(m_e.group(1))
        elif m_w:
            warns += int(m_w.group(1))
    state.audit_errors = errs
    state.audit_warnings = warns


def _enrich_ci(state: PackageState) -> None:
    """Latest GH Actions run of EVERY workflow on develop, deduped by
    workflow name. Populates:

      state.ci_status            — overall ('failure' if any failed,
                                   'in_progress' if any running, else
                                   'success' / first conclusion).
      state.ci_workflows_passed
      state.ci_workflows_failed
      state.ci_workflows_running

    One `gh run list --limit 50` per pkg (still parallel via the pool).
    50 is enough to cover all distinct workflows for a normal scitex
    pkg; we dedupe by `name` keeping the most-recent each.
    """
    if not state.exists_locally:
        return
    try:
        out = subprocess.check_output(
            [
                "gh",
                "run",
                "list",
                "-R",
                f"ywatanabe1989/{state.pkg}",
                "--branch=develop",
                "--limit=50",
                "--json=name,status,conclusion,createdAt",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=15,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return
    import json as _json

    try:
        rows = _json.loads(out)
    except _json.JSONDecodeError:
        return
    if not rows:
        return

    # Dedupe by workflow name, keep most-recent (rows are returned
    # in descending createdAt order, so first wins).
    latest: dict[str, dict] = {}
    for row in rows:
        name = row.get("name") or ""
        if not name or name in latest:
            continue
        latest[name] = row

    passed = failed = running = 0
    for r in latest.values():
        concl = (r.get("conclusion") or "").lower()
        status = (r.get("status") or "").lower()
        if concl == "success":
            passed += 1
        elif concl == "failure":
            failed += 1
        elif status in {"in_progress", "queued", "requested", "pending"}:
            running += 1
        elif concl == "cancelled":
            pass  # ignore cancelled in the counts
        else:
            # Unknown / skipped — don't count.
            pass

    state.ci_workflows_passed = passed
    state.ci_workflows_failed = failed
    state.ci_workflows_running = running

    # Aggregate single status: failure dominates, then in-progress,
    # then success. Preserves the existing ci_status semantics for
    # callers that read it as a single string.
    if failed > 0:
        state.ci_status = "failure"
    elif running > 0:
        state.ci_status = "in_progress"
    elif passed > 0:
        state.ci_status = "success"
    elif latest:
        state.ci_status = (next(iter(latest.values())).get("conclusion") or "").lower()


def _enrich_gh_release(state: PackageState) -> None:
    """Latest GitHub Release tag for the package's repo.

    A tag without an attached release is a release-management gap —
    PyPI got published but no release notes/asset landed. Exposed as a
    separate column from `tag_latest` (git tag).

    Sets ``state.gh_release_lookup_done = True`` on every reachable
    response — including the "no releases exist yet" case, which
    `gh release view` reports as a non-zero exit. That lets the
    renderer distinguish "not yet queried" (dim N/C) from "queried,
    no release attached to the latest tag" (red MISSING — the
    canonical 2026-05-27 footgun where PyPI publishes succeed but the
    awk-based release-notes extractor fails the GH-Release job).
    """
    if not state.exists_locally:
        return
    # `gh release view` returns rc!=0 when no release exists yet; we
    # MUST distinguish that "queried, none" answer from a transport
    # failure. `subprocess.run` (no check) gives us the return code so
    # we can set `gh_release_lookup_done = True` in either case.
    try:
        proc = subprocess.run(
            [
                "gh",
                "release",
                "view",
                "--repo",
                f"ywatanabe1989/{state.pkg}",
                "--json",
                "tagName",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return

    out = proc.stdout or ""
    err = (proc.stderr or "").lower()
    # The "no releases" case: gh prints `release not found` (or `no
    # releases`) on stderr and exits 1. Treat that as a confirmed
    # negative answer rather than a transport failure.
    if proc.returncode != 0:
        if "release not found" in err or "no releases" in err:
            state.gh_release_lookup_done = True
        return

    import json as _json

    try:
        data = _json.loads(out)
    except _json.JSONDecodeError:
        return
    state.gh_release_latest = (data.get("tagName") or "").strip()
    state.gh_release_lookup_done = True


def _compute_drift_local(version: str, tag: str) -> str:
    if not version or not tag:
        return ""
    if version == "(dynamic)":
        return "✓"  # scm-derived; tag IS the version
    tag_v = tag.lstrip("v")
    if tag_v == version:
        return "✓"
    return f"V={version} T={tag}"


def _compute_drift_pypi(tag: str, pypi: str) -> str:
    if not tag or not pypi:
        return ""
    tag_v = tag.lstrip("v")
    if tag_v == pypi:
        return "✓"
    return f"T={tag} P={pypi}"


def _ecosystem_packages() -> dict:
    """Read ECOSYSTEM dict; tolerant of older scitex-dev versions."""
    try:
        from scitex_dev._ecosystem._core import ECOSYSTEM
    except ImportError:
        return {}
    return dict(ECOSYSTEM)


def _gather_one(pkg: str, info: dict, verbosity: int) -> PackageState:
    raw_path = info.get("local_path", "")
    repo = Path(raw_path).expanduser() if raw_path else DEFAULT_PROJ_ROOT / pkg
    state = PackageState(
        pkg=pkg,
        category=info.get("category", ""),
        local_path=str(repo),
        exists_locally=repo.is_dir(),
    )
    if not state.exists_locally:
        return state

    state.version_pyproject, state.version_dynamic = _read_pyproject_version(repo)
    state.tag_latest = _latest_tag(repo)
    state.branch = _branch(repo)
    state.ahead = _ahead_of_origin(repo)
    state.uncommitted = _uncommitted_count(repo)
    state.last_commit_iso = _last_commit_iso(repo)
    state.has_audit_gate = _has_audit_gate(repo)
    state.skip_rules = _read_skip_rules(repo) if state.has_audit_gate else []
    state.drift_local = _compute_drift_local(state.version_pyproject, state.tag_latest)
    state.venv_state = _venv_state(repo)

    # Verbosity 2+: PyPI lookup. Deliberately not run here — networked.
    # The renderer can call _enrich_pypi(state) lazily / async per row.
    return state


def _enrich_pypi(state: PackageState) -> None:
    """Resolve PyPI latest version via the JSON API.

    Sets ``state.pypi_lookup_done = True`` on every reachable response
    (200 → version filled; 404 → confirmed unpublished). Network /
    timeout errors leave ``pypi_lookup_done = False`` so the renderer
    can distinguish "not yet computed" from "confirmed missing".

    Previously this called the experimental ``pip index versions``,
    whose stderr noise + brittle output format silently dropped some
    packages — they rendered as `N/C` even when on PyPI.
    """
    import json as _json
    import urllib.error
    import urllib.request

    url = f"https://pypi.org/pypi/{state.pkg}/json"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            state.pypi_lookup_done = True
        return
    except (urllib.error.URLError, TimeoutError, _json.JSONDecodeError):
        return
    state.pypi_latest = (data.get("info") or {}).get("version", "") or ""
    state.pypi_lookup_done = True
    state.drift_pypi = _compute_drift_pypi(state.tag_latest, state.pypi_latest)


def gather_ecosystem_state(
    verbosity: int = 1,
    *,
    workers: int = 16,
    packages: list[str] | None = None,
    on_update: Callable[[list[PackageState]], None] | None = None,
    enrichers: set[str] | None = None,
) -> list[PackageState]:
    """Collect dashboard rows for every ECOSYSTEM package.

    Verbosity 0–1 are local-only (fast). Verbosity 2+ adds PyPI etc.

    If ``on_update`` is given, it's invoked after the basic gather
    completes AND after every enrichment task finishes, with the
    current `states` list. Callers (e.g. the CLI's Rich-Live
    streaming view) use this to re-render the table progressively
    as cells fill in.
    """
    from concurrent.futures import as_completed

    eco = _ecosystem_packages()
    if packages:
        eco = {k: v for k, v in eco.items() if k in packages}
    items = list(eco.items())

    with ThreadPoolExecutor(max_workers=workers) as pool:
        states = list(pool.map(lambda kv: _gather_one(kv[0], kv[1], verbosity), items))
    if on_update:
        on_update(states)

    # Verbosity controls which COLUMNS are shown, not what gets
    # computed. Callers (CLI / tests) pass the set of `enrichers` they
    # actually need based on visible columns; if omitted we fall back
    # to a verbosity-driven heuristic for backwards-compat.
    if enrichers is None:
        enrichers = set()
        if verbosity >= 2:
            enrichers.add("pypi")
        if verbosity >= 3:
            enrichers.update({"deep", "audit", "ci"})

    per_pkg_enrichers: list[Callable[[PackageState], None]] = []
    if "pypi" in enrichers:
        per_pkg_enrichers.append(_enrich_pypi)
    if "deep" in enrichers:
        per_pkg_enrichers.append(_enrich_deep)
        # Free pytest-results read from `.pytest_cache/` (sub-ms per pkg).
        # Shows real passed/failed from the LAST actual pytest run
        # without spawning anything. Pkgs with no prior run fall back
        # to the `_enrich_deep` file-count.
        per_pkg_enrichers.append(_enrich_tests_from_pytest_cache)
        # Cheap coverage read: local coverage.xml + commit-SHA-keyed
        # cache. Sub-ms per pkg; populates the Coverage column without
        # requiring the heavy `--with-tests run` path.
        per_pkg_enrichers.append(_enrich_coverage)
    if "tests-collect" in enrichers:
        # Cheap: pytest --collect-only -q inside each pkg's own venv.
        # Gives real test counts (parametrize cases included) instead of
        # the basic enricher's test-file count.
        per_pkg_enrichers.append(_enrich_tests_collect)
    if "tests-run" in enrichers:
        # Heavy: actually run pytest inside each pkg's own venv and
        # parse the passed/failed summary. Populates the `F NN (NN/NN)`
        # cell format. Cost: 30-300s per pkg.
        per_pkg_enrichers.append(_enrich_tests_run)
    # Bulk enrichers (one task per fn, processes ALL states at once).
    # Both replace per-pkg subprocess fan-outs with a single batched
    # call: audit-all <pkgs...> as one subprocess; one GraphQL query
    # with aliased fields as one rate-limit charge.
    bulk_enrichers: list[Callable[[list[PackageState]], None]] = []
    if "audit" in enrichers:
        bulk_enrichers.append(_enrich_audit_bulk)
    if "ci" in enrichers:
        # CI stays per-pkg: GraphQL `checkSuites` on develop HEAD
        # misses recent commits where CI hasn't run yet. `gh run list`
        # sorts by run time and finds the most recent actually-ran
        # workflow. Parallel via the shared pool keeps wall-clock
        # bounded; cost is N rate-limit charges instead of 1.
        per_pkg_enrichers.append(_enrich_ci)
    if "gh-release" in enrichers:
        # `gh release view` per-pkg. Latest published release tag —
        # separate from local git tag.
        per_pkg_enrichers.append(_enrich_gh_release)

    has_work = per_pkg_enrichers or bulk_enrichers
    if has_work:
        tasks: list = []
        for fn in per_pkg_enrichers:
            for s in states:
                tasks.append((fn, s, False))
        for fn in bulk_enrichers:
            tasks.append((fn, states, True))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fn, arg) for fn, arg, _is_bulk in tasks]
            if on_update is None:
                for _ in as_completed(futures):
                    pass
            else:
                for _ in as_completed(futures):
                    on_update(states)

    # Sort: most recently edited first (top → bottom = newest → oldest).
    # Empty `last_commit_iso` sinks to the bottom.
    states.sort(key=lambda s: s.last_commit_iso or "", reverse=True)
    return states
