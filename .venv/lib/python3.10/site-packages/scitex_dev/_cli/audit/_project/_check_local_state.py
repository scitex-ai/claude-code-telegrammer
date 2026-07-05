"""PS-145 / PS-146 / PS-147 — local-state convention checks.

Implements the rules from
`_skills/general/01_ecosystem/06_local-state-directories.md`:

  PS-145 — cross-package state read (§9.5 plugin-port pattern).
           Source must not contain `~/.scitex/<other-pkg>/` literals
           or `SCITEX_<OTHER>_*` env-var reads. If X needs to extend
           via Y's tree, expose a plugin-port env var slot.

  PS-146 — pip-install side-effect (§3.5 lazy mkdir, never via hooks).
           pyproject.toml must not declare a setuptools `cmdclass`
           or hatch build hook that creates `~/.scitex/<pkg>/` at
           install time. Wheels stay inert; PathManager mkdir's
           lazily on first write.

  PS-147 — eval-form shell completion (§11 / required-introspection).
           Source must not write `eval "$(_<NAME>_COMPLETE=...)"`
           into the user's rc file. The cache-file pattern is:
           generate completion to `~/.scitex/<pkg-short>/runtime/
           completion/<binary>` once, source it from rc.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


# Known short-names for every scitex-* package and external partner.
# Mirrors the §2 prefix-stripping rule in
# 01_ecosystem/06_local-state-directories.md. Kept in sync manually with
# `_ecosystem._core.ECOSYSTEM`. Adding a new package here is a one-liner.
_KNOWN_SHORTS = frozenset(
    {
        "agent-container",
        "app",
        "audio",
        "audit",
        "benchmark",
        "bridge",
        "browser",
        "capture",
        "clew",
        "cloud",
        "compat",
        "config",
        "container",
        "context",
        "crossref-local",
        "cv",
        "dataset",
        "datetime",
        "db",
        "decorators",
        "dev",
        "dict",
        "dsp",
        "etc",
        "events",
        "figrecipe",
        "gen",
        "genai",
        "gists",
        "git",
        "hpc",
        "introspect",
        "io",
        "linalg",
        "linter",
        "logging",
        "ml",
        "msword",
        "newb",
        "nn",
        "notebook",
        "notification",
        "openalex-local",
        "orochi",
        "os",
        "parallel",
        "path",
        "pd",
        "plt",
        "repro",
        "resource",
        "scholar",
        "security",
        "seizure-metrics",
        "session",
        "sh",
        "skills",
        "socialia",
        "ssh",
        "stats",
        "str",
        "template",
        "tex",
        "types",
        "ui",
        "web",
        "writer",
    }
)


def _is_in_docstring_or_comment(text: str, offset: int) -> bool:
    """Cheap heuristic: True if `offset` lies inside a triple-quoted block
    or on a `#`-comment line.

    Counts unescaped ``\"\"\"`` / ``'''`` occurrences before `offset` —
    odd ⇒ inside. Doesn't model nested literal forms (good enough for
    the audit, which prefers false negatives over false positives).
    """
    head = text[:offset]
    if head.count('"""') % 2 == 1:
        return True
    if head.count("'''") % 2 == 1:
        return True
    line_start = head.rfind("\n") + 1
    line_prefix = text[line_start:offset]
    if "#" in line_prefix:
        # Allow `#` inside string literals on the same line; cheap
        # escape: only treat as comment when prefix has no `"` or `'`.
        if '"' not in line_prefix and "'" not in line_prefix:
            return True
    return False


def _self_shorts(distribution: str) -> set[str]:
    """Short-names that this package is allowed to read from.

    Always includes the canonical `<distribution>` minus `scitex-`,
    plus the bare `distribution` (so non-prefixed packages map cleanly).
    """
    bare = distribution.replace("scitex-", "")
    return {distribution, bare}


def _src_files(repo: Path) -> list[Path]:
    """Yield .py files under src/ (best-effort, gitignore-naive)."""
    src = repo / "src"
    if not src.is_dir():
        return []
    return [p for p in src.rglob("*.py") if "__pycache__" not in p.parts]


# ---------------------------------------------------------------------------
# PS-145 — cross-package state read
# ---------------------------------------------------------------------------

