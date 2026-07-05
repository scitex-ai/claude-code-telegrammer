"""Audit engine — walks a Click command tree and classifies tokens.

Rules audited (warn-only):
- §1   noun-verb structure        (subcommand grammar)
- §1b  banned bare leaves         (`version`, `completion`)
- §1d  vocabulary in catalog/dict
- §2   universal flag presence    (--version/-V, --help-recursive at top;
                                   --json on read verbs; --dry-run, --yes
                                   on mutating verbs)
- §4   help format                (Usage line + at least one example)
"""

from __future__ import annotations

import gzip
import importlib.metadata as im
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

import click
import yaml

from . import CATALOG, FLAT_KEEPERS

# §5/§1b banned bare leaves at any depth.
BANNED_LEAVES = {"version", "completion"}


# §1e — flags that strongly imply "start a long-running service / server / UI"
# on the leaf they appear under. When ANY of these is present on a leaf that
# ALSO classifies as a noun, the §1e rule fires regardless of whether Moby
# also classifies the same name as a verb (operator directive 13316: catch
# `scitex-todo board --port 8051` pattern ecosystem-wide).
SERVER_STARTUP_FLAGS = frozenset(
    {
        "--port",
        "--host",
        "--bind",
        "--serve",
        "--daemon",
        "--workers",
        "--listen",
        "--addr",
        "--address",
    }
)


# ----------------------------------------------------------------------- #
# Registry loader (per §6b config-precedence cascade for `scitex-dev`)    #
# ----------------------------------------------------------------------- #

REGISTRY_CASCADE_DOC = """\
Registry resolution (highest priority first):
\b
  1. --registry PATH                        (CLI flag)
  2. $SCITEX_DEV_REGISTRY                   (env var)
  3. <cwd>/.scitex/dev/ecosystem.yaml       (project)
  4. ~/.scitex/dev/ecosystem.yaml           (user)
  5. bundled scitex_dev.ecosystem.ECOSYSTEM (default)

YAML override format (any layer 1-4) replaces or extends the bundled dict;
keys present in the override win, others fall through to the default."""


def _load_registry(
    explicit_path: str | Path | None = None,
) -> tuple[dict, str]:
    """Resolve the ecosystem registry per the §6b cascade.

    Returns (registry_dict, provenance_string). The provenance string names
    the layer that supplied the registry — surfaced in --help and in the
    `--all` summary so users know what they're auditing.
    """
    from .... import _ecosystem as _eco

    bundled: dict = dict(_eco.ECOSYSTEM)

    candidates: list[tuple[str, Path | None]] = []
    if explicit_path:
        candidates.append(("--registry flag", Path(explicit_path).expanduser()))
    import os as _os

    env_path = _os.environ.get("SCITEX_DEV_REGISTRY")
    if env_path:
        candidates.append(("$SCITEX_DEV_REGISTRY", Path(env_path).expanduser()))
    candidates.append(
        (
            "project (.scitex/dev/ecosystem.yaml)",
            Path.cwd() / ".scitex" / "dev" / "ecosystem.yaml",
        )
    )
    candidates.append(
        (
            "user (~/.scitex/dev/ecosystem.yaml)",
            Path.home() / ".scitex" / "dev" / "ecosystem.yaml",
        )
    )

    for label, path in candidates:
        if path is None or not path.is_file():
            continue
        try:
            override = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            click.echo(
                f"warn  registry override at {path} is unreadable ({e}); falling through",
                err=True,
            )
            continue
        if not isinstance(override, dict):
            click.echo(
                f"warn  registry override at {path} must be a mapping; falling through",
                err=True,
            )
            continue
        merged = {**bundled, **override}
        return merged, f"{label}: {path}"

    return bundled, "bundled (scitex_dev.ecosystem.ECOSYSTEM)"


# Module-name fragments that mark a console-script as an MCP / protocol server,
# not a user-facing CLI. Audited separately by the future `audit-mcp-tools`.
_MCP_MODULE_FRAGMENTS = ("mcp_server", "_mcp", "_server")


def _is_mcp_server_entry(ep_value: str) -> bool:
    """True if a console-script target points at an MCP / protocol server."""
    module = ep_value.split(":", 1)[0].lower()
    return any(frag in module for frag in _MCP_MODULE_FRAGMENTS)


# Verb classes for §2 flag-presence checks.
READ_VERBS = {
    "list",
    "show",
    "get",
    "find",
    "search",
    "describe",
    "inspect",
    "diff",
    "tail",
    "status",
}
MUTATING_VERBS = {
    "create",
    "add",
    "init",
    "generate",
    "scaffold",
    "clone",
    "copy",
    "import",
    "register",
    "update",
    "edit",
    "rename",
    "move",
    "merge",
    "patch",
    "reset",
    "restore",
    "rollback",
    "delete",
    "remove",
    "purge",
    "clean",
    "archive",
    "revoke",
    "start",
    "stop",
    "restart",
    "pause",
    "resume",
    "enable",
    "disable",
    "install",
    "uninstall",
    "build",
    "compile",
    "publish",
    "deploy",
    "tag",
    "ship",
    "save",
    "write",
    "upload",
    "export",
    "convert",
    "sync",
    "pull",
    "push",
    "commit",
    "stash",
    "apply",
    "reconcile",
    "send",
    "notify",
    "broadcast",
    "fix",
}


@lru_cache(maxsize=1)
def _load_moby() -> dict[str, set[str]]:
    """Parse vendored Moby POS into {word: {labels}}.

    Labels: noun, verb, verb-t, verb-i.
    """
    db: dict[str, set[str]] = {}
    data = resources.files("scitex_dev._cli.audit._summary").joinpath(
        "data", "mobypos.txt.gz"
    )
    with gzip.open(data.open("rb"), mode="rt", encoding="latin-1") as f:
        for line in f:
            if "\\" not in line:
                continue
            word, pos = line.rstrip("\n").rsplit("\\", 1)
            word = word.lower()
            tags: set[str] = set()
            for c in pos:
                if c == "N":
                    tags.add("noun")
                elif c == "V":
                    tags.add("verb")
                elif c == "t":
                    tags.add("verb-t")
                elif c == "i":
                    tags.add("verb-i")
            if tags:
                db.setdefault(word, set()).update(tags)
    return db


def _load_custom_dict() -> dict[str, set[str]]:
    """Merge project + user custom dictionaries."""
    out: dict[str, set[str]] = {}
    candidates = [
        Path.cwd() / ".scitex" / "dev" / "cli-audit-dict.yaml",
        Path.home() / ".scitex" / "dev" / "cli-audit-dict.yaml",
    ]
    for path in reversed(candidates):
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        for tag, key in [
            ("noun", "nouns"),
            ("verb-t", "transitive_verbs"),
            ("verb-i", "intransitive_verbs"),
        ]:
            for w in data.get(key, []) or []:
                out.setdefault(w.lower(), set()).add(tag)
    return out


def _singular_candidates(word: str) -> list[str]:
    """Return likely singular forms of `word` (cheapest English heuristic)."""
    out: list[str] = []
    if word.endswith("ies") and len(word) > 3:
        out.append(word[:-3] + "y")  # bibentries -> bibentry
    if word.endswith("ses") and len(word) > 3:
        out.append(word[:-2])  # caches -> cache
    if word.endswith("es") and len(word) > 2:
        out.append(word[:-2])  # passes -> pass
    if word.endswith("s") and len(word) > 1:
        out.append(word[:-1])  # jobs -> job
    return out


def _classify(token: str) -> set[str]:
    """Return labels for a token using layered lookup, with plural fall-through."""
    token_lc = token.lower()
    first = token_lc.split("-")[0]

    custom = _load_custom_dict()
    if token_lc in custom:
        return set(custom[token_lc])
    if first in custom:
        return set(custom[first])

    if token_lc in CATALOG:
        return set(CATALOG[token_lc])
    if first in CATALOG:
        return set(CATALOG[first])

    moby = _load_moby()
    if token_lc in moby:
        return set(moby[token_lc])
    if first in moby:
        return set(moby[first])

    # Plural fall-through — `packages` → `package`. Only inherits the noun
    # label (a plural verb form is rare and would be picked up by Moby above).
    for candidate in _singular_candidates(token_lc):
        for source in (custom, CATALOG, moby):
            labels = source.get(candidate)
            if labels and "noun" in labels:
                return {"noun"}
    for candidate in _singular_candidates(first):
        for source in (custom, CATALOG, moby):
            labels = source.get(candidate)
            if labels and "noun" in labels:
                return {"noun"}

    return {"unknown"}


@dataclass
class Violation:
    command: str
    rule: str
    message: str


def _verb_token(name: str) -> str:
    """Extract the verb token from a leaf name.

    For tree leaves the leaf name *is* the verb (e.g. `list`).
    For compound leaves (`<verb>-<noun>`), the head is the verb (e.g. `start-dashboard`).
    """
    return name.lower().split("-")[0]


def _flag_names(cmd: click.BaseCommand) -> set[str]:
    """All flag spellings declared on a command (`--foo`, `-f`)."""
    out: set[str] = set()
    for p in getattr(cmd, "params", []) or []:
        for opt in getattr(p, "opts", []) or []:
            out.add(opt)
        for opt in getattr(p, "secondary_opts", []) or []:
            out.add(opt)
    return out


def _has_example(cmd: click.BaseCommand) -> bool:
    """§4 — concrete example detection.

    Stricter than a substring sniff: requires either
      - an `Examples:` / `Example:` header followed by content, or
      - a literal command-line invocation (`$ <cli> ...`), or
      - a fenced code block (```), or
      - a callable .. code-block:: directive.
    """
    blocks = []
    for attr in ("help", "epilog"):
        v = getattr(cmd, attr, None)
        if v:
            blocks.append(v)
    text = "\n".join(blocks)
    if not text:
        return False
    if re.search(r"(?im)^\s*examples?:\s*$", text):
        return True
    if re.search(r"(?m)^\s*\$\s+\S", text):
        return True
    if "```" in text:
        return True
    if ".. code-block::" in text:
        return True
    return False


