"""Category S (research script organization): STX-S009 / STX-S010.

These are PATH / FILENAME rules — they inspect where a research-project
script lives and what it is named, not its AST. Both are research-gated
(``project-type: research`` in ``.scitex/dev/config.yaml``) and default to
WARNING; a project escalates either to ERROR via ``per_rule_severity``.

Why they exist (neurovista scripts/ reorg, 2026-07-02): clew provenance
hashes a script by its PATH. A flat, ungrouped ``scripts/`` tree churns
those paths on every reorg (moved file → broken chain); grouping scripts
into stable DOMAIN directories (``scripts/pac/``, ``scripts/stats/`` …)
keeps the provenance edge stable and the tree readable.

- STX-S009 — a script sits FLAT under ``scripts/`` (no domain subdir).
- STX-S010 — a script FILENAME does not begin with a verb.

Both target files UNDER a configured ``script_dir`` — which
``is_script()`` deliberately excludes from the ``@stx.session`` rules — so
the checker emits them from ``get_issues()`` BEFORE its ``is_script``
early-return (see ``checker.get_issues``).
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources
from pathlib import Path

from ._base import Rule
from ._lookup import lookup as _lk

S009 = Rule(
    id="STX-S009",
    severity="warning",
    category="structure",
    message=(
        "Research script sits flat under scripts/ — group it into a DOMAIN "
        "subdirectory (scripts/<domain>/…) for a stable clew-provenance path"
    ),
    suggestion=(
        "Move this script into a domain directory so its path is stable and\n"
        "the tree stays organized by topic:\n"
        "  scripts/calc_pac.py        -> scripts/pac/calc_pac.py\n"
        "  scripts/plot_raster.py     -> scripts/figures/plot_raster.py\n"
        "clew hashes a script by its PATH: a flat scripts/ churns those paths\n"
        "on every reorg (moved file -> provenance chain breaks). Domain dirs\n"
        "keep the producing-session edge stable.\n"
        "Knobs (.scitex/dev/config.yaml / [tool.scitex-dev.linter]):\n"
        "  script_domain_min_depth = 1     # required domain-dir depth\n"
        "  script_org_exempt = [...]        # filenames to skip\n"
        "Escalate to error: per_rule_severity = { \"STX-S009\": \"error\" }"
    ),
)

S010 = Rule(
    id="STX-S010",
    severity="warning",
    category="structure",
    message=(
        "Research script filename does not start with a verb — name scripts "
        "for the ACTION they perform (calc_/plot_/build_/…)"
    ),
    suggestion=(
        "Begin the filename with an imperative verb describing what it does:\n"
        "  analysis.py     -> calc_analysis.py\n"
        "  pac_figure.py   -> plot_pac_figure.py\n"
        "  dataset.py      -> build_dataset.py\n"
        "Verb-first names read as a pipeline and keep scripts/ scannable.\n"
        "Extend the accepted verbs (.scitex/dev/config.yaml / "
        "[tool.scitex-dev.linter]):\n"
        "  script_verb_prefixes = [\"calc\", \"plot\", \"build\", ...]\n"
        "Escalate to error: per_rule_severity = { \"STX-S010\": \"error\" }"
    ),
)


# Built-in tech/CLI verbs that a general English lexicon does not carry —
# coined-but-real imperatives (``symlink``) plus abbreviated forms
# (``calc``/``gen``/``eval``/``preprocess``). The PRIMARY judge of "is this a
# verb" is the bundled WordNet-derived lexicon (see ``_load_verb_lexicon``,
# operator directive 2026-07-02: a real verb lexicon, not a curated CLI
# whitelist — the v1 whitelist produced 22 false positives on neurovista);
# this set only supplements it, and ``script_verb_prefixes`` extends both.
DEFAULT_SCRIPT_VERBS: frozenset[str] = frozenset(
    {
        "calc", "concat", "eval", "gen", "preprocess", "resample",
        "setup", "symlink", "sync",
    }
)


@lru_cache(maxsize=1)
def _load_verb_lexicon() -> frozenset[str]:
    """English verb lemmas bundled as package data (``_verb_lexicon.txt``).

    Derived from WordNet 3.1 ``index.verb`` (single-token lowercase lemmas,
    ~8.4k entries, incl. British spellings like ``analyse``). Loaded once per
    process. Returns an empty set when the data file is missing (e.g. a
    stripped install) — the check then degrades to the built-in defaults +
    config extension rather than crashing or mass-flagging.
    """
    try:
        text = (
            resources.files("scitex_dev.linter._rules")
            .joinpath("_verb_lexicon.txt")
            .read_text(encoding="utf-8")
        )
    except Exception:
        return frozenset()
    return frozenset(
        line
        for line in (raw.strip() for raw in text.splitlines())
        if line and not line.startswith("#")
    )


def _is_verb_token(token: str, extra_verbs: set) -> bool:
    """True iff *token* reads as an imperative verb.

    Accepts: lexicon membership, the built-in tech-verb defaults, the
    project's ``script_verb_prefixes``, and ``re``-prefixed re-derivations
    (``recompute``/``rerender`` → ``compute``/``render``) which WordNet does
    not enumerate.
    """
    if token in extra_verbs:
        return True
    lexicon = _load_verb_lexicon()
    if token in lexicon:
        return True
    if token.startswith("re") and len(token) > 4:
        base = token[2:]
        if base in lexicon or base in extra_verbs:
            return True
    return False

DEFAULT_SCRIPT_ORG_EXEMPT: tuple[str, ...] = (
    "__init__.py",
    "__main__.py",
    "conftest.py",
)

_TOKEN_SPLIT_RE = re.compile(r"[_\-]+")


def _first_token(stem: str) -> str:
    """First ``_``/``-``-delimited token of a filename stem, lowercased."""
    parts = _TOKEN_SPLIT_RE.split(stem, maxsplit=1)
    return parts[0].lower() if parts and parts[0] else ""


def _script_dir_index(parts: tuple[str, ...], script_dirs) -> int | None:
    """Index of the LAST path component that names a configured script dir."""
    idx = None
    for i, comp in enumerate(parts):
        if comp in script_dirs:
            idx = i
    return idx


def check_script_organization(checker) -> bool:
    """Emit STX-S009 / STX-S010 for a research script under a script dir.

    Returns True iff at least one issue was added. The caller (``checker.
    get_issues``) gates this on ``"research" in config.project_types`` and
    runs it BEFORE its ``is_script`` early-return, because files under
    ``scripts/`` are excluded from ``is_script`` by design.
    """
    cfg = checker.config
    path = Path(checker.filepath)
    if path.suffix != ".py":
        return False

    name = path.name
    # Configured exemptions EXTEND the built-in ones (never drop __init__ etc.).
    exempt = set(DEFAULT_SCRIPT_ORG_EXEMPT) | set(
        getattr(cfg, "script_org_exempt", None) or ()
    )
    if name in exempt or (name.startswith("__") and name.endswith("__.py")):
        return False

    parts = path.parts
    script_dirs = list(getattr(cfg, "script_dirs", None) or ["scripts"])
    idx = _script_dir_index(parts, script_dirs)
    if idx is None:
        return False  # not under a configured script dir

    added = False

    # STX-S009 — domain grouping. Components between the script dir and the
    # filename are the domain path; require at least `min_depth` of them.
    subdirs = parts[idx + 1 : -1]
    min_depth = getattr(cfg, "script_domain_min_depth", 1)
    if len(subdirs) < min_depth:
        checker._add(_lk("STX-S009"), 1, 0, "")
        added = True

    # STX-S010 — verb-first filename, judged by the bundled verb LEXICON
    # (WordNet-derived) first; the built-in tech-verb defaults and the
    # project's ``script_verb_prefixes`` EXTEND it (see ``_is_verb_token``).
    extra_verbs = set(DEFAULT_SCRIPT_VERBS) | set(
        getattr(cfg, "script_verb_prefixes", None) or ()
    )
    token = _first_token(path.stem)
    if token and not _is_verb_token(token, extra_verbs):
        checker._add(_lk("STX-S010"), 1, 0, "")
        added = True

    return added
