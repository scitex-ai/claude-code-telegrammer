"""Rich-based table renderer for the ecosystem dashboard.

Verbosity → column visibility:

  0     PKG, AUDIT, DRIFT, CI                       (4 cols, at-a-glance)
  1     + W, SKIP, VER, TAG                         (8 cols, default)
  2     + PYPI, DRIFT_PYPI, BRANCH, AHEAD, LAST     (13 cols, deep triage)
  3     + every remaining field                     (export-equivalent)

`render_table(states, verbosity)` returns a `rich.table.Table` ready
to print or pass to `rich.live.Live`. Cell coloring is severity-based:
red on errors / drift, yellow on warnings / skip > 0, green on ✓.
"""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from ._state import PackageState

_TIERS: list[list[str]] = [
    # Logical groups: identity → audit (E,W,Bypassed) → venv → version
    # (pyproject,tag,PyPI) → test (pytest,coverage,CI) → git → code.
    # Version mismatches are shown via cell-colour, not separate
    # drift columns — any cell whose value differs from pyproject's
    # is rendered red.
    # 0 — at-a-glance
    ["pkg", "audit", "warn", "venv", "ver", "tag", "ci"],
    # 1 — default
    [
        "pkg",
        "audit",
        "warn",
        "skip",
        "venv",
        "branch",
        "uncommitted",
        "ahead",
        "ver",
        "tag",
        "release",
        "pypi",
        "tests",
        "cov",
        "ci",
    ],
    # 2 — deep triage
    [
        "pkg",
        "audit",
        "warn",
        "skip",
        "venv",
        "branch",
        "uncommitted",
        "ahead",
        "last",
        "ver",
        "tag",
        "release",
        "pypi",
        "tests",
        "cov",
        "ci",
    ],
    # 3 — everything
    [
        "pkg",
        "category",
        "audit",
        "warn",
        "skip",
        "ver",
        "tag",
        "release",
        "pypi",
        "tests",
        "cov",
        "ci",
        "rtd",
        "branch",
        "ahead",
        "last",
        "skills",
        "mcp_tools",
        "py_apis",
        "loc",
    ],
]


# Each column has (a) a group label (top line, shared across the
# group) and (b) a column name (bottom line). The renderer prints the
# group label only on the FIRST column of each group; subsequent
# columns in the same group leave the top line blank, producing a
# visual "Audit | | |" / "Version | | | |" effect under Rich's box
# drawing.
_COL_GROUP = {
    "pkg": "",
    "category": "",
    "audit": "Audit",
    "warn": "Audit",
    "skip": "Audit",
    "venv": "Env",
    "ver": "Version",
    "tag": "Version",
    "release": "Version",
    "pypi": "Version",
    "drift_local": "Version",
    "drift_pypi": "Version",
    "tests": "Test",
    "cov": "Test",
    "ci": "Test",
    "rtd": "Test",
    "branch": "Git",
    "uncommitted": "Git",
    "ahead": "Git",
    "last": "Git",
    "skills": "Code",
    "mcp_tools": "Code",
    "py_apis": "Code",
    "loc": "Code",
}

# Which enricher (if any) populates each column. The CLI uses this
# to determine what to compute based on visible cols at the current
# verbosity — verbosity controls VISIBILITY only; visible columns are
# always computed.
_COL_TO_ENRICHER: dict[str, str] = {
    "audit": "audit",
    "warn": "audit",
    "skip": "audit",
    "pypi": "pypi",
    "release": "gh-release",
    "ci": "ci",
    "rtd": "deep",
    "skills": "deep",
    "mcp_tools": "deep",
    "py_apis": "deep",
    "tests": "deep",
    "cov": "deep",
    "loc": "deep",
}


def enrichers_for_cols(cols: list[str]) -> set[str]:
    """Map a list of visible column ids to the enrichers needed."""
    return {_COL_TO_ENRICHER[c] for c in cols if c in _COL_TO_ENRICHER}


def cols_for_verbosity(verbosity: int) -> list[str]:
    """Public view of the verbosity → columns mapping."""
    return _TIERS[max(0, min(verbosity, len(_TIERS) - 1))]