def _is_pass_through(cmd: click.BaseCommand) -> bool:
    """§1c — verbatim-forwarding entry point detection.

    Two signals:
      1. Click `context_settings={"ignore_unknown_options": True, "allow_extra_args": True}`.
      2. A `_pass_through = True` attribute on the command (sentinel for non-Click cases
         and for explicit declarations).
    """
    if getattr(cmd, "_pass_through", False):
        return True
    cs = getattr(cmd, "context_settings", None) or {}
    return bool(cs.get("ignore_unknown_options")) and bool(cs.get("allow_extra_args"))


def _check_help_format(cmd: click.BaseCommand, full: str, out: list[Violation]) -> None:
    """§4 — help must include Usage synopsis (Click adds automatically) + an example.

    Click guarantees the Usage line, so we only check for an example marker.
    """
    if isinstance(cmd, click.Group):
        # Groups list subcommands; examples live on leaves.
        return
    if not _has_example(cmd):
        out.append(
            Violation(
                full,
                "§4",
                "help has no concrete example — add one to the docstring "
                "or Click epilog (e.g. 'Example:\\n  $ <cli> <noun> <verb> ...')",
            )
        )


# Version pattern accepted in the root help text. Matches the canonical
# `<cli> (vX.Y.Z) — ...` form used by scitex-dev/scitex-io as well as a
# bare `vX.Y.Z` token elsewhere in the help. Pre-release suffixes
# (rc1, dev0, post1, a2, b3) are accepted because importlib.metadata
# returns them verbatim.
_VERSION_IN_HELP_RE = re.compile(
    r"\bv?\d+\.\d+(?:\.\d+)?(?:[.\-_]?(?:rc|dev|post|a|b)\d+)?\b"
)


def _check_root_help_has_version(
    cmd: click.BaseCommand, full: str, out: list[Violation]
) -> None:
    """§4 — the root command's --help MUST include the package version.

    Operators reading `<cli> --help` should see which version they're
    on without a separate `<cli> --version` call. The convention is the
    canonical opening line `<cli> (vX.Y.Z) — <one-line description>`,
    but any `vX.Y.Z` token in the root command's help/epilog satisfies
    the rule. (Pass-through entry points are exempt — checked by the
    caller.)
    """
    blocks = []
    for attr in ("help", "epilog"):
        v = getattr(cmd, attr, None)
        if v:
            blocks.append(v)
    text = "\n".join(blocks)
    if not text or not _VERSION_IN_HELP_RE.search(text):
        out.append(
            Violation(
                full,
                "§4",
                "root --help does not show the package version — add the "
                "canonical opening line `<cli> (vX.Y.Z) — <description>` "
                "(use importlib.metadata.version() so the literal stays in sync)",
            )
        )


# Convention flags — when a leaf exposes one of these capabilities, it MUST
# use the canonical spelling per `08_universal-flags.md` "Convention flags"
# section. Maps non-canonical synonyms → canonical form.
_CONVENTION_SYNONYMS: dict[str, str] = {
    # Parallelism: `-j/--jobs` is the canonical (matches make/cargo/ninja)
    "--parallel": "--jobs (use `-j N` / `--jobs N`)",
    "--n-cpus": "--jobs (use `-j N` / `--jobs N`)",
    "--n_cpus": "--jobs (use `-j N` / `--jobs N`)",
    "--ncpus": "--jobs (use `-j N` / `--jobs N`)",
    "--workers": "--jobs (use `-j N` / `--jobs N`)",
    "--n-workers": "--jobs (use `-j N` / `--jobs N`)",
    # Quietness: `-q/--quiet` is canonical
    "--silent": "--quiet (use `-q` / `--quiet`)",
    # NOTE: `--debug` is intentionally NOT mapped — it has a distinct meaning
    # for server-mode commands (Flask/uvicorn debug-reload) that is not
    # verbosity. Use `-v/--verbose` for log verbosity, `--debug` for runtime
    # debug mode.
}


def _check_convention_flags(
    cmd: click.BaseCommand, full: str, out: list[Violation]
) -> None:
    """§2 convention flags — non-canonical synonyms for capabilities that
    have a standardized spelling per 08_universal-flags.md (Convention flags).
    """
    flags = _flag_names(cmd)
    for synonym, canonical in _CONVENTION_SYNONYMS.items():
        if synonym in flags:
            out.append(
                Violation(
                    full,
                    "§2",
                    f"non-canonical convention flag {synonym!r} — use {canonical}",
                )
            )


def _check_universal_flags(
    cmd: click.BaseCommand, full: str, is_root: bool, out: list[Violation]
) -> None:
    """§2 — universal flag presence."""
    flags = _flag_names(cmd)
    _check_convention_flags(cmd, full, out)

    if is_root:
        if "--version" not in flags or "-V" not in flags:
            missing = ", ".join(sorted({"--version", "-V"} - flags))
            out.append(
                Violation(
                    full,
                    "§2",
                    f"top-level missing {missing} (both long AND short forms required: `@click.version_option('-V', '--version', prog_name='<cli>')`)",
                )
            )
        # Click's canonical way to register short -h is via
        # `context_settings={"help_option_names": ["-h", "--help"]}`,
        # which doesn't surface in cmd.params. Honor it before flagging.
        ctx_help = set((cmd.context_settings or {}).get("help_option_names") or [])
        help_names = flags | ctx_help
        if "--help" not in help_names or "-h" not in help_names:
            missing = ", ".join(sorted({"--help", "-h"} - help_names))
            out.append(
                Violation(
                    full,
                    "§2",
                    f"top-level missing {missing} (both required: `context_settings={{'help_option_names': ['-h', '--help']}}`)",
                )
            )
        if "--help-recursive" not in flags:
            out.append(
                Violation(
                    full,
                    "§2",
                    "top-level missing --help-recursive flag",
                )
            )
        # --json must be parseable at root so `<cli> --json` doesn't crash.
        # Emitting JSON content (vs help text) when called with --json is
        # checked behaviorally elsewhere.
        if "--json" not in flags:
            out.append(
                Violation(
                    full,
                    "§2",
                    "top-level missing --json flag "
                    "(universal: machine-readable output for every CLI)",
                )
            )
        return

    # Leaf-only flag checks; groups themselves are read-like dispatchers.
    if isinstance(cmd, click.Group):
        return

    name = cmd.name or ""
    verb = _verb_token(name)

    if verb in READ_VERBS and "--json" not in flags:
        out.append(
            Violation(
                full,
                "§2",
                f"read verb '{verb}' missing --json flag (machine-readable output)",
            )
        )
    if verb in MUTATING_VERBS:
        if "--dry-run" not in flags:
            out.append(
                Violation(
                    full,
                    "§2",
                    f"mutating verb '{verb}' missing --dry-run flag",
                )
            )
        if not ({"--yes", "-y"} & flags):
            out.append(
                Violation(
                    full,
                    "§2",
                    f"mutating verb '{verb}' missing --yes/-y flag",
                )
            )


def _has_required_positional(cmd: click.BaseCommand) -> bool:
    """True iff ``cmd`` declares at least one required positional argument.

    A bare transitive verb at the top level is acceptable when it takes
    its object as a positional argument (`<cli> <verb> <OBJECT>`) — the
    object is right there, just not concatenated into the subcommand
    name. Compare ``pip install <pkg>``, ``git commit -m``, ``pytest
    <path>``: ergonomic, unambiguous, no `<verb>-<noun>` clutter. The
    auditor's §1 rule recognises this shape and skips the warning.
    """
    for p in getattr(cmd, "params", []) or []:
        if isinstance(p, click.Argument) and getattr(p, "required", False):
            return True
    return False