# Match `.scitex/<short>` literals — quoted path fragments. Tolerant of
# ".scitex" or "scitex" preceded by Path.home()/expanduser style code.
_RE_LOCAL_STATE = re.compile(
    r"""\.scitex[\\/]+([a-z][a-z0-9_-]*)""",
    re.IGNORECASE,
)
_RE_ENV_VAR = re.compile(
    r"""\bSCITEX_([A-Z][A-Z0-9_]*)_[A-Z0-9_]+\b""",
)
# Ambient env-var suffixes that don't denote per-package state.
_AMBIENT_ENV_SUFFIXES = frozenset({"DIR"})  # SCITEX_DIR is the relocator (§6)


def _short_from_env_token(token: str) -> str:
    """`AGENT_CONTAINER` → `agent-container`, `OROCHI` → `orochi`."""
    return token.lower().replace("_", "-")


def check_ps145_cross_package_read(
    repo: Path,
    distribution: str,
    violation_cls: type,
    out: list,
) -> None:
    self_shorts = _self_shorts(distribution)
    # Also map the env-var form: scitex-agent-container → AGENT_CONTAINER.
    self_env_tokens = {
        s.replace("scitex-", "").upper().replace("-", "_") for s in self_shorts
    }
    findings: dict[Path, list[str]] = {}
    for py in _src_files(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits: list[str] = []
        for m in _RE_LOCAL_STATE.finditer(text):
            short = m.group(1).lower()
            if short in self_shorts:
                continue
            if short not in _KNOWN_SHORTS:
                continue
            if _is_in_docstring_or_comment(text, m.start()):
                continue
            line_no = text[: m.start()].count("\n") + 1
            hits.append(f".scitex/{short} (line {line_no})")
        for m in _RE_ENV_VAR.finditer(text):
            full = m.group(0)
            owner_part = full[len("SCITEX_") :].rsplit("_", 1)[0]
            if owner_part in self_env_tokens:
                continue
            short = _short_from_env_token(owner_part)
            if short not in _KNOWN_SHORTS:
                continue
            if owner_part in _AMBIENT_ENV_SUFFIXES:
                continue
            if _is_in_docstring_or_comment(text, m.start()):
                continue
            # Require an env-var-read context within ~40 chars to the
            # left ('os.environ', 'os.getenv', 'getenv(', 'environ['
            # or the var appearing as an os.environ key on the line).
            # This filters out Python module-level constants like
            # `SCITEX_LOGGING_AVAILABLE = True` set by try/except
            # ImportError — they are not env-var reads.
            window_start = max(0, m.start() - 60)
            window = text[window_start : m.start()]
            line_text = text[
                text.rfind("\n", 0, m.start()) + 1 : text.find("\n", m.end())
                if text.find("\n", m.end()) != -1
                else len(text)
            ]
            is_env_read = bool(
                re.search(r"\b(os\.environ|os\.getenv|getenv|environ\[)", window)
                or re.search(
                    r"\b(os\.environ|os\.getenv|getenv|environ\[).{0,80}"
                    + re.escape(full),
                    line_text,
                )
            )
            if not is_env_read:
                continue
            line_no = text[: m.start()].count("\n") + 1
            hits.append(f"{full} (line {line_no})")
        if hits:
            findings[py] = hits

    for py, hits in sorted(findings.items()):
        sample = "; ".join(hits[:3])
        more = f" (+{len(hits) - 3} more)" if len(hits) > 3 else ""
        out.append(
            violation_cls(
                "PS-145",
                str(py),
                (
                    f"reads another scitex package's user-state tree or env "
                    f"var: {sample}{more}. Use the plugin-port pattern: "
                    f"expose `SCITEX_<THIS>_*_DIRS` and let the consumer "
                    f"populate it from their own startup. See "
                    f"_skills/general/01_ecosystem/06_local-state-directories.md "
                    f"§9.5."
                ),
            )
        )


# ---------------------------------------------------------------------------
# PS-146 — pip-install side-effect
# ---------------------------------------------------------------------------

_RE_MKDIR_SCITEX = re.compile(
    r"""(?:Path\.home\(\)|expanduser)[\s\S]{0,80}?\.scitex""",
)


def check_ps146_pip_install_side_effect(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return
    try:
        text = pp.read_text(encoding="utf-8")
    except OSError:
        return
    try:
        meta = tomllib.loads(text)
    except Exception:
        return

    issues: list[str] = []

    # 1. Hatch build hooks pointing at custom scripts that mkdir under
    #    ~/.scitex/. We can't import the hook safely; flag by presence
    #    of any [tool.hatch.build.hooks.<name>] table whose hook script
    #    contains the mkdir-scitex pattern.
    hatch = (meta.get("tool", {}) or {}).get("hatch", {}) or {}
    hooks = (hatch.get("build", {}) or {}).get("hooks", {}) or {}
    for hook_name, cfg in hooks.items():
        path = (cfg or {}).get("path") or (cfg or {}).get("file")
        if not path:
            continue
        target = repo / path
        if not target.is_file():
            continue
        try:
            hook_text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _RE_MKDIR_SCITEX.search(hook_text):
            issues.append(
                f"hatch hook `{hook_name}` ({path}) mkdir's under `~/.scitex/`"
            )

    # 2. Setuptools `cmdclass` with custom install/develop class. Less
    #    common in the SciTeX stack but still flag the declaration.
    if "[tool.setuptools.cmdclass]" in text or re.search(
        r"^\s*cmdclass\s*=", text, re.MULTILINE
    ):
        # Only flag if the declaration mentions an install/develop verb —
        # `cmdclass = {"build_py": ...}` is fine.
        if re.search(r"cmdclass[\s\S]{0,200}(install|develop|post_install)", text):
            issues.append(
                "pyproject.toml declares a setuptools `cmdclass` overriding "
                "install/develop — likely an install-time side-effect"
            )

    # 3. setup.py shim with mkdir-scitex pattern.
    setup_py = repo / "setup.py"
    if setup_py.is_file():
        try:
            sp_text = setup_py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            sp_text = ""
        if _RE_MKDIR_SCITEX.search(sp_text):
            issues.append("setup.py creates `~/.scitex/...` at install time")

    if not issues:
        return
    detail = " ; ".join(issues) + (
        ". `pip install <pkg>` must not create `~/.scitex/<pkg-short>/` — "
        "use lazy `mkdir(parents=True, exist_ok=True)` from PathManager on "
        "first write. See _skills/general/"
        "01_ecosystem/06_local-state-directories.md §3.5."
    )
    out.append(violation_cls("PS-146", str(pp), detail))


# ---------------------------------------------------------------------------
# PS-147 — eval-form shell completion
# ---------------------------------------------------------------------------

# Look for a string literal of the form  eval "$(_FOO_COMPLETE=bash_source ...)
# being written/appended to a rc-like target.
_RE_EVAL_COMPLETE = re.compile(
    r"""eval\s+["']?\$\(\s*_[A-Z][A-Z0-9_]*_COMPLETE\s*=""",
)
# Match _<NAME>_COMPLETE= as a string literal anywhere in source — strong
# proxy for "this package wires shell completion".
_RE_COMPLETE_VAR = re.compile(r"_[A-Z][A-Z0-9_]*_COMPLETE\s*=")


def check_ps147_eval_form_completion(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    findings: list[tuple[Path, int, str]] = []
    for py in _src_files(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Cheap pre-filter: must mention rc-files AND _COMPLETE=.
        if not _RE_COMPLETE_VAR.search(text):
            continue
        if not re.search(r"\.(bashrc|zshrc|profile|bash_profile)\b", text):
            continue
        for m in _RE_EVAL_COMPLETE.finditer(text):
            if _is_in_docstring_or_comment(text, m.start()):
                continue
            line_no = text[: m.start()].count("\n") + 1
            line = text.splitlines()[line_no - 1]
            stripped = line.lstrip()
            findings.append((py, line_no, stripped[:120]))

    for py, line_no, snippet in findings:
        out.append(
            violation_cls(
                "PS-147",
                f"{py}:{line_no}",
                (
                    f"writes eval-form shell-completion line into a user rc "
                    f"file: `{snippet}`. The eval form re-invokes the binary "
                    f"on every shell start (~0.4s per binary). Use the "
                    f"cache-file pattern: generate completion once into "
                    f"`~/.scitex/<pkg-short>/runtime/completion/<binary>`, "
                    f"create an XDG symlink, and write a `[ -f cache ] && "
                    f"source cache` line into rc. See _skills/general/"
                    f"03_interface/02_cli/03_required-introspection-commands.md "
                    f"and 01_ecosystem/06_local-state-directories.md §11."
                ),
            )
        )