_COL_NAMES = {
    "pkg": "Package",
    "category": "Category",
    "audit": "Error",
    "warn": "Warning",
    "skip": "Bypassed",
    "venv": ".venv",
    "ver": "pyproject.toml",
    "tag": "git tag",
    "release": "GH Release",
    "pypi": "PyPI",
    "drift_local": "Drift",
    "drift_pypi": "PyPI Drift",
    "tests": "pytest",
    "cov": "Coverage",
    "ci": "CI",
    "rtd": "RTD",
    "branch": "branch",
    "uncommitted": "dirty",
    "ahead": "↑ unpushed",
    "last": "last commit",
    "skills": "skills",
    "mcp_tools": "MCP tools",
    "py_apis": "Python APIs",
    "loc": "LOC",
}


def _column_header(cols: list[str], idx: int) -> str:
    """Two-line header for column at index `idx` in `cols`.

    Top line carries the group label only when this column is the
    leading column of a new group (i.e. the previous column belongs
    to a different group, or this is column 0). Subsequent same-group
    columns leave the top line blank so the group reads visually.
    """
    col = cols[idx]
    group = _COL_GROUP.get(col, "")
    prev_group = _COL_GROUP.get(cols[idx - 1], "") if idx > 0 else None
    top = group if (group and group != prev_group) else ""
    return f"{top}\n{_COL_NAMES.get(col, col)}"


def _legend_text() -> Text:
    """Compact glyph legend. Column headers are self-descriptive
    after the two-line group rename, so we no longer need a per-
    column glossary — just remind users what the value glyphs mean.
    """
    parts: list[Text] = []
    parts.append(Text("Glyphs: ", style="bold dim"))
    parts.append(Text("N/C", style="dim"))
    parts.append(Text(" not yet computed (live, fills in)  ·  ", style="dim"))
    parts.append(Text("—", style="dim"))
    parts.append(Text(" PyPI: confirmed unpublished  ·  ", style="dim"))
    parts.append(Text("0", style="green"))
    parts.append(Text(" clean  ·  ", style="dim"))
    parts.append(Text("N", style="yellow"))
    parts.append(Text(" warnings  ·  ", style="dim"))
    parts.append(Text("N", style="red"))
    parts.append(Text(" errors  ·  ", style="dim"))
    parts.append(Text("✓", style="green"))
    parts.append(Text(" synced / pass  ·  ", style="dim"))
    parts.append(Text("✗", style="red"))
    parts.append(Text(" failed  ·  ", style="dim"))
    parts.append(Text("…", style="yellow"))
    parts.append(Text(" in progress", style="dim"))
    out = Text("")
    for p in parts:
        out.append_text(p)
    return out


def _color_count(n: int, *, error: bool = False) -> Text:
    if n < 0:
        return Text("N/C", style="dim")
    if n == 0:
        return Text("0", style="green")
    return Text(str(n), style="red" if error else "yellow")


def _color_skip(skip_rules: list[str]) -> Text:
    # `audit.skip` is an intentional opt-out, not an error. Yellow flags
    # "review periodically" without screaming. Red bold is reserved for
    # actual failures (E counts, CI ✗).
    n = len(skip_rules)
    if n == 0:
        return Text("0", style="green")
    return Text(str(n), style="yellow")


def _normalise_version(s: str) -> str:
    """Trim leading `v` and trailing `-alpha`/`-beta`/etc. for equality
    checks. `0.2.7` ≡ `v0.2.7`."""
    if not s:
        return ""
    s = s.lstrip("v")
    return s