def _walk(
    cmd: click.BaseCommand,
    path: list[str],
    out: list[Violation],
    root_display: str,
) -> None:
    # Skip hidden commands — not part of the public CLI surface
    # (typically deprecation redirects kept for back-compat).
    if getattr(cmd, "hidden", False):
        return
    is_root = not path
    name = root_display if is_root else (cmd.name or "<root>")
    full = " ".join(path + [name]) if path else name
    is_group = isinstance(cmd, click.Group)

    # §2 universal flag presence.
    _check_universal_flags(cmd, full, is_root, out)

    # §4 root --help must show the package version. Pass-through entry
    # points are exempt because their help is forwarded verbatim from
    # the upstream tool.
    if is_root and not _is_pass_through(cmd):
        _check_root_help_has_version(cmd, full, out)

    if not is_root:
        # §1c — pass-through entry points are exempt from §1 / §1d / §4.
        if _is_pass_through(cmd):
            return

        labels = _classify(name)
        is_leaf = not is_group
        is_compound = "-" in name

        # §1b banned bare leaves.
        if is_leaf and name.lower() in BANNED_LEAVES:
            redirect = {
                "version": "use the --version/-V flag at top level",
                "completion": "use 'install-shell-completion' or 'print-shell-completion'",
            }[name.lower()]
            out.append(
                Violation(full, "§1b", f"banned bare leaf '{name}' — {redirect}")
            )

        if is_leaf:
            # §1 — leaf-noun check. Historically the exemption
            # (`{verb-t, verb-i, verb, flat-keeper} & labels`) silently
            # passed multi-class noun-verb homonyms such as `board`
            # (Moby classifies as both noun and verb-t/verb-i), letting
            # `scitex-todo board --port 8051` slip through (operator
            # directive 13316). At TOP LEVEL (depth=1) AND for BARE
            # (non-compound) leaves the rule is tightened: a leaf
            # carrying `noun` in its labels is flagged regardless of
            # also-verb labels, because the operator's CLI grammar
            # requires top-level bare leaves to be unambiguously verbs.
            # Compound leaves like `print-shell-completion` are
            # explicitly excluded from PART A — the compound IS the
            # `<verb>-<object>` grammar the rule is asking for.
            top_level_leaf = len(path) == 1
            multi_class_homonym = (
                bool({"verb-t", "verb-i", "verb"} & labels) and "noun" in labels
            )
            if (
                "noun" in labels
                and (
                    (top_level_leaf and multi_class_homonym and not is_compound)
                    or not ({"verb-t", "verb-i", "verb", "flat-keeper"} & labels)
                )
                and name not in FLAT_KEEPERS
                and "flat-keeper" not in labels
            ):
                suffix = (
                    " — Moby classifies this as both noun AND verb; if the "
                    "verb meaning is intended in this CLI context, add to "
                    "`.scitex/dev/cli-audit-dict.yaml` under `intransitive_verbs:` "
                    "(same escape hatch `next` uses)."
                    if multi_class_homonym
                    else ""
                )
                out.append(
                    Violation(
                        full,
                        "§1",
                        f"leaf token looks like a noun — transitive action implied; "
                        f"use '<verb>-{name}' (e.g. start-{name}) or add a sibling verb"
                        + suffix,
                    )
                )

            # §1e — server-startup-flag heuristic. High-signal catch:
            # a noun-classified leaf at top level that accepts any of
            # `--port / --host / --bind / --serve / --daemon / --workers /
            # --listen / --addr / --address` is unambiguously starting a
            # service; the grammar should be `<noun> start` (group) or
            # `start-<noun>` (compound). Fires even when the §1 check
            # would have exempted the leaf via a Moby verb label —
            # operator directive 13316's exact pattern.
            if "noun" in labels and top_level_leaf:
                if SERVER_STARTUP_FLAGS & _flag_names(cmd):
                    out.append(
                        Violation(
                            full,
                            "§1e",
                            f"top-level noun leaf '{name}' accepts a server-"
                            f"startup flag (one of --port/--host/--bind/"
                            f"--serve/--daemon/--workers/--listen/--addr/"
                            f"--address) — that's a service-start verb in "
                            f"disguise; rename to 'start-{name}' or nest "
                            f"under a '{name}' group with a 'start' "
                            f"subcommand (e.g. '{name} start --port …').",
                        )
                    )
            if (
                ("verb-t" in labels or "verb" in labels)
                and not is_compound
                and len(path) == 1
                and "noun" not in labels
                and not _has_required_positional(cmd)
            ):
                out.append(
                    Violation(
                        full,
                        "§1",
                        f"bare transitive verb at top level — needs an object; "
                        f"use '{name}-<object>' or nest under a noun, OR add "
                        f"a required positional argument that IS the object "
                        f"(e.g. '{name} <SOURCE>')",
                    )
                )
        else:
            if ({"verb-t", "verb-i", "verb"} & labels) and "noun" not in labels:
                out.append(
                    Violation(
                        full,
                        "§1",
                        "group token looks like a verb — non-leaf subcommands must be nouns",
                    )
                )

        if labels == {"unknown"}:
            out.append(
                Violation(
                    full,
                    "§1d",
                    f"'{name}' not in catalog, custom dict, or Moby POS — "
                    f"add to .scitex/dev/cli-audit-dict.yaml or rename",
                )
            )

        # §4 help format on leaves.
        _check_help_format(cmd, full, out)

    if is_group:
        next_path = [name] if is_root else path + [name]
        for sub in cmd.commands.values():
            _walk(sub, next_path, out, root_display)


# --------------------------------------------------------------------- #
# argparse adapter — wrap an argparse.ArgumentParser tree as click nodes #
#                                                                       #
# Implementation lives in `scitex_dev._audit_argparse_adapter` (outside  #
# the `_cli/` subtree) so the §11 walker — which scans `_cli/**/*.py`    #
# for any `import argparse` — does not flag the auditor itself. The     #
# adapter is essential: it lets the auditor wrap legacy argparse-based  #
# CLIs in third-party packages and check them under the same rules as   #
# Click CLIs.                                                            #
# --------------------------------------------------------------------- #

from ...._core.audit_argparse_adapter import (  # noqa: E402
    StopBeforeParse as _StopBeforeParse,
    intercept_parse_calls as _intercept_parse_calls,
    wrap_argparse as _wrap_argparse,
)

import contextlib as _contextlib  # noqa: E402  -- needed by helpers below


class _PackageTimeout(Exception):
    """Raised when a single package's audit exceeds the watchdog window."""


@_contextlib.contextmanager
def _watchdog(seconds: float):
    """SIGALRM-based watchdog (Unix, main-thread only).

    Wraps a slow-or-hung `_audit_one` call in `run_audit_all` so a single
    bad package can't wedge the ecosystem run. On non-Unix or off-main-thread,
    silently no-ops so behavior degrades to the prior (no-watchdog) baseline.
    """
    import signal as _signal
    import threading as _threading

    if (
        not hasattr(_signal, "SIGALRM")
        or _threading.current_thread() is not _threading.main_thread()
        or seconds <= 0
    ):
        yield
        return

    def _handler(signum, frame):
        raise _PackageTimeout()

    prev_handler = _signal.signal(_signal.SIGALRM, _handler)
    _signal.setitimer(_signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, prev_handler)


@_contextlib.contextmanager
def _isolated_streams():
    """Run a block with stdin/stdout/stderr redirected to /dev/null.

    MCP-server entry points often close stdio on import or write protocol
    frames to stdout — the auditor's reporter streams must survive that.
    On exit, sys.stdout/stderr are restored to the original interpreter
    streams (via os.fdopen on fds 1/2 if the saved streams were closed).
    """
    import os as _os
    import sys as _sys

    real_stdin = _sys.stdin
    real_out, real_err = _sys.__stdout__, _sys.__stderr__
    devnull_in = open(_os.devnull, "r")
    devnull_out = open(_os.devnull, "w")
    saved_stdin = _sys.stdin
    _sys.stdin = devnull_in
    try:
        with (
            _contextlib.redirect_stdout(devnull_out),
            _contextlib.redirect_stderr(devnull_out),
        ):
            yield
    finally:
        _sys.stdin = real_stdin if not real_stdin.closed else saved_stdin
        # `closefd=False` is essential: without it, the wrapper's eventual GC
        # would close the inherited fd 1/2 and break every subsequent write
        # (including `click.echo` output of later violations and the summary).
        if real_out is None or real_out.closed:
            _sys.stdout = _os.fdopen(1, "w", closefd=False)
        else:
            _sys.stdout = real_out
        if real_err is None or real_err.closed:
            _sys.stderr = _os.fdopen(2, "w", closefd=False)
        else:
            _sys.stderr = real_err
        try:
            devnull_in.close()
        except Exception:
            pass
        try:
            devnull_out.close()
        except Exception:
            pass


def _capture_root(callable_obj):
    """Invoke `callable_obj` with parse calls intercepted; return the captured
    root command — either an `argparse.ArgumentParser` or a `click.BaseCommand`.

    Catches the common patterns:
      - `def main(argv): parser=...; parser.parse_args(argv)`  (argparse)
      - `def main(): cli()`                                    (Click, lazy import)
      - `def main(): app.main(args=[])`                        (Click, explicit)

    Returns None if no parse call was triggered.

    The patching contract (assumed by every checker that calls this):
      1. argparse.ArgumentParser.parse_args / parse_known_args raise _StopBeforeParse
         after appending `self` to the captured list.
      2. click.BaseCommand.main does the same.
      3. sys.argv is set to a single-element list to avoid leaking real args.
      4. All three originals are restored even on exception.

    Limitation — multi-parser CLIs:
      Only the **first** parser whose `parse_args` is invoked is captured.
      A `def main(): outer.parse_args(); inner.parse_args()` shape would
      lose `inner`. No real ecosystem package does this today, but if one
      shows up the fix is to extend `_intercept_parse_calls` to keep
      collecting after the first hit and rank candidates by `_actions` count.
    """
    import sys as _sys

    captured: list[object] = []
    saved_argv = _sys.argv
    _sys.argv = [getattr(callable_obj, "__name__", "cli")]
    try:
        with _intercept_parse_calls(captured):
            # Try `main(argv)` then `main()` — different conventions in the wild.
            for invocation in (lambda: callable_obj([]), lambda: callable_obj()):
                try:
                    invocation()
                except _StopBeforeParse:
                    break
                except TypeError:
                    continue  # signature mismatch; try the other shape
                except SystemExit:
                    if captured:
                        break
                except BaseException:
                    if captured:
                        break
                if captured:
                    break
    finally:
        _sys.argv = saved_argv
    return captured[0] if captured else None


def _resolve_entry_point(package: str) -> click.BaseCommand | None:
    """Find the root command for an entry-point name.

    Tries, in order:
      1. Entry point itself is a click.BaseCommand.
      2. Entry point is a wrapper `def main(): app()` — scan its module for
         a module-level click.BaseCommand.
      3. Entry point is a `def main(argv): parser=...; parser.parse_args(argv)`
         (argparse) — capture the parser and wrap it as a Click-shaped tree.
      4. Otherwise → not auditable.
    """
    import importlib

    try:
        eps = im.entry_points(group="console_scripts")
    except TypeError:
        eps = im.entry_points().get("console_scripts", [])
    matching = [ep for ep in eps if ep.name == package]
    if not matching:
        return None

    last_err: str | None = None
    for ep in matching:
        try:
            obj = ep.load()
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            continue
        if isinstance(obj, click.BaseCommand):
            return obj

        # Wrapper function — scan its module for a click root.
        mod_name = getattr(obj, "__module__", None)
        if mod_name:
            try:
                mod = importlib.import_module(mod_name)
            except Exception:
                mod = None
            if mod is not None:
                for attr in ("cli", "app", "main_cli", "root", "main"):
                    val = getattr(mod, attr, None)
                    if isinstance(val, click.BaseCommand):
                        return val
                for val in vars(mod).values():
                    if isinstance(val, click.BaseCommand):
                        return val

        # Invoke-and-capture fallback — handles both lazy-imported click roots
        # and argparse parsers built inside main().
        if callable(obj):
            root = _capture_root(obj)
            if isinstance(root, click.BaseCommand):
                return root
            if root is not None:
                return _wrap_argparse(root, name=package)

        last_err = f"not a click or argparse CLI (got {type(obj).__name__})"

    _resolve_entry_point._last_err = last_err  # type: ignore[attr-defined]
    return None


