"""PS-CLEW-001 / PS-AGENT-001 — Clew add_claim / claims.json terminus checks.

Implements the two rules introduced after the paper-scitex-clew
post-mortem on 2026-06-01 (the agent declared SUCCESS while the
chain of evidence was silently broken):

  PS-CLEW-001 — add_claim without self-verify.
    A .py file calls ``clew.add_claim(...)`` (also matched as
    ``scitex_clew.add_claim`` and the ``from scitex_clew import
    add_claim`` alias) but the same file does NOT also call
    ``clew.verify_claim(...)`` or ``clew.list_claims(...)``. Without
    that post-loop self-verify the agent never notices a broken
    source-hash chain — the run completes "successfully" with
    `source_verified=False` claims rolled into the manuscript.

  PS-AGENT-001 — agent script with no claims.json terminus.
    A ``scripts/agent/*.py`` file calls ``clew.add_claim(...)`` but
    NO module-level / function-level call writes a real file at
    ``data/results/claims.json``. The DAG terminus MUST be a real
    file; the launcher's verifier scores by reading
    ``data/results/claims.json``. Without it the run is unscored.

Both rules are AST-based and intentionally prefer false-NEGATIVES
over false-positives — if ``add_claim`` is called indirectly via a
helper module the rule stays quiet. The same is true for writes
routed through a helper that ultimately writes the canonical
``claims.json`` — only direct ``Path(...).write_text(...)`` and
``stx.io.save(..., "...claims.json")`` calls in the file itself
count for PS-AGENT-001. Documented limitation: extend this when
the helper-routing patterns settle.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _attr_chain(node: ast.AST) -> str:
    """Return dotted name for ``a.b.c`` / ``Name('a')`` / nothing.

    Returns "" when the expression isn't a pure attribute chain
    (e.g. subscript, call, lambda).
    """
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


_CLEW_NAMES = {"clew", "scitex_clew"}


def _is_clew_call(node: ast.Call, attr: str, *, clew_aliases: set[str]) -> bool:
    """True iff ``node`` is ``<clew>.attr(...)`` for any module alias.

    Also matches ``attr(...)`` directly (the
    ``from scitex_clew import attr`` shape).
    """
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == attr:
        # `clew.add_claim(...)` / `scitex_clew.add_claim(...)` /
        # `some_alias.add_claim(...)` if alias for scitex_clew.
        chain = _attr_chain(func.value)
        if chain in clew_aliases:
            return True
    if isinstance(func, ast.Name) and func.id == attr:
        # `add_claim(...)` (from-import or rebound name).
        if attr in clew_aliases:
            # The plain function name landed in module namespace via
            # `from scitex_clew import add_claim`. We have to be careful
            # here: many local helpers might be named `verify_claim`
            # without any connection to clew. We only register this
            # match if the caller has actually surfaced the name via
            # `from scitex_clew import <attr>` (see `_collect_aliases`).
            return True
    return False


def _collect_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Walk imports and return (module_aliases, from_imported_names).

    module_aliases: names that bind to the ``scitex_clew`` module.
        Always contains ``"clew"`` and ``"scitex_clew"`` because those
        are the canonical conventions.
    from_imported_names: set of attribute names lifted by
        ``from scitex_clew import <name>``; only these will be matched
        bare (so an unrelated local ``list_claims`` helper doesn't
        trigger).
    """
    module_aliases: set[str] = {"clew", "scitex_clew"}
    from_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "scitex_clew":
                    if alias.asname:
                        module_aliases.add(alias.asname)
                    else:
                        module_aliases.add("scitex_clew")
        elif isinstance(node, ast.ImportFrom) and node.module == "scitex_clew":
            for alias in node.names:
                from_imports.add(alias.asname or alias.name)
    return module_aliases, from_imports


def _count_clew_method_calls(
    tree: ast.AST,
    attr: str,
    module_aliases: set[str],
    from_imports: set[str],
) -> int:
    """Count direct ``<clew-module-alias>.attr(...)`` calls plus bare
    ``attr(...)`` calls where ``attr`` was imported from scitex_clew.
    """
    n = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == attr:
            chain = _attr_chain(func.value)
            if chain in module_aliases:
                n += 1
        elif isinstance(func, ast.Name) and func.id == attr:
            # Bare call — only count if it's a from-imported clew name.
            if attr in from_imports:
                n += 1
    return n


# ---------------------------------------------------------------------------
# claims.json terminus detection (PS-AGENT-001)
# ---------------------------------------------------------------------------