def _color_version_cell(state: "PackageState", col: str) -> Text:
    """Render a version cell coloured red iff it disagrees with the
    canonical (pyproject.toml) version.

    `pyproject.toml` is the source of truth. `git tag` and `PyPI` are
    expected to match it; any divergence is shown by reddening the
    offending cell. Empty/unknown values render dim.
    """
    val_raw = {
        "ver": state.version_pyproject,
        "tag": state.tag_latest,
        "release": state.gh_release_latest,
        "pypi": state.pypi_latest,
    }.get(col, "")

    if not val_raw:
        # `-` for missing tag/pyproject; networked columns split:
        #   pypi  — N/C while lookup is pending, `—` once a 404
        #           confirms the package isn't published, `?` on
        #           network error so the user knows to retry.
        #   release — N/C while pending; once lookup_done flips, a
        #           local tag without a matching GH Release is the
        #           2026-05-27 footgun (PyPI ok but GH Release awk
        #           failed). Show `MISSING` red so it sticks out next
        #           to a populated TAG cell.
        if col == "pypi":
            if getattr(state, "pypi_lookup_done", False):
                placeholder = "—"  # confirmed not on PyPI
            else:
                placeholder = "N/C"  # not yet computed
        elif col == "release":
            if getattr(state, "gh_release_lookup_done", False):
                if state.tag_latest:
                    # We have a local tag but no GH Release — release
                    # pipeline gap. Red is intentional: this is the
                    # same severity as a PyPI-vs-pyproject divergence.
                    return Text("MISSING", style="red bold")
                placeholder = "—"  # confirmed no releases (also no tag)
            else:
                placeholder = "N/C"  # not yet computed
        else:
            placeholder = "-"
        return Text(placeholder, style="dim")

    canonical = _normalise_version(state.version_pyproject)
    own = _normalise_version(val_raw)

    if col == "ver":
        # The canonical column itself — always rendered neutral
        # (cyan when dynamic, plain otherwise). Mismatch is shown by
        # the OTHER columns going red.
        return Text(val_raw, style="cyan" if state.version_dynamic else "")

    if canonical and own and canonical != own:
        return Text(val_raw, style="red")
    return Text(val_raw, style="green" if canonical and own else "")


def _format_pass_fail_cell(
    *,
    passed: int,
    failed: int,
    fallback_collected: int = -1,
    fallback_count: int = -1,
    width: int = 4,
) -> Text:
    """Shared renderer for `F<failed> (<passed>/<total>)` cells.

    Used by both the Test column (pytest pass/fail) and the CI column
    (workflows pass/fail). Numbers are right-padded to `width` digits
    so columns visually align across rows — `F  3 (1890/1893)` lines
    up under `F 32 (1608/1640)`.

    Priority order (Test column): real run results > collected-only
    count > test-file count > N/C. CI column passes only `passed` /
    `failed`.
    """
    if passed >= 0 or failed >= 0:
        f = max(0, failed)
        p = max(0, passed)
        total = p + f
        t = Text()
        if f > 0:
            # Real failures — red `F<n>` prefix is the alarm signal.
            t.append(f"F{f:>{width}d} ", style="red bold")
        else:
            # Clean run — drop the `F` so a glance distinguishes
            # passing rows from failing ones. The space pad keeps the
            # `(<p>/<t>)` column visually aligned with `F<n>` rows.
            t.append(f" {f:>{width}d} ", style="green")
        t.append(f"({p:>{width}d}/{total:>{width}d})")
        return t
    if fallback_collected >= 0:
        return Text(str(fallback_collected), style="dim")
    if fallback_count >= 0:
        return Text(f"{fallback_count}f", style="dim italic")
    return Text("N/C", style="dim")


def _color_ci(s: str) -> Text:
    return {
        "success": Text("✓", style="green"),
        "failure": Text("✗", style="red bold"),
        "in_progress": Text("…", style="yellow"),
        "cancelled": Text("⊘", style="dim"),
        "": Text("N/C", style="dim"),
    }.get(s, Text(s, style="dim"))