def _check_introspection(
    cmd: click.BaseCommand, package: str, out: list[Violation]
) -> None:
    """§1a — `list-python-apis` (top-level) and `mcp list-tools` must exist.

    Both must accept --json. Verbosity ladder (-v/-vv/-vvv) is checked
    behaviorally elsewhere; here we only assert presence and --json.
    """
    if not isinstance(cmd, click.Group):
        return

    sub = cmd.commands.get("list-python-apis")
    if sub is None:
        out.append(
            Violation(
                package,
                "§1a",
                "missing required top-level command 'list-python-apis'",
            )
        )
    else:
        if "--json" not in _flag_names(sub):
            out.append(
                Violation(
                    f"{package} list-python-apis",
                    "§1a",
                    "missing --json flag (required for §1a introspection)",
                )
            )

    mcp = cmd.commands.get("mcp")
    if mcp is None or not isinstance(mcp, click.Group):
        out.append(
            Violation(
                package,
                "§1a",
                "missing required 'mcp' command group with 'list-tools' subcommand",
            )
        )
        return
    list_tools = mcp.commands.get("list-tools")
    if list_tools is None:
        out.append(
            Violation(
                f"{package} mcp",
                "§1a",
                "missing required 'list-tools' subcommand under 'mcp'",
            )
        )
    elif "--json" not in _flag_names(list_tools):
        out.append(
            Violation(
                f"{package} mcp list-tools",
                "§1a",
                "missing --json flag (required for §1a introspection)",
            )
        )

    # §1a — shell-completion subcommands are MANDATORY for every CLI:
    # `install-shell-completion` (writes the script to ~/.config/...) and
    # `print-shell-completion` (prints to stdout). Without them, users get
    # nothing on `<pkg> <TAB>`. Codified 2026-05-06 after scitex-scholar
    # shipped without either subcommand and the gap surfaced only when a
    # human noticed `scitex-scholar install` failed.
    for required in ("install-shell-completion", "print-shell-completion"):
        if required not in cmd.commands:
            out.append(
                Violation(
                    package,
                    "§1a",
                    f"missing required top-level command {required!r} — "
                    "without it `<pkg> <TAB>` produces nothing. Wire via "
                    "`scitex_dev._cli._completion.attach_shell_completion(group, "
                    f'prog_name="{package}")`.',
                )
            )

    # §1a — `<pkg> skills {list, get, install}` group required when the
    # package ships a `_skills/` directory. Lets users introspect and
    # install the bundled skills without having to discover scitex-dev.
    if _package_ships_skills(package):
        skills = cmd.commands.get("skills")
        if skills is None or not isinstance(skills, click.Group):
            out.append(
                Violation(
                    package,
                    "§1a",
                    "missing required 'skills' command group "
                    "({list, get, install}) — package ships _skills/ but "
                    "exposes no CLI to list/get/install them",
                )
            )
        else:
            for verb in ("list", "get", "install"):
                if verb not in skills.commands:
                    out.append(
                        Violation(
                            f"{package} skills",
                            "§1a",
                            f"missing required '{verb}' subcommand under 'skills'",
                        )
                    )


# ----------------------------------------------------------------------- #
# Package-locator helpers (registry source-tree fallback)                  #
#                                                                         #
# Mirrors the fix landed in PRs #177 (audit-skills) and #178 (audit-      #
# python-apis). Several §-checks in this file resolve a package via       #
# `importlib.util.find_spec(...)` and silently skip the check when the    #
# package is not pip-installed in the auditor's venv. Result: §11 CLI-    #
# framework / §2 no-interactive-prompts / §1a skills-subcommand audits   #
# went uncalled for every locally-cloned peer, hiding real violations.   #
#                                                                         #
# These helpers keep `find_spec` as the primary path and fall back to the #
# ecosystem registry's `local_path` so the audit runs against the on-disk #
# source tree. A truly-missing package (neither installed nor registered  #
# nor on-disk) still returns None so the legacy skip is preserved for     #
# genuinely-unauditable inputs.                                           #
# ----------------------------------------------------------------------- #


def _registry_local_src(distribution: str) -> Path | None:
    """Source-tree fallback: ``<local_path>/src/<import_name>/`` from registry.

    Returns None if the registry entry is missing, has no ``local_path``,
    or the path doesn't exist on disk. Defensive — a stale / partial
    registry import returns None silently so the per-package audit keeps
    working.
    """
    try:
        from ...._ecosystem._registry import ECOSYSTEM
    except Exception:  # pragma: no cover — defensive
        return None
    info = ECOSYSTEM.get(distribution) or {}
    local_path = info.get("local_path")
    if not local_path:
        return None
    try:
        root = Path(local_path).expanduser()
    except (RuntimeError, OSError):  # pragma: no cover — defensive
        return None
    candidate = root / "src" / distribution.replace("-", "_")
    return candidate if candidate.is_dir() else None


def _resolve_pkg_root(distribution: str) -> Path | None:
    """Return ``<pkg>/`` — installed search location or registry-fallback src tree.

    Used by checks that walk the package tree (e.g. ``rglob("*.py")``).
    The returned path is the directory containing ``__init__.py`` plus the
    rest of the package source.
    """
    import importlib.util

    import_name = distribution.replace("-", "_")
    spec = importlib.util.find_spec(import_name)
    if spec is not None and spec.submodule_search_locations:
        return Path(next(iter(spec.submodule_search_locations)))
    return _registry_local_src(distribution)


def _resolve_dotted_module_file(distribution: str, dotted: str) -> Path | None:
    """Resolve ``pkg.sub.mod`` to its concrete ``.py`` file.

    Tries ``importlib.util.find_spec`` first; on miss, walks the dotted
    path under the registry-fallback source tree. Picks the package's
    ``__init__.py`` when the final segment is a directory, otherwise the
    ``.py`` file. Returns None if neither resolution succeeds — caller
    should treat that as "module not present, skip".
    """
    import importlib.util

    # ``find_spec`` raises ``ModuleNotFoundError`` when the dotted path
    # has an unimportable parent (the common case in CI where the package
    # is on disk but not pip-installed). Treat the raise the same as a
    # None return — fall through to the registry source-tree walk.
    try:
        spec = importlib.util.find_spec(dotted)
    except (ImportError, ValueError):
        spec = None
    if spec is not None and spec.origin is not None:
        return Path(spec.origin)
    pkg_root = _resolve_pkg_root(distribution)
    if pkg_root is None:
        return None
    parts = dotted.split(".")
    rest = parts[1:]  # parts[0] is import_name (already pkg_root)
    if not rest:
        init = pkg_root / "__init__.py"
        return init if init.is_file() else None
    sub = pkg_root
    for p in rest[:-1]:
        sub = sub / p
    last = rest[-1]
    candidate_pkg = sub / last / "__init__.py"
    if candidate_pkg.is_file():
        return candidate_pkg
    candidate_mod = sub / f"{last}.py"
    return candidate_mod if candidate_mod.is_file() else None


def _package_ships_skills(package: str) -> bool:
    """True if ``<pkg>/_skills/<package>/`` exists.

    Uses ``_resolve_pkg_root`` so non-installed but on-disk-valid peers
    are detected via the registry fallback (was previously returning False
    for every such peer — a phantom that hid §1a `skills` subcommand
    omission audits across the ecosystem).
    """
    pkg_root = _resolve_pkg_root(package)
    if pkg_root is None:
        return False
    return (pkg_root / "_skills" / package).is_dir()


def _expected_env_prefix(package: str) -> str | None:
    """Compute `SCITEX_<PKG>_` prefix for a scitex-* package.

    Returns None for non-scitex packages (out of scope per §6a).
    """
    name = package.lower()
    if name == "scitex":
        return "SCITEX_"
    if not name.startswith("scitex-"):
        return None
    short = name[len("scitex-") :].replace("-", "_").upper()
    return f"SCITEX_{short}_"


def _bare_pkg_prefix(package: str) -> str | None:
    """Forbidden bare package-name prefix (e.g. `PLT_` for scitex-plt)."""
    name = package.lower()
    if not name.startswith("scitex-"):
        return None
    return name[len("scitex-") :].replace("-", "_").upper() + "_"


# Common third-party / OS env vars that any code may legitimately read.
_ALLOWED_ENV_PREFIXES = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TERM",
    "DISPLAY",
    "LANG",
    "LC_",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    "EDITOR",
    "PAGER",
    "PWD",
    "OLDPWD",
    "XDG_",
    "SSH_",
    "SUDO_",
    "DBUS_",
    "PYTHON",
    "VIRTUAL_ENV",
    "CONDA_",
    "PIP_",
    "PYTEST_",
    "PYTHONPATH",
    "MPLBACKEND",
    "MPLCONFIGDIR",
    "CI",
    "GITHUB_",
    # `gh` CLI's canonical token env var; widely used alongside GITHUB_TOKEN.
    "GH_TOKEN",
    "GITLAB_",
    "RUNNER_",
    "AWS_",
    "GCP_",
    "GOOGLE_",
    "AZURE_",
    "OPENAI_",
    "ANTHROPIC_",
    "HF_",
    "HUGGINGFACE_",
    "WANDB_",
    "MLFLOW_",
    "SLURM_",
    "SBATCH_",
    "OMP_",
    "MKL_",
    "OPENBLAS_",
    "NUMEXPR_",
    "CUDA_",
    "NCCL_",
    "TF_",
    "TORCH_",
    "JAX_",
    "KERAS_",
    "RAY_",
    "NO_COLOR",
    "FORCE_COLOR",
    "CLICOLOR",
    "CLICOLOR_FORCE",
    "DOCKER_",
    "PODMAN_",
    "APPTAINER_",
    "SINGULARITY_",
    "POSTGRES_",
    "MYSQL_",
    "REDIS_",
    "MONGO_",
    "DJANGO_",
    "FLASK_",
    "VITE_",
    "NODE_",
    "NPM_",
    "YARN_",
    "JUPYTER_",
    "IPYTHON",
    "READTHEDOCS",
    "RTD_",
    "SPHINX_",
    "CLAUDE_",
    "CURSOR_",
)


