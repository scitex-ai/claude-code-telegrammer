#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex-dev wrapper around ``newb.self_explain``.

The implementation lives upstream in the standalone ``newb`` package
(https://pypi.org/project/newb/). scitex-dev's value-add is just the
ecosystem-aware distribution-name → ``_skills/<dist>/`` resolver.

See ``general/05_development/04_skills-self-explain.md`` for the concept.

Lazy-import discipline (PS-213 LAZY-EXTRA-PATTERN-OK)
----------------------------------------------------
``newb`` lives in the ``[skills]`` optional-dependencies group (NOT core)
so that bare ``pip install scitex-dev`` does not pull in
``claude-agent-sdk`` (newb's heavy transitive). Every reference to newb
in this module goes through :func:`_require_newb`, which fails with a
clear ``pip install "scitex-dev[skills]"`` hint when the extra is
missing. Module-level ``render_markdown`` is still importable from older
callers via ``__getattr__`` (PEP 562) so the public symbol survives.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def _require_newb():
    """Lazy-import ``newb`` with a structured install hint on failure.

    Returns the imported ``newb`` module. Raises ``SystemExit`` with the
    documented install-hint string referencing the ``[skills]`` extra,
    so PS-213 LAZY-EXTRA-PATTERN-OK recognises this as a permitted
    lazy-extra pattern. The hint string is INLINE (not a module-level
    constant) so the auditor's static AST walk can see it without
    resolving Name references.
    """
    try:
        import newb as _newb
    except ImportError as exc:  # pragma: no cover — tested with monkeypatched sys.modules
        raise SystemExit(
            "scitex-dev: `skills self-explain` requires the optional "
            "`[skills]` extra (provides `newb`). Install with:\n"
            '    pip install "scitex-dev[skills]"'
        ) from exc
    return _newb


def _newb_run_callable(_newb):
    """Return ``newb.test`` (>=0.18) or fall back to ``newb.run`` (<0.18).

    newb 0.18+ renamed ``run`` → ``test`` (mental model: "newbie tries").
    Older newbs still expose ``run``; new newbs may drop it.
    """
    fn = getattr(_newb, "test", None)
    if fn is None:
        fn = getattr(_newb, "run", None)
    if fn is None:
        raise SystemExit(
            "scitex-dev: installed `newb` exposes neither `test` nor `run`; "
            'upgrade with `pip install -U "scitex-dev[skills]"`.'
        )
    return fn


def __getattr__(name: str):
    """Lazy module-level ``render_markdown`` for back-compat callers.

    Older callers do ``from scitex_dev._cli.skills._self_explain import
    render_markdown``. We honour that, but only resolve newb at attribute
    access time so a bare scitex-dev install can still import this
    module.
    """
    if name == "render_markdown":
        return _require_newb().render_markdown
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _find_skills_dir(
    distribution: str,
    *,
    ecosystem: dict | None = None,
    local_path_lookup=None,
) -> Path:
    """Locate ``_skills/<distribution>/`` for a given ecosystem package.

    Resolution: ``<local_path>/src/<import_name>/_skills/<distribution>/``.

    ``ecosystem`` / ``local_path_lookup`` are test-injection hooks so
    callers can supply a synthetic registry without monkey-patching.
    """
    if ecosystem is None or local_path_lookup is None:
        from ..._ecosystem import ECOSYSTEM as _ECO, get_local_path as _gpl

        if ecosystem is None:
            ecosystem = _ECO
        if local_path_lookup is None:
            local_path_lookup = _gpl
    ECOSYSTEM = ecosystem
    get_local_path = local_path_lookup

    if distribution not in ECOSYSTEM:
        raise ValueError(
            f"Unknown distribution {distribution!r}. Known: {sorted(ECOSYSTEM)[:5]}..."
        )
    local = get_local_path(distribution)
    import_name = ECOSYSTEM[distribution]["import_name"]
    if local is None:
        raise FileNotFoundError(
            f"No local checkout for {distribution!r} "
            f"(ecosystem entry has no local_path)."
        )
    candidate = local / "src" / import_name / "_skills" / distribution
    if not candidate.is_dir():
        raise FileNotFoundError(
            f"Expected skills dir not found: {candidate}. "
            f"Has the package been laid out with _skills/<dist>/ yet?"
        )
    return candidate


def self_explain(
    distribution: str,
    *,
    model: str = "claude-haiku-4-5",
    runs_per_prompt: int = 1,
    _runner: Optional[Any] = None,
    skills_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Have an agent (mounted with only this package's skills) self-explain.

    Thin wrapper: resolves a SciTeX ecosystem distribution name to its
    ``_skills/<dist>/`` directory and delegates to :func:`newb.self_explain`.

    Parameters
    ----------
    distribution
        Ecosystem distribution name, e.g. ``"scitex-io"``.
    model
        Claude model id passed to ``claude -p --model``.
    runs_per_prompt
        How many times to ask each prompt. >1 returns lists; ==1 returns
        scalars (the common case).
    _runner
        Test seam — inject a runner with a ``.run(prompt, model=...)``
        method to bypass docker.

    Returns
    -------
    dict
        ``{"package", "what_for", "problems_solved", "quick_start",
        "when_not_to_use"[, "red_tests"]}``. The ``"package"`` field is
        populated from ``skills_dir.name``, which is the distribution
        name in the SciTeX layout (``_skills/<dist>/``).
    """
    _newb = _require_newb()
    _newb_run = _newb_run_callable(_newb)
    if skills_dir is None:
        skills_dir = _find_skills_dir(distribution)
    return _newb_run(
        skills_dir,
        model=model,
        runs_per_prompt=runs_per_prompt,
        _runner=_runner,
    )


# EOF