def _cell(state: PackageState, col: str) -> Text | str:
    if col == "pkg":
        if not state.exists_locally:
            return Text(state.pkg, style="dim")
        return Text(state.pkg, style="bold")
    if col == "category":
        return state.category or "-"
    if col == "audit":
        return _color_count(state.audit_errors, error=True)
    if col == "warn":
        return _color_count(state.audit_warnings)
    if col == "skip":
        return _color_skip(state.skip_rules)
    if col == "venv":
        # Per-package isolation status (02_package/10_dev-venv-isolation.md).
        # real → green ✓ ; symlink (shared) → red ↗ ; missing → dim ·
        s = state.venv_state
        return {
            "real": Text("real", style="green"),
            "symlink": Text("symlink", style="red"),
            "missing": Text("·", style="dim"),
        }.get(s, Text(s or "N/C", style="dim"))
    if col in ("ver", "tag", "release", "pypi"):
        return _color_version_cell(state, col)
    if col == "branch":
        b = state.branch or "-"
        return Text(b, style="" if b in ("develop", "main") else "yellow")
    if col == "uncommitted":
        # 0 dim (clean), N yellow (working-tree dirty; needs commit).
        if state.uncommitted < 0:
            return Text("N/C", style="dim")
        if state.uncommitted == 0:
            return Text("0", style="dim")
        return Text(str(state.uncommitted), style="yellow")
    if col == "ahead":
        # 0 dim (synced), N yellow (commits not pushed to origin).
        if state.ahead == 0:
            return Text("0", style="dim")
        return Text(str(state.ahead), style="yellow")
    if col == "last":
        return state.last_commit_iso[:10] if state.last_commit_iso else "-"
    if col == "ci":
        # Prefer the rich per-workflow counts; fall back to the
        # single-status glyph when the new fields aren't populated
        # (older PackageState payloads, JSON cache rehydrates).
        if state.ci_workflows_passed >= 0 or state.ci_workflows_failed >= 0:
            return _format_pass_fail_cell(
                passed=state.ci_workflows_passed,
                failed=state.ci_workflows_failed,
            )
        return _color_ci(state.ci_status)
    if col == "rtd":
        return state.rtd_status or Text("N/C", style="dim")
    if col == "skills":
        return _color_count(state.skills_count)
    if col == "mcp_tools":
        return _color_count(state.mcp_tools)
    if col == "py_apis":
        return _color_count(state.py_apis)
    if col == "tests":
        return _format_pass_fail_cell(
            passed=state.tests_passed,
            failed=state.tests_failed,
            fallback_collected=state.tests_collected,
            fallback_count=state.tests_count,
        )
    if col == "cov":
        return (
            f"{state.coverage:.0%}" if state.coverage >= 0 else Text("N/C", style="dim")
        )
    if col == "loc":
        return _color_count(state.loc)
    return "?"


def render_table(
    states: list[PackageState],
    verbosity: int = 1,
    *,
    host: str | None = None,
) -> Table:
    """Return a Rich Table for the requested verbosity tier.

    Sorts most-recently-edited first (top → bottom = newest → oldest).
    The last-edited timestamp considers uncommitted working-tree
    changes, not just the last commit — see `_last_commit_iso` in
    `_state.py`. Ties broken by package name.

    ``host`` (optional) is shown in the table title so it's obvious
    which machine's checkouts the data describes — distinguishes
    `dashboard list` (local) from `dashboard list --host spartan`
    (remote). Defaults to the current short hostname when omitted.
    """
    cols = _TIERS[max(0, min(verbosity, len(_TIERS) - 1))]
    if host is None:
        import socket

        try:
            host = socket.gethostname().split(".", 1)[0] or "local"
        except OSError:
            host = "local"

    # Sort newest → oldest, with packages missing a timestamp at the
    # bottom. Two-pass keeps the logic straightforward without trying
    # to negate ISO strings inside a tuple-key.
    dated = sorted(
        [s for s in states if s.last_commit_iso],
        key=lambda s: (s.last_commit_iso, s.pkg),
        reverse=True,
    )
    undated = sorted(
        [s for s in states if not s.last_commit_iso],
        key=lambda s: s.pkg,
    )
    ordered_states = dated + undated

    table = Table(
        title=f"scitex ecosystem  ·  @{host}  ·  v={verbosity}  ·  {len(states)} packages",
        title_style="bold cyan",
        header_style="bold",
        caption=_legend_text(),
        caption_justify="left",
        caption_style="",
        # Expand to fill the full terminal width. Without this Rich
        # uses the table's natural minimum width and truncates headers
        # (`Audit Error` → `A…`) even when there's plenty of room.
        expand=True,
    )
    # `no_wrap=True` keeps cells on one line; `overflow="ellipsis"`
    # collapses long values to `…` only when truly necessary (e.g. on
    # a narrow split-pane). The Package column gets a generous min so
    # `scitex-agent-container` stays unabridged on any sane terminal.
    for i, col in enumerate(cols):
        kwargs: dict = {"no_wrap": True, "overflow": "ellipsis"}
        if col == "pkg":
            kwargs["min_width"] = 22
        table.add_column(_column_header(cols, i), **kwargs)
    for state in ordered_states:
        table.add_row(*[_cell(state, c) for c in cols])
    return table