def _is_allowed_env(var: str, pkg_allowlist: tuple[str, ...] = ()) -> bool:
    """True when ``var`` is allowed by the universal or per-package list.

    The universal list (:data:`_ALLOWED_ENV_PREFIXES`) covers third-party
    tools, OS conventions and well-known ML/dev frameworks. The
    per-package layer is the opt-out declared via
    ``[tool.scitex_dev] env_allowlist`` in the audited package's
    ``pyproject.toml`` — see
    :mod:`scitex_dev._cli.audit._summary._env_allowlist`. Both layers
    apply the same "equal-to-stripped or prefix-match" semantics, so
    callers don't have to remember which list a prefix lives in.
    """
    if any(var == p.rstrip("_") or var.startswith(p) for p in _ALLOWED_ENV_PREFIXES):
        return True
    from ._env_allowlist import is_var_in_pkg_allowlist

    return is_var_in_pkg_allowlist(var, pkg_allowlist)


@lru_cache(maxsize=1)
def _known_scitex_prefixes() -> tuple[str, ...]:
    """Return the set of valid `SCITEX_<PKG>_` prefixes from the bundled registry."""
    try:
        from .... import _ecosystem as _eco
    except Exception:
        return ()
    out: set[str] = {"SCITEX_"}  # umbrella
    for name in _eco.ECOSYSTEM:
        prefix = _expected_env_prefix(name)
        if prefix:
            out.add(prefix)
    return tuple(sorted(out))


def _scan_env_vars(
    package: str,
    out: list[Violation],
    *,
    pkg_allowlist: tuple[str, ...] | None = None,
) -> None:
    """§6a — env vars must use `SCITEX_<PKG>_*`; bare `<PKG>_*` is forbidden.

    Scans the installed package's .py files. Best-effort: only flags
    obvious violations (bare-pkg prefix or non-allowed non-SCITEX vars).

    Parameters
    ----------
    package
        Distribution name (e.g. ``"scitex-agent-container"``).
    out
        Accumulator for violations.
    pkg_allowlist
        Per-package opt-out prefixes. When ``None`` (the default), the
        list is read from the audited package's ``pyproject.toml``
        ``[tool.scitex_dev] env_allowlist`` (see
        :mod:`scitex_dev._cli.audit._summary._env_allowlist`). Pass an
        explicit tuple (including the empty tuple ``()``) to bypass the
        pyproject read — used by tests that operate on a synthetic
        package tree.
    """
    expected = _expected_env_prefix(package)
    if expected is None:
        return
    bare = _bare_pkg_prefix(package)

    if pkg_allowlist is None:
        from ._env_allowlist import read_pkg_env_allowlist

        pkg_allowlist = read_pkg_env_allowlist(package)

    try:
        dist = im.distribution(package)
    except im.PackageNotFoundError:
        return
    files = dist.files or []
    py_files = [
        f
        for f in files
        if str(f).endswith(".py") and "/tests/" not in str(f) and "/test_" not in str(f)
    ]

    pat = re.compile(
        r"""os\.environ(?:\.get|\[)\s*\(?\s*["']([A-Z][A-Z0-9_]+)["']"""
        r"""|os\.getenv\s*\(\s*["']([A-Z][A-Z0-9_]+)["']"""
    )
    found_bare: set[str] = set()
    found_wrong: set[str] = set()
    for fp in py_files:
        try:
            text = Path(fp.locate()).read_text(encoding="utf-8", errors="ignore")
        except (OSError, AttributeError):
            continue
        for m in pat.finditer(text):
            var = m.group(1) or m.group(2)
            if not var or _is_allowed_env(var, pkg_allowlist):
                continue
            if bare and var.startswith(bare):
                found_bare.add(var)
            elif var.startswith("SCITEX_") and not var.startswith(expected):
                # Cross-package reference (e.g. scitex-dev reading SCITEX_PLT_*).
                # Allow if the prefix matches a known sibling package; flag if it
                # doesn't (likely a typo).
                known_prefixes = _known_scitex_prefixes()
                matched = False
                for sibling in known_prefixes:
                    if var.startswith(sibling):
                        matched = True
                        break
                if not matched:
                    found_wrong.add(var)
            elif not var.startswith("SCITEX_") and not _is_allowed_env(
                var, pkg_allowlist
            ):
                found_wrong.add(var)

    for var in sorted(found_bare):
        out.append(
            Violation(
                package,
                "§6a",
                f"env var '{var}' uses bare package prefix — rename to '{expected}{var[len(bare or '') :]}'",
            )
        )
    for var in sorted(found_wrong):
        out.append(
            Violation(
                package,
                "§6a",
                f"env var '{var}' has no recognized prefix — use '{expected}*' or add to allowlist",
            )
        )


def _check_config_help(
    cmd: click.BaseCommand, package: str, out: list[Violation]
) -> None:
    """§6b — root --help must document the config-path fallback order."""
    expected = _expected_env_prefix(package)
    if expected is None:
        return
    text = " ".join(
        filter(None, [getattr(cmd, "help", "") or "", getattr(cmd, "epilog", "") or ""])
    )
    epilog_or_help = text.lower()
    has_config_yaml = "config.yaml" in epilog_or_help
    has_env_ref = f"{expected.lower()}config" in epilog_or_help or expected in text
    has_path_hint = ".scitex/" in epilog_or_help or "~/.scitex" in epilog_or_help
    if not (has_config_yaml or has_env_ref or has_path_hint):
        out.append(
            Violation(
                package,
                "§6b",
                f"root --help does not document config-path fallback "
                f"(expected mention of 'config.yaml', '{expected}CONFIG', or '~/.scitex/...')",
            )
        )