def _string_arg_contains(arg: ast.AST, needle: str) -> bool:
    """Return True if ``arg`` is a constant string (or simple f-string
    template) whose concatenated literal-segments contain ``needle``."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return needle in arg.value
    if isinstance(arg, ast.JoinedStr):
        text = ""
        for part in arg.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                text += part.value
        return needle in text
    return False


def _writes_claims_json(tree: ast.AST) -> bool:
    """Detect any of the canonical claims.json terminus writes:

      1. ``Path(<...>).write_text(<...>)`` where the Path() arg's
         literal content contains ``claims.json``.
      2. ``<path-expr>.write_text(<...>)`` where the receiver expr
         contains the literal substring ``claims.json`` somewhere in
         its constants (so ``claims_json.write_text(...)`` qualifies
         iff ``claims_json`` is bound to a value containing that
         literal).
      3. ``stx.io.save(<obj>, "...claims.json")`` (or any module that
         routes to ``io.save`` with that suffix in the first OR second
         positional arg, since save() signatures vary).
      4. ``CONFIG.PATH.CLAIMS_JSON`` reads — strong signal the file
         knows the convention path. We treat any expression that
         attribute-chains through ``CLAIMS_JSON`` as a positive (the
         skill page docs anchor every claims.json access on that key).
      5. ``json.dump(<obj>, open("...claims.json", "w"))`` —
         tolerated because the file CONTAINS the literal somewhere.

    To keep false-positives low we also accept the literal
    ``"claims.json"`` appearing anywhere on the same line as
    ``write_text(`` or ``stx.io.save(`` — captured by walking
    Call.args/keywords for any string constant containing the
    substring.
    """
    has_claims_literal_anywhere = False
    has_write_or_save = False
    uses_claims_json_path_key = False

    for node in ast.walk(tree):
        # CONFIG.PATH.CLAIMS_JSON attribute access — strong path-key
        # signal (the skill convention).
        if isinstance(node, ast.Attribute) and node.attr == "CLAIMS_JSON":
            uses_claims_json_path_key = True

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "claims.json" in node.value:
                has_claims_literal_anywhere = True

        if isinstance(node, ast.Call):
            func = node.func
            # write_text(...)  on any receiver
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "write_text"
            ):
                has_write_or_save = True
                # Receiver-level claims.json literal? (e.g.
                # Path("data/results/claims.json").write_text(...))
                for sub in ast.walk(func.value):
                    if (
                        isinstance(sub, ast.Constant)
                        and isinstance(sub.value, str)
                        and "claims.json" in sub.value
                    ):
                        return True
                for a in list(node.args) + [kw.value for kw in node.keywords]:
                    if _string_arg_contains(a, "claims.json"):
                        return True

            # stx.io.save(obj, "...claims.json") — match any save()
            # call whose function chain ends with `.save`.
            if isinstance(func, ast.Attribute) and func.attr == "save":
                has_write_or_save = True
                for a in list(node.args) + [kw.value for kw in node.keywords]:
                    if _string_arg_contains(a, "claims.json"):
                        return True

            # json.dump(..., open("...claims.json", ...))
            if isinstance(func, ast.Attribute) and func.attr in {"dump", "dumps"}:
                for a in list(node.args) + [kw.value for kw in node.keywords]:
                    for sub in ast.walk(a):
                        if (
                            isinstance(sub, ast.Constant)
                            and isinstance(sub.value, str)
                            and "claims.json" in sub.value
                        ):
                            has_write_or_save = True

    # Best signal of a real terminus: a write_text/save call AND the
    # CONFIG.PATH.CLAIMS_JSON convention key. Either alone is enough,
    # but combine for low false-positive rate.
    if has_write_or_save and (has_claims_literal_anywhere or uses_claims_json_path_key):
        return True
    return False


# ---------------------------------------------------------------------------
# File iteration
# ---------------------------------------------------------------------------


_SKIP_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "build",
        "dist",
        "GITIGNORED",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
    }
)


def _iter_python_files(repo: Path) -> Iterable[Path]:
    for p in repo.rglob("*.py"):
        parts = set(p.parts)
        if parts & _SKIP_PARTS:
            continue
        if any(
            x.startswith(".bloat-bak-")
            or x.endswith(".bak")
            or x.endswith("-bak")
            or ".bloat-bak-" in x
            for x in p.parts
        ):
            continue
        yield p


def _iter_agent_scripts(repo: Path) -> Iterable[Path]:
    """Match ``scripts/agent/*.py`` (and ``scripts/agent/**/*.py`` for
    nested agent script trees seen in cohort scaffolding).

    A research project's agent stage scripts live under
    ``scripts/agent/`` by convention (per the
    ``02_research-project_*`` skill family). For the cohort scaffolds
    that live deep under ``scripts/cohorts/.../<capsule>/scripts/agent/``,
    we also match the substring ``/scripts/agent/`` anywhere in the
    path.
    """
    for p in _iter_python_files(repo):
        parts = p.parts
        for i in range(len(parts) - 2):
            if parts[i] == "scripts" and parts[i + 1] == "agent":
                yield p
                break


# ---------------------------------------------------------------------------
# Rule entry points
# ---------------------------------------------------------------------------


def _parse(text: str) -> ast.AST | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def check_ps_clew_001_add_claim_without_self_verify(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """PS-CLEW-001 — add_claim called but neither verify_claim nor
    list_claims called in the same module.

    Walks every ``*.py`` under the repo (skipping vendored / cache
    directories). Limitation: only direct clew API calls are
    detected; calls indirected through helper modules are intentional
    false-negatives (see module docstring).
    """
    for py in _iter_python_files(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "add_claim" not in text:
            # Cheap pre-filter — skip the bulk of the codebase.
            continue
        tree = _parse(text)
        if tree is None:
            continue
        module_aliases, from_imports = _collect_aliases(tree)
        n_add = _count_clew_method_calls(
            tree, "add_claim", module_aliases, from_imports
        )
        if n_add == 0:
            continue
        n_verify = _count_clew_method_calls(
            tree, "verify_claim", module_aliases, from_imports
        )
        n_list = _count_clew_method_calls(
            tree, "list_claims", module_aliases, from_imports
        )
        if n_verify + n_list > 0:
            continue
        # Find the first add_claim call's line for a precise location.
        line_no = 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_clew_call(
                node, "add_claim", clew_aliases=module_aliases | from_imports
            ):
                line_no = getattr(node, "lineno", 1)
                break
        out.append(
            violation_cls(
                "PS-CLEW-001",
                f"{py}:{line_no}",
                (
                    f"calls `clew.add_claim(...)` {n_add} time(s) but "
                    "never calls `clew.verify_claim(...)` or "
                    "`clew.list_claims(...)` in the same module. "
                    "Without a post-loop self-verify the agent "
                    "declares SUCCESS even when the chain of evidence "
                    "(source_file SHA-256) is silently broken. "
                    "Fix-hint: after all add_claim() calls, add a "
                    "self-verify block, e.g. "
                    "`for c in registered: result = "
                    "clew.verify_claim(c.claim_id); assert "
                    "result['source_verified']`. See "
                    "paper-scitex-clew commit 87a0f7b for the "
                    "canonical pattern and the operator directive "
                    "2026-06-01."
                ),
            )
        )


def check_ps_agent_001_agent_script_no_claims_json(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """PS-AGENT-001 — agent script calls add_claim but does not write
    a real ``data/results/claims.json`` file via ``Path.write_text``
    or ``stx.io.save``.

    Scope: ``scripts/agent/*.py`` (and nested cohort-scaffold agent
    scripts). The DAG terminus convention is from the
    research-project skill family.
    """
    for py in _iter_agent_scripts(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "add_claim" not in text:
            continue
        tree = _parse(text)
        if tree is None:
            continue
        module_aliases, from_imports = _collect_aliases(tree)
        n_add = _count_clew_method_calls(
            tree, "add_claim", module_aliases, from_imports
        )
        if n_add == 0:
            continue
        if _writes_claims_json(tree):
            continue
        # Pinpoint the first add_claim call.
        line_no = 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_clew_call(
                node, "add_claim", clew_aliases=module_aliases | from_imports
            ):
                line_no = getattr(node, "lineno", 1)
                break
        out.append(
            violation_cls(
                "PS-AGENT-001",
                f"{py}:{line_no}",
                (
                    f"agent script calls `clew.add_claim(...)` "
                    f"{n_add} time(s) but does not write a real "
                    "`data/results/claims.json` file (neither "
                    "`Path(...).write_text(...)` nor "
                    "`stx.io.save(..., '...claims.json')`). The DAG "
                    "terminus MUST be a real file — the launcher's "
                    "verifier reads `data/results/claims.json` to "
                    "score the run. Without it the run is unscored. "
                    "Fix-hint: after all add_claim() calls, persist "
                    "the canonical claims.json, e.g. "
                    "`Path(eval(CONFIG.PATH.CLAIMS_JSON))"
                    ".write_text(json.dumps(payload, indent=2))` or "
                    "`stx.io.save(payload, eval(CONFIG.PATH."
                    "CLAIMS_JSON))`."
                ),
            )
        )
