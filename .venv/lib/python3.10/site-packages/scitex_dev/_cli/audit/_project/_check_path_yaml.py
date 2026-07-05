"""PS-PATH-001 / PS-PATH-002 — `config/PATH.yaml` shape checks.

Implements the two tight rules documented in
``_skills/scientific/02_research-project_03_project-structure-config-and-data.md``
(see also the operator directive 2026-06-01 and PR #97):

  PS-PATH-001 — outer ``PATH:`` wrapper.
    The filename already gives the namespace; ``@stx.session`` exposes
    top-level keys directly under ``CONFIG.PATH``. Wrapping the
    contents in a top-level ``PATH:`` key produces
    ``CONFIG.PATH.PATH.<KEY>`` and 100 % of ``eval(CONFIG.PATH.<KEY>)``
    access sites crash with ``AttributeError``.

  PS-PATH-002 — bare-string leaf value.
    Every leaf scalar in ``PATH.yaml`` is read via
    ``eval(CONFIG.PATH.<KEY>)``. A bare ``"./data/foo"`` parses to the
    Python expression ``./data/foo`` and SyntaxErrors; the ``f"..."``
    prefix makes it a valid f-string literal that evaluates to the
    path with any ``{var}`` interpolated against the local frame.

Both rules are gated by file presence — if no ``config/PATH.yaml``
exists in the repo, neither rule fires.

Scope: every research / package / hybrid project (the rules are
artifact-gated, so adding them everywhere is safe — they only speak
when the file is there).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable


def _git_ignored_subset(repo: Path, candidates: list[Path]) -> set[Path]:
    """Return the subset of ``candidates`` that git says are IGNORED.

    A gitignored file is by definition not part of the project being
    audited — but persistent CI checkouts (self-hosted runners) accrue
    synced/scaffolded debris that IS on disk yet ignored, e.g. the
    dotfiles-synced ``docs/to_claude/examples/.../config/PATH.yaml`` that
    failed scitex-scholar's v1.4.3 PyPI publish on PS-PATH-001
    (2026-07-03). Filtering by ``git check-ignore`` scopes the audit to
    what the repo actually ships, the same class of runner-state-leak fix
    as the SIF ``--cleanenv`` item.

    One batched ``git check-ignore --stdin -z`` call (NUL-safe both
    directions). Fail-open BY DESIGN: outside a git repo, or when git is
    missing/errors, returns the empty set so every candidate is still
    audited — degrading to the pre-fix behaviour rather than silently
    skipping real violations.
    """
    if not candidates:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "--stdin", "-z"],
            input="\0".join(str(p) for p in candidates) + "\0",
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    # Exit 0 = at least one ignored; 1 = none ignored; anything else
    # (128 = not a git repo, ...) means "don't know" -> fail-open.
    if proc.returncode not in (0, 1):
        return set()
    return {Path(chunk) for chunk in proc.stdout.split("\0") if chunk}


def _is_in_worktree_checkout(parts: tuple[str, ...]) -> bool:
    """True iff ``parts`` traverses an operator / subagent git-worktree
    checkout — paths the audit walker must NEVER treat as canonical
    source.

    Two segments are guarded:

      * ``.worktrees/`` — the operator's own ``git worktree add`` sibling
        checkouts. They live inside the repo but carry old branches'
        files (e.g. PATH.yaml pre-PR-97 fix), so walking into them
        surfaces stale violations on develop's audit even though the
        canonical source is already correct.
      * ``.claude/worktrees/`` — subagent-spawned worktrees from
        ``Agent(isolation="worktree")``. Same problem shape; same fix.
        Note this segment is matched on the *pair* ``(".claude",
        "worktrees")`` so a hypothetical ``.claude/skills/`` etc. isn't
        accidentally skipped.

    Lead-approved 2026-06-07 after PR #130 (worktree-gc) wedged on
    PS-PATH-001 fires under both segments. Mirrors the same blind-spot
    fix Task #42 made for the sac walkers.
    """
    for i, part in enumerate(parts):
        if part == ".worktrees":
            return True
        if part == ".claude" and i + 1 < len(parts) and parts[i + 1] == "worktrees":
            return True
    return False


def _path_yaml_files(repo: Path) -> Iterable[Path]:
    """Yield every ``config/PATH.yaml`` (and ``configs/PATH.yaml``) under
    ``repo``.

    We walk shallowly: the canonical location is ``<repo>/config/PATH.yaml``
    but research projects with per-cohort scaffolding sometimes ship
    additional copies under ``scripts/cohorts/.../<capsule>/config/PATH.yaml``.
    The shape rules apply uniformly — every file must be valid on its own.
    """
    candidates: list[Path] = []
    seen: set[Path] = set()
    for pattern in ("config/PATH.yaml", "configs/PATH.yaml"):
        for p in repo.rglob(pattern):
            if "__pycache__" in p.parts:
                continue
            # Skip vendored / backup / GITIGNORED trees so the rule
            # doesn't flag user-archived snapshots.
            if any(
                part in {".git", ".venv", "build", "dist", "GITIGNORED", "node_modules"}
                or part.endswith(".bak")
                or part.startswith(".bloat-bak-")
                or part.endswith("-bak")
                or ".bloat-bak-" in part
                for part in p.parts
            ):
                continue
            # Skip git-worktree checkouts (operator's .worktrees/ and
            # subagent .claude/worktrees/). They carry transient branch
            # state — never canonical source. See _is_in_worktree_checkout.
            if _is_in_worktree_checkout(p.parts):
                continue
            if p in seen:
                continue
            seen.add(p)
            candidates.append(p)
    # Finally, drop anything git itself IGNORES — persistent-runner
    # debris (synced docs/to_claude examples etc.) is on disk but not
    # part of the project; auditing it wedges releases. Fail-open
    # outside git. See _git_ignored_subset.
    ignored = _git_ignored_subset(repo, candidates)
    for p in candidates:
        if p not in ignored:
            yield p


# A "leaf scalar" line in the YAML is `KEY: VALUE` where VALUE is a
# non-empty token. Dict-header lines look like `KEY:` (no value after).
# We use a line-based scan rather than yaml.safe_load for PS-PATH-002
# because PyYAML strips the surrounding quotes of `f"..."` literals
# unhelpfully (it returns the string `f"./data/foo"` as a value,
# which is correct — but PyYAML's anchor/alias handling and quoted-empty
# edge cases make line scanning the more transparent option).
_LEAF_RE = re.compile(
    r"""^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<value>.+?)\s*$"""
)


def _is_pure_comment_or_blank(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _strip_inline_comment(value: str) -> str:
    """Strip ``# comment`` from a YAML value if it's not inside quotes.

    Cheap heuristic: walk char-by-char, track quote state.
    """
    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            out.append(ch)
            out.append(value[i + 1])
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _has_f_prefix(value: str) -> bool:
    """Return True iff ``value`` starts with an f-string prefix.

    Accepts ``f"..."``, ``f'...'``, ``F"..."``, ``F'...'``. Rejects
    bare quoted strings, bare tokens, and YAML constructs like
    ``[a, b]`` (treated as bare — flagged).
    """
    v = value.lstrip()
    if not v:
        return False
    if v[0] in ("f", "F"):
        rest = v[1:]
        if rest.startswith('"') or rest.startswith("'"):
            return True
    return False


def check_ps_path_001_outer_wrapper(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """PS-PATH-001 — top-level YAML is a dict whose first/only key is
    ``PATH:`` and that key's value is itself a dict.

    We don't require PyYAML to fire: a quick structural scan picks up
    the canonical buggy shape (an unindented ``PATH:`` header followed
    by indented children). If PyYAML IS available we use it to confirm
    the parsed top-level shape, suppressing false positives where the
    file is malformed YAML for other reasons.
    """
    for yaml_path in _path_yaml_files(repo):
        try:
            text = yaml_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        flagged_line: int | None = None
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(text)
        except ImportError:
            data = None
        except Exception:
            data = None

        if isinstance(data, dict):
            keys = list(data.keys())
            if (
                len(keys) == 1
                and keys[0] == "PATH"
                and isinstance(data["PATH"], dict)
            ):
                # Find the literal `PATH:` line for a precise location.
                for idx, line in enumerate(text.splitlines(), start=1):
                    if _is_pure_comment_or_blank(line):
                        continue
                    stripped = line.lstrip()
                    if stripped.startswith("PATH:") and line == line.lstrip():
                        flagged_line = idx
                        break
                if flagged_line is None:
                    flagged_line = 1
        else:
            # PyYAML unavailable OR parse failed. Fall back to line scan.
            for idx, line in enumerate(text.splitlines(), start=1):
                if _is_pure_comment_or_blank(line):
                    continue
                # Top-level (unindented) `PATH:` line with empty value
                # (or only an inline comment) is the canonical wrapper.
                m = re.match(r"^PATH\s*:\s*(#.*)?$", line)
                if m:
                    # Look ahead for at least one indented child line —
                    # that confirms it's an outer dict, not a stray key.
                    rest = text.splitlines()[idx:]
                    for nxt in rest:
                        if _is_pure_comment_or_blank(nxt):
                            continue
                        if nxt.startswith((" ", "\t")):
                            flagged_line = idx
                        break
                break

        if flagged_line is None:
            continue

        out.append(
            violation_cls(
                "PS-PATH-001",
                f"{yaml_path}:{flagged_line}",
                (
                    "config/PATH.yaml wraps its contents in an outer "
                    "`PATH:` key. The filename already gives the "
                    "namespace; @stx.session exposes top-level keys "
                    "directly under CONFIG.PATH.<KEY>. With the "
                    "wrapper, every `eval(CONFIG.PATH.<KEY>)` access "
                    "site crashes with AttributeError because the "
                    "real path is at `CONFIG.PATH.PATH.<KEY>`. "
                    "Fix-hint: remove the outer `PATH:` wrapper line "
                    "and dedent its children one level. See "
                    "_skills/scientific/"
                    "02_research-project_03_project-structure-config-"
                    "and-data.md §`PATH.yaml` and PR #97."
                ),
            )
        )


def check_ps_path_002_bare_string_leaf(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """PS-PATH-002 — every leaf scalar value must start with ``f"`` / ``f'``.

    Line-based scan: for each ``KEY: VALUE`` where VALUE is non-empty
    (a leaf), require an f-string prefix. Dict headers (``KEY:`` with
    no value) are skipped — they're not leaves.

    False-negative trade-offs (documented per spec): multi-line
    folded/block scalars (``KEY: |``, ``KEY: >``) are not flagged —
    they're not directly evalable as f-strings and aren't the buggy
    shape this rule targets.
    """
    for yaml_path in _path_yaml_files(repo):
        try:
            text = yaml_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # If the file has the outer-PATH wrapper, PS-PATH-001 will fire
        # — but we still want PS-PATH-002 to fire too, so the operator
        # sees BOTH problems in one audit pass. Don't short-circuit.

        for idx, line in enumerate(text.splitlines(), start=1):
            if _is_pure_comment_or_blank(line):
                continue
            m = _LEAF_RE.match(line)
            if not m:
                continue
            value = _strip_inline_comment(m.group("value"))
            if not value:
                continue  # dict header `KEY:` with trailing whitespace
            # YAML list / inline-flow / block scalar indicators are not
            # f-strings and not the target — skip.
            if value.startswith(("[", "{", "|", ">", "*", "&")):
                continue
            # The buggy shape: leaf scalar (bare or quoted) without f.
            if _has_f_prefix(value):
                continue

            key = m.group("key")
            out.append(
                violation_cls(
                    "PS-PATH-002",
                    f"{yaml_path}:{idx}",
                    (
                        f"config/PATH.yaml leaf `{key}` value "
                        f"`{value[:60]}` is not an f-string literal. "
                        "Every value must start with `f\"...\"` (or "
                        "`f'...'`); scripts always do "
                        "`eval(CONFIG.PATH.<KEY>)` and a bare "
                        "`\"./data/foo\"` is parsed as the Python "
                        "expression `./data/foo` (SyntaxError). "
                        "Fix-hint: prefix the value with `f`, e.g. "
                        f"`{key}: f\"./your/path\"`. See "
                        "_skills/scientific/"
                        "02_research-project_03_project-structure-"
                        "config-and-data.md §`PATH.yaml`."
                    ),
                )
            )