def _run_subprocess(args: list[str], timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a CLI command; return (exit_code, stdout, stderr). -1 on timeout/error."""
    import subprocess

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return -1, "", ""


def _collect_json_leaves(cmd: click.BaseCommand, path: list[str]) -> list[list[str]]:
    """Return paths (e.g. ['mcp', 'list-tools']) of every leaf that has --json."""
    out: list[list[str]] = []
    if getattr(cmd, "hidden", False):
        return out
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            out.extend(_collect_json_leaves(sub, path + [name]))
        return out
    if "--json" in _flag_names(cmd):
        out.append(path)
    return out


def _collect_hidden_leaves(cmd: click.BaseCommand, path: list[str]) -> list[list[str]]:
    """Return paths of every hidden leaf (deprecation-redirect candidates)."""
    out: list[list[str]] = []
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            child_path = path + [name]
            if getattr(sub, "hidden", False) and not isinstance(sub, click.Group):
                out.append(child_path)
            else:
                out.extend(_collect_hidden_leaves(sub, child_path))
    return out


def _check_behavioral(
    package: str,
    out: list[Violation],
    cmd: click.BaseCommand | None = None,
    timeout: float = 10.0,
) -> None:
    """Behavioral checks (§1a ladder, §3 exit codes, §5 redirects, §7 parity, §8 JSON)."""
    import json as _json

    sub_to = max(1.0, min(timeout, 30.0))

    # §3 — bogus flag at top level should exit 2 (Click default).
    rc, _so, _se = _run_subprocess(
        [package, "--definitely-not-a-flag-xyz"], timeout=sub_to
    )
    if rc != 2 and rc != -1:
        out.append(
            Violation(
                package,
                "§3",
                f"unknown flag at top-level exited {rc}, expected 2 (usage error)",
            )
        )

    # §3 — bogus subcommand should exit 2.
    rc, _so, _se = _run_subprocess(
        [package, "definitely-not-a-subcommand-xyz"], timeout=sub_to
    )
    if rc not in (
        2,
        -1,
        0,
    ):  # 0 means CLI accepted gibberish — also a bug, but separate signal
        if rc != 2:
            out.append(
                Violation(
                    package,
                    "§3",
                    f"unknown subcommand exited {rc}, expected 2 (usage error)",
                )
            )

    # §1a behavioral — list-python-apis verbosity ladder.
    levels = [[], ["-v"], ["-vv"], ["-vvv"]]
    counts: list[int] = []
    for extra in levels:
        rc, so, _se = _run_subprocess(
            [package, "list-python-apis", *extra], timeout=sub_to
        )
        if rc != 0:
            counts.append(-1)
            continue
        counts.append(len([ln for ln in so.splitlines() if ln.strip()]))
    if all(c >= 0 for c in counts):
        for i in range(1, len(counts)):
            if counts[i] < counts[i - 1]:
                out.append(
                    Violation(
                        f"{package} list-python-apis",
                        "§1a",
                        f"verbosity ladder not monotonic: -{'v' * i} produced fewer "
                        f"non-empty lines ({counts[i]}) than -{'v' * (i - 1)} ({counts[i - 1]})",
                    )
                )
                break

    # §8 — every leaf with --json must produce parseable JSON on stdout.
    if cmd is not None:
        for leaf_path in _collect_json_leaves(cmd, []):
            rc, so, _se = _run_subprocess(
                [package, *leaf_path, "--json"], timeout=sub_to
            )
            if rc == 0 and so.strip():
                try:
                    _json.loads(so)
                except _json.JSONDecodeError:
                    out.append(
                        Violation(
                            f"{package} {' '.join(leaf_path)}",
                            "§8",
                            "--json stdout is not parseable JSON (log contamination?)",
                        )
                    )

    # §5 — hidden leaves should be deprecation redirects: exit non-zero with
    # a "renamed" / "moved" message on stderr.
    if cmd is not None:
        for leaf_path in _collect_hidden_leaves(cmd, []):
            rc, _so, se = _run_subprocess([package, *leaf_path], timeout=sub_to)
            if rc == 0:
                out.append(
                    Violation(
                        f"{package} {' '.join(leaf_path)}",
                        "§5",
                        "hidden leaf exited 0 — expected non-zero deprecation redirect",
                    )
                )
                continue
            blob = se.lower()
            if not any(
                tok in blob for tok in ("renamed", "moved", "deprecated", "use ")
            ):
                out.append(
                    Violation(
                        f"{package} {' '.join(leaf_path)}",
                        "§5",
                        "hidden leaf exited non-zero but stderr lacks redirect hint "
                        "(expected 'renamed', 'moved', 'deprecated', or 'use ...')",
                    )
                )

    # §7 — CLI ↔ MCP parity. When both `list-python-apis --json` and
    # `mcp list-tools --json` are present, every Python API should map to
    # an MCP tool (loosely: the MCP set should cover a substantial fraction
    # of the Python API set).
    py_rc, py_so, _ = _run_subprocess(
        [package, "list-python-apis", "--json"], timeout=sub_to
    )
    mcp_rc, mcp_so, _ = _run_subprocess(
        [package, "mcp", "list-tools", "--json"], timeout=sub_to
    )
    if py_rc == 0 and mcp_rc == 0 and py_so.strip() and mcp_so.strip():
        try:
            py_set = _extract_names(_json.loads(py_so))
            mcp_set = _extract_names(_json.loads(mcp_so))
        except (_json.JSONDecodeError, AttributeError, TypeError):
            py_set, mcp_set = set(), set()
        if py_set and mcp_set:
            # MCP names typically prefix the package short name; strip it for comparison.
            short = package.replace("scitex-", "").replace("-", "_")
            mcp_normalized = {n.removeprefix(f"{short}_") for n in mcp_set}
            missing = py_set - mcp_normalized
            if missing and len(missing) > len(py_set) * 0.5:
                out.append(
                    Violation(
                        package,
                        "§7",
                        f"{len(missing)}/{len(py_set)} Python APIs have no matching MCP tool "
                        f"(sample: {sorted(missing)[:3]})",
                    )
                )


def _extract_names(payload) -> set[str]:
    """Pull a flat name set out of a JSON listing (handles list[str] | list[dict] | dict)."""
    if isinstance(payload, list):
        out: set[str] = set()
        for item in payload:
            if isinstance(item, str):
                out.add(item)
            elif isinstance(item, dict):
                for k in ("name", "tool", "api", "id"):
                    v = item.get(k)
                    if isinstance(v, str):
                        out.add(v)
                        break
        return out
    if isinstance(payload, dict):
        for k in ("apis", "tools", "items", "data", "results"):
            if k in payload:
                return _extract_names(payload[k])
        return set(k for k in payload.keys() if isinstance(k, str))
    return set()


def _check_option_positional_ordering(
    package: str, root: click.BaseCommand, out: list[Violation]
) -> None:
    """§10 — options on either side of the SOURCE positional must work.

    Click's ``invoke_without_command=True`` group with a positional
    argument treats anything *after* the positional as a subcommand
    name, so the natural ``cli <SOURCE> --flag value`` form crashes.
    The fix is a pre-Click ``argv`` reorder hook wired into the
    console-script entry (and ``__main__.py``).

    Static check (no subprocess): when the root command is a Click
    Group with ``invoke_without_command=True`` AND has a top-level
    positional argument, the registered console-script value must NOT
    point at the click group itself — it must point at a wrapper
    function (commonly ``cli_entrypoint``) that calls
    ``sys.argv[1:] = _reorder_argv(sys.argv[1:])`` before handing off
    to the group. See `interface-cli-option-positional-ordering`.
    """
    if not isinstance(root, click.Group):
        return
    if not getattr(root, "invoke_without_command", False):
        return
    if not _has_required_positional(root) and not any(
        isinstance(p, click.Argument) for p in (root.params or [])
    ):
        return
    ep_value = _ep_value_for(package)
    if ep_value is None:
        return
    # Resolve the entry-point object and compare against the click group.
    mod_name, _, obj_name = ep_value.partition(":")
    try:
        import importlib

        mod = importlib.import_module(mod_name)
        ep_obj = getattr(mod, obj_name, None)
    except Exception:
        return
    # If the entry-point IS the click group (or one of its standard
    # decorated forms), there's no chance to rewrite argv.
    if ep_obj is root or (
        isinstance(ep_obj, click.BaseCommand) and ep_obj.name == root.name
    ):
        out.append(
            Violation(
                package,
                "§10",
                f"top-level group has a positional but the console-script "
                f"entry ({ep_value}) is the click group itself — "
                f"`cli <SOURCE> --flag value` will fail with 'No such "
                f"command'. Wire a `cli_entrypoint()` wrapper that "
                f"reorders sys.argv before calling the group "
                f"(see interface-cli-option-positional-ordering).",
            )
        )


def _check_cli_framework(package: str, out: list[Violation]) -> None:
    """§11 — CLI framework conformance.

    Every scitex-* CLI must use Click (per `08_universal-flags.md` /
    `07_audit-cli.md`). argparse causes drift the auditor itself
    cannot fully police: doubled subparser metavar in --help, manual
    --json wiring on every parser, no shared CategorizedGroup, no
    decorator ergonomics. Click is already a transitive dep through
    scitex-dev; argparse adds zero benefit to the ecosystem.

    Static check: parse the entry-point module + every sibling .py in
    its directory for `import argparse` / `from argparse`. Flag any
    occurrence in a CLI module.
    """
    ep_value = _ep_value_for(package)
    if ep_value is None:
        return
    # entry-point format: "module.path:object" — locate the module file.
    # Uses the registry-aware resolver so non-installed peers (CI / fresh
    # checkout) still get §11 audited against their on-disk source tree.
    mod_name = ep_value.split(":", 1)[0]
    ep_file = _resolve_dotted_module_file(package, mod_name)
    if ep_file is None:
        return
    # Walk only files that are actually part of the CLI tree:
    #   * the entry-point file itself
    #   * every .py under a `_cli/` subdir of the entry-point's parent
    #     (the canonical Click submodule layout: pkg/_cli/__init__.py
    #     plus pkg/_cli/_*.py command files)
    # Recursing into the whole package root produced false positives for
    # stats library files (posthoc/_*.py), linter rule modules, even
    # this auditor itself — none of those are CLI entry-points and any
    # argparse import there is unrelated to §11.
    py_files = [ep_file]
    cli_subdir = ep_file.parent / "_cli"
    if cli_subdir.is_dir():
        py_files += [
            p
            for p in cli_subdir.rglob("*.py")
            if p != ep_file and "__pycache__" not in p.parts
        ]
    elif ep_file.parent.name == "_cli":
        # Entry-point already lives inside _cli/ — sweep its siblings.
        py_files += [
            p
            for p in ep_file.parent.rglob("*.py")
            if p != ep_file and "__pycache__" not in p.parts
        ]

    import re as _re

    pat = _re.compile(
        r"^\s*(import\s+argparse|from\s+argparse\s+import)", _re.MULTILINE
    )
    offenders: list[str] = []
    for f in py_files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if pat.search(text):
            offenders.append(str(f))

    if offenders:
        # Single rolled-up violation; list first 3 file paths so the
        # remediation is actionable without flooding output.
        sample = ", ".join(offenders[:3])
        more = f" (+{len(offenders) - 3} more)" if len(offenders) > 3 else ""
        out.append(
            Violation(
                package,
                "§11",
                f"CLI uses `argparse` — Click is canonical (zero drift, "
                f"shared CategorizedGroup, --json/--help-recursive built-in). "
                f"Migrate: {sample}{more}",
            )
        )


def _ep_value_for(package: str) -> str | None:
    """First console-script ``module:obj`` value registered under ``package``.

    Resolution order (each step proceeds to the next on miss, so a package
    that is neither installed nor on-disk-registered still returns None):

    1. **Installed metadata.** ``importlib.metadata.entry_points()`` —
       picks up console-scripts from any peer that's been
       ``pip install``-ed in the auditor's venv.
    2. **On-disk pyproject (registry fallback).** When the peer is NOT
       installed but IS in the ecosystem registry, read
       ``<local_path>/pyproject.toml``'s ``[project.scripts]`` table and
       return ``scripts.get(package)``. This is the upstream piece of the
       same fail-silent class PRs #177 / #178 / #179 closed — without it
       audit-summary's §10 / §11 / §1a checks couldn't even ask "what is
       this package's CLI entry?" for a freshly-cloned peer, so the
       downstream resolvers (`_resolve_dotted_module_file` etc.) never
       ran on non-installed peers.

    A truly-missing console-script (not in metadata, not in registry, or
    registry path / pyproject missing) still returns None so callers
    keep their "no console script — skipped" behaviour for genuinely-
    scriptless packages.
    """
    # 1. Installed metadata.
    try:
        eps = im.entry_points(group="console_scripts")
    except TypeError:  # pragma: no cover — pre-3.10 API path
        eps = im.entry_points().get("console_scripts", [])
    for ep in eps:
        if ep.name == package:
            return ep.value

    # 2. On-disk pyproject via registry. Defensive — every parse failure
    # falls through to None so a single malformed pyproject never breaks
    # the per-package audit.
    try:
        from ...._ecosystem._registry import ECOSYSTEM
    except Exception:  # pragma: no cover — defensive
        return None
    info = ECOSYSTEM.get(package) or {}
    local_path = info.get("local_path")
    if not local_path:
        return None
    try:
        root = Path(local_path).expanduser()
    except (RuntimeError, OSError):  # pragma: no cover — defensive
        return None
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        import tomllib
    except ImportError:  # pragma: no cover — 3.10 path
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return None
    try:
        with open(pyproject, "rb") as fh:
            meta = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    scripts = (meta.get("project") or {}).get("scripts") or {}
    value = scripts.get(package)
    return value if isinstance(value, str) else None


_INTERACTIVE_OK_LINE_MARKER = "# audit-cli: interactive-ok"
_INTERACTIVE_OK_FILE_MARKER = "# audit-cli: file-interactive-ok"


def _has_file_interactive_ok_marker(text: str) -> bool:
    """True if the file opts out of §2 wholesale via a top-of-file marker.

    Looked-for marker (case-sensitive, must appear in the first 30 lines —
    well within any docstring + import block):

        ``# audit-cli: file-interactive-ok``

    Use this on files whose entire purpose is interactive (e.g.
    ``_login.py``, an ``auth_setup`` Click command). Per-call markers
    are preferred when only one or two calls need exempting; this
    file-level switch is for "the whole module is intentional".
    """
    for line in text.split("\n", 30)[:30]:
        if _INTERACTIVE_OK_FILE_MARKER in line:
            return True
    return False


def _line_or_above_has_interactive_ok(lines: list[str], lineno: int) -> bool:
    """True if the call at ``lineno`` (1-indexed) is exempted by a marker.

    Accepted shapes (case-sensitive substring match — the message tail is
    free-form so authors can document the why):

        click.prompt(...)  # audit-cli: interactive-ok — login flow
        # audit-cli: interactive-ok — login flow
        click.prompt(...)

    The immediately-preceding form must be on the line directly above the
    call (skipping blank lines and other comment lines does NOT walk past
    a non-comment, non-blank line). This keeps the exemption tight to the
    one call it documents — a marker far above does not silently exempt
    every call below it.
    """
    if lineno <= 0 or lineno > len(lines):
        return False
    # Same-line trailing comment.
    if _INTERACTIVE_OK_LINE_MARKER in lines[lineno - 1]:
        return True
    # Immediately-preceding non-blank line (typical "comment above call"
    # idiom). Allow intermediate blank lines, but not a non-comment line.
    i = lineno - 2
    while i >= 0 and not lines[i].strip():
        i -= 1
    if i < 0:
        return False
    stripped = lines[i].lstrip()
    return stripped.startswith("#") and _INTERACTIVE_OK_LINE_MARKER in stripped


def _check_no_interactive_prompts(package: str, out: list[Violation]) -> None:
    """§2 — CLI source must not call `click.confirm`, `click.prompt`,
    `getpass.getpass`, or built-in `input`.

    Mutating actions are gated by `--yes`/`-y` (refuse with non-zero exit
    otherwise). Read flows are expected to fail loud with a clear error,
    not pause for input. Agentic / cron / CI invocations cannot answer a
    Y/n prompt — they hang, then time out — so any blocking-stdin call
    is a silent reliability bomb.

    Static AST scan over `src/<pkg>/**/*.py`. Skips obvious non-CLI
    directories (`tests/`, `examples/`, `docs/`).

    Exemptions (precision refinement — some CLI commands are LEGITIMATELY
    interactive, e.g. an OAuth flow that prompts for a secret, or a
    destructive command that requires a typed-out confirmation token):

    * **Per-call marker** — ``# audit-cli: interactive-ok`` on the SAME
      line as the call OR on the line immediately above (with optional
      blank lines but no intervening non-comment line). The author is
      asserting "this prompt is the intended UX, not a CI-reliability
      bomb." Keep the exemption tight to ONE call: a comment far above
      the call does NOT silently exempt every call below it.

    * **Per-file marker** — ``# audit-cli: file-interactive-ok`` anywhere
      in the first 30 lines. Exempts every prompt in the file. Use this
      for whole modules that exist to be interactive (e.g. ``_login.py``,
      an ``auth_setup`` Click command file).

    Markers are case-sensitive substring matches; any tail after the
    sentinel is treated as free-form documentation, so authors can write
    why the exemption is justified (``# audit-cli: interactive-ok —
    login flow needs the user's TOTP``) without confusing the parser.
    """
    import ast

    # Use the registry-aware resolver so non-installed peers (CI / fresh
    # ecosystem checkout) still get §2 audited against their on-disk
    # source tree instead of silently passing.
    pkg_root = _resolve_pkg_root(package)
    if pkg_root is None or not pkg_root.exists():
        return

    forbidden = {
        (
            "click",
            "confirm",
        ): "click.confirm() — use `--yes`/`-y` and refuse-without-yes instead",
        (
            "click",
            "prompt",
        ): "click.prompt() — accept the value as a CLI option/flag instead",
        (
            "getpass",
            "getpass",
        ): "getpass.getpass() — accept secret via env var or --password-file",
        ("getpass", "getuser"): None,  # informational, not a prompt — exempt
    }
    forbidden_bare = {"input"}  # builtin input()

    for py in pkg_root.rglob("*.py"):
        if any(s in py.parts for s in ("__pycache__", "tests", "examples", "docs")):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError:
            continue
        # File-level opt-out (e.g. `_login.py`) — skip the whole file.
        if _has_file_interactive_ok_marker(text):
            continue
        lines = text.split("\n")
        rel = py.relative_to(pkg_root.parent)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            # click.confirm(...) / getpass.getpass(...)
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                key = (f.value.id, f.attr)
                msg = forbidden.get(key)
                if msg is None and key not in forbidden:
                    continue
                if msg is None:
                    continue  # exempt entry
                if _line_or_above_has_interactive_ok(lines, node.lineno):
                    continue  # per-call opt-out
                out.append(
                    Violation(
                        package,
                        "§2",
                        f"interactive prompt at {rel}:{node.lineno} — {msg}",
                    )
                )
            # bare input(...) — exempt if it's `input.button-primary` etc.
            elif isinstance(f, ast.Name) and f.id in forbidden_bare:
                if _line_or_above_has_interactive_ok(lines, node.lineno):
                    continue  # per-call opt-out
                out.append(
                    Violation(
                        package,
                        "§2",
                        f"interactive `input()` at {rel}:{node.lineno} — "
                        "CLIs must be non-interactive; accept value via "
                        "option/flag or fail with a clear error.",
                    )
                )


def _check_startup_speed(
    package: str,
    out: list[Violation],
    threshold_ms: int = 500,
    runs: int = 3,
) -> None:
    """§10 — the MARGINAL cost of `import <module>` (above bare-interpreter
    startup) must be < threshold_ms.

    Click bash-completion calls the program once per Tab press to resolve
    dynamic completions, so a slow import = unusable tab-completion. The
    fix is PEP 562 lazy `__getattr__` in the top-level `__init__.py`
    (see `_skills/general/03_interface/01_python-api/
    04_lazy-imports-and-optional-deps.md`).

    Measurement (2026-06-19): the metric is ``T - B`` — ``T`` is the wall-clock
    of ``python -c "import <module>"`` and ``B`` is the wall-clock of a bare
    ``python -c "pass"`` reference, each taken as the *best of N* runs.
    Subtracting ``B`` cancels the interpreter + site + coverage startup baseline
    (and the machine-speed factor inside it), so the check reflects the
    PACKAGE's own import cost — not the runner's filesystem or CPU load.
    best-of-N (min) warms the file cache and drops transient load spikes: the
    earlier absolute-time check false-failed on the shared/NFS Spartan CI node,
    where a cold first import over the network FS measured 937ms while the
    package's real marginal cost is a few ms.
    """
    import subprocess as _sp
    import sys as _sys
    import time as _time

    ep_value = _ep_value_for(package)
    if ep_value is None:
        return
    # Entry-point format is "module.path:object"; take the TOP-LEVEL package.
    module_name = ep_value.split(":", 1)[0].split(".", 1)[0]
    if not module_name:
        return

    def _best_ms(code: str) -> float | None:
        """Best-of-`runs` wall-clock (ms) of ``python -c <code>``; None on failure."""
        best: float | None = None
        for _ in range(max(1, runs)):
            t0 = _time.perf_counter()
            try:
                r = _sp.run(
                    [_sys.executable, "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except Exception:
                return None
            if r.returncode != 0:
                return None  # import failure — covered elsewhere
            dt = (_time.perf_counter() - t0) * 1000.0
            best = dt if best is None else min(best, dt)
        return best

    # Bare interpreter reference, then the package import — same env, so site +
    # coverage + machine-speed cancel in the difference.
    baseline = _best_ms("pass")
    full = _best_ms(f"import {module_name}")
    if baseline is None or full is None:
        return  # import failure — covered elsewhere

    v = _startup_speed_violation(
        package, module_name, baseline, full, threshold_ms, runs
    )
    if v is not None:
        out.append(v)


def _startup_speed_violation(
    package: str,
    module_name: str,
    baseline: float,
    full: float,
    threshold_ms: int,
    runs: int,
) -> "Violation | None":
    """Decide the §10 finding from already-measured timings (pure, testable).

    Returns a §10 ERROR Violation when the package's marginal import cost
    exceeds ``threshold_ms`` on a *trustworthy* measurement, a §10w WARN
    Violation when the runner is too slow/noisy to measure reliably, or
    ``None`` when the import is comfortably under budget.

    Baseline-sanity guard
    ---------------------
    The metric is ``marginal = full - baseline`` (see ``_check_startup_speed``).
    Subtracting the bare-interpreter ``baseline`` is only meaningful when
    ``baseline`` is small relative to the budget. On a loaded / NFS CI runner
    the *bare* interpreter alone has measured 1072–1476ms (normal ≈ 20ms);
    once ``baseline`` exceeds the entire ``threshold_ms`` budget, the residual
    ``marginal`` is dominated by scheduling/FS noise and flips sign run-to-run,
    false-flaking the SAME package. In that regime we DO NOT emit the §10
    ERROR — we emit a §10w WARNING (warn-tier severity, so ``audit-all`` exit
    stays 0) and skip the budget assertion. On normal runners
    (``baseline`` ≪ ``threshold_ms``) the check stays fully STRICT: the
    marginal is measured and enforced exactly as before.
    """
    if baseline > threshold_ms:
        return Violation(
            package,
            "§10w",
            f"§10 import-budget SKIPPED: runner baseline {baseline:.0f}ms exceeds "
            f"the {threshold_ms}ms budget itself — environment too slow/noisy "
            "(likely NFS or loaded CI) to measure import time reliably; re-run on "
            "a normal runner to enforce.",
        )

    marginal = full - baseline
    if marginal > threshold_ms:
        return Violation(
            package,
            "§10",
            f"`import {module_name}` adds {marginal:.0f}ms over bare-interpreter "
            f"startup (>{threshold_ms}ms threshold; import={full:.0f}ms, "
            f"baseline={baseline:.0f}ms, best-of-{runs}). Slow tab-completion: Click "
            "runs the program once per Tab press. Convert "
            f"{module_name}/__init__.py to PEP 562 lazy `__getattr__` (see python-api "
            "skill 04_lazy-imports-and-optional-deps.md, 'PEP 562 module __getattr__' section).",
        )
    return None


# --------------------------------------------------------------------- #
# Rule severity & filtering                                              #
# --------------------------------------------------------------------- #

# Severity tiers — used by --severity to gate which findings are reported.
#
# Per 2026-05-06 directive: any rule that has been live long enough to ship a
# documented spec is `error` (CI must fail). Demote a rule back to `warn` only
# after a concrete false-positive lands on develop. `info` is reserved for
# purely advisory categorizations (pass-through entry-points) that cannot
# describe a violation.
RULE_SEVERITY: dict[str, str] = {
    "§1": "error",
    "§1a": "error",
    "§1b": "error",
    "§1c": "info",
    "§1d": "error",
    "§1e": "info",
    "§2": "error",
    "§3": "error",
    "§4": "error",
    "§5": "error",
    # §6 (Python API ↔ MCP tool parity). Promoted back to error 2026-05-08
    # at user direction: severity must match the rule corpus's intent —
    # if it's a real violation, label it as one. False-positives on
    # utility-heavy packages should be addressed via per-package
    # allowlists (skip_rules in test_audit.py) or a tightened threshold,
    # not by globally demoting the rule to warn.
    "§6": "error",
    "§6a": "error",
    "§6b": "error",
    "§7": "error",
    "§8": "error",
    "§10": "error",
    # §10w — warn-tier sibling of §10. Emitted only when the runner's
    # bare-interpreter baseline already exceeds the import budget, so the
    # marginal import cost cannot be measured reliably (loaded/NFS CI). WARN,
    # not error, so `audit-all` exit stays 0 instead of false-flaking the fleet.
    "§10w": "warn",
    "§11": "error",
    # PA-304: umbrella imports (scitex.X / import scitex) inside standalone
    # source. Drags umbrella __init__ + lazy re-export setup into every call
    # — measurable on NFS-mounted homes (HPC). Codified 2026-05-06 after the
    # scitex-scholar 2.7s cold-import surfaced on Spartan.
    "PA-304": "error",
    # PA-305: playwright.async_api imported without capture_debug_artifacts_async
    # call. Codified 2026-05-06 — every browser-automation decision point must
    # capture screenshot+HTML so selector regressions are diagnosable
    # post-mortem. See _skills/general/02_package/09_browser-automation-debugging.md.
    "PA-305": "error",
}
SEVERITY_ORDER = {"info": 0, "warn": 1, "error": 2}


def _max_severity(violations: list[Violation]) -> str:
    """Highest severity present among violations; 'info' if list is empty."""
    best = "info"
    for v in violations:
        sev = RULE_SEVERITY.get(v.rule, "warn")
        if SEVERITY_ORDER[sev] > SEVERITY_ORDER[best]:
            best = sev
    return best


def _filter_violations(
    violations: list[Violation],
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
) -> list[Violation]:
    """Apply --rule / --exclude / --severity gating to a violation list."""
    out: list[Violation] = []
    threshold = SEVERITY_ORDER.get(min_severity or "info", 0)
    rules_set = {r.lstrip("§") for r in rules}
    excl_set = {r.lstrip("§") for r in exclude}
    for v in violations:
        rule_key = v.rule.lstrip("§")
        if rules_set and rule_key not in rules_set:
            continue
        if rule_key in excl_set:
            continue
        sev = RULE_SEVERITY.get(v.rule, "warn")
        if SEVERITY_ORDER[sev] < threshold:
            continue
        out.append(v)
    return out


def _audit_one(
    package: str,
    behavioral: bool = False,
    timeout: float = 30.0,
    ep_value_for=None,
) -> tuple[str, list[Violation]]:
    """Audit a single package; return (status, violations).

    Status is one of: "ok", "warn", "skip-mcp", "not-found", "not-auditable".
    """
    if ep_value_for is None:
        ep_value_for = _ep_value_for
    ep_value = ep_value_for(package)
    if ep_value is None:
        return "not-found", []
    if _is_mcp_server_entry(ep_value):
        return "skip-mcp", []

    # MCP / argparse entry points may close stdio on import or write protocol
    # frames to stdout — `_isolated_streams` redirects the three standard
    # streams to /dev/null and restores them on exit.
    with _isolated_streams():
        cmd = _resolve_entry_point(package)

    if cmd is None:
        last_err = getattr(_resolve_entry_point, "_last_err", None)
        if hasattr(_resolve_entry_point, "_last_err"):
            delattr(_resolve_entry_point, "_last_err")
        return f"not-auditable: {last_err or 'unknown'}", []

    out: list[Violation] = []
    _walk(cmd, [], out, root_display=package)
    _check_introspection(cmd, package, out)
    _check_config_help(cmd, package, out)
    _scan_env_vars(package, out)
    _check_startup_speed(package, out)
    _check_no_interactive_prompts(package, out)
    _check_cli_framework(package, out)
    _check_option_positional_ordering(package, cmd, out)
    if behavioral:
        _check_behavioral(package, out, cmd, timeout=timeout)
    return ("ok" if not out else "warn"), out


def _violation_to_dict(v: Violation) -> dict:
    return {"command": v.command, "rule": v.rule, "message": v.message}


def _emit_human(package: str, status: str, violations: list[Violation]) -> None:
    if status == "skip-mcp":
        click.echo(
            f"info  {package}: MCP / protocol server — skipped (use audit-mcp-tools when available)"
        )
        return
    from .._emit import emit as _emit

    if status == "not-found":
        # No console script is a legitimate state for utility packages
        # (types, base/core libraries, etc.) — audit-cli can't enforce
        # a CLI convention on a package that has no CLI. Surface as info.
        _emit("info", f"{package}: no console script — skipped")
        return
    if status.startswith("not-auditable"):
        _emit("error", f"{package}: {status}", err=True)
        return
    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

    if status == "ok":
        _emit("success", f"{package}: no CLI convention violations")
        emit_disclaimer()
        return
    sev = _max_severity(violations)
    level = "error" if sev == "error" else "warning"
    noun = "error(s)" if sev == "error" else "warning(s)"
    _emit(level, f"{package}: {len(violations)} {noun}")
    for v in violations:
        _emit(level, f"  [{v.rule}] {v.command}: {v.message}")
    emit_disclaimer()
    emit_skill_hints()


def _emit_json(records: list[dict], registry_provenance: str) -> None:
    import json as _json

    payload = {
        "registry_source": registry_provenance,
        "results": records,
    }
    click.echo(_json.dumps(payload, indent=2))


def run_audit(
    package: str,
    behavioral: bool = False,
    output_json: bool = False,
    registry_provenance: str = "",
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
) -> int:
    """Audit a single package (single-target mode)."""
    # Category-aware skip: archived packages, templates, etc. — see
    # `scitex_dev._ecosystem._core.should_skip_audit` for the per-auditor
    # category map.
    try:
        from ...._ecosystem import should_skip_audit
    except ImportError:
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(package, "audit-cli")
    if skip:
        if output_json:
            rec = {"package": package, "status": f"skip-{reason}", "violations": []}
            _emit_json([rec], registry_provenance or "single-package mode")
        else:
            from .._emit import emit as _emit_skip

            _emit_skip("skip", f"{package}: {reason}")
        return 0

    status, violations = _audit_one(package, behavioral=behavioral, timeout=timeout)
    violations = _filter_violations(violations, rules, exclude, min_severity)
    if not violations and status == "warn":
        status = "ok"
    if output_json:
        rec = {
            "package": package,
            "status": status,
            "violations": [_violation_to_dict(v) for v in violations],
        }
        _emit_json([rec], registry_provenance or "single-package mode")
    else:
        _emit_human(package, status, violations)
    if status.startswith("not-auditable"):
        return 2
    if status == "not-found":
        # Legitimate "no CLI" — exit 0, audit-cli has nothing to enforce.
        return 0
    # Exit 1 if any violation reaches `error` severity. Warnings alone exit 0.
    return 1 if _max_severity(violations) == "error" else 0


def run_audit_all(
    behavioral: bool = False,
    output_json: bool = False,
    dry_run: bool = False,
    registry_path: str | Path | None = None,
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
) -> int:
    """Audit every package in the registry (ecosystem-wide mode).

    With dry_run=True, lists the targets without auditing.
    """
    registry, provenance = _load_registry(registry_path)
    targets: list[tuple[str, str, str]] = []  # (name, ep_value, status_hint)
    for name, _info in registry.items():
        ep_value = _ep_value_for(name)
        if ep_value is None:
            targets.append((name, "", "not-found"))
            continue
        if _is_mcp_server_entry(ep_value):
            targets.append((name, ep_value, "skip-mcp"))
            continue
        targets.append((name, ep_value, "audit"))

    if dry_run:
        if output_json:
            payload = {
                "registry_source": provenance,
                "dry_run": True,
                "targets": [
                    {"package": n, "entry_point": ep, "action": s}
                    for n, ep, s in targets
                ],
            }
            import json as _json

            click.echo(_json.dumps(payload, indent=2))
        else:
            click.echo(f"# registry: {provenance}")
            click.echo(f"# {len(targets)} package(s) — dry-run, no audit performed")
            for name, ep, status in targets:
                click.echo(f"  {status:<12} {name:<28} {ep}")
        return 0

    records: list[dict] = []
    counts = {"ok": 0, "warn": 0, "skip-mcp": 0, "not-found": 0, "not-auditable": 0}
    any_error = False
    for name, ep, hint in targets:
        if hint == "not-found":
            status, violations = "not-found", []
        elif hint == "skip-mcp":
            status, violations = "skip-mcp", []
        else:
            # Wall-clock watchdog so a single hanging package can't wedge --all.
            # Budget = behavioral subprocess cap + 5s slack for static checks.
            wall_budget = max(timeout + 5.0, 10.0)
            try:
                with _watchdog(wall_budget):
                    status, violations = _audit_one(
                        name, behavioral=behavioral, timeout=timeout
                    )
            except _PackageTimeout:
                status, violations = (
                    f"not-auditable: timed out after {wall_budget:.0f}s",
                    [],
                )
        violations = _filter_violations(violations, rules, exclude, min_severity)
        if not violations and status == "warn":
            status = "ok"
        if not output_json:
            _emit_human(name, status, violations)
        if _max_severity(violations) == "error" or status.startswith("not-auditable"):
            any_error = True
        records.append(
            {
                "package": name,
                "status": status,
                "violations": [_violation_to_dict(v) for v in violations],
            }
        )
        bucket = "not-auditable" if status.startswith("not-auditable") else status
        counts[bucket] = counts.get(bucket, 0) + 1

    if output_json:
        _emit_json(records, provenance)
    else:
        click.echo("")
        click.echo(f"# registry: {provenance}")
        click.echo(
            f"# summary: {counts['ok']} ok, {counts['warn']} warn, "
            f"{counts['skip-mcp']} skipped (MCP), "
            f"{counts['not-found']} not-found, {counts['not-auditable']} not-auditable"
        )
    return 1 if any_error else 0
