"""Fail-loud diagnostics for the scitex-dev linter — Pillar 0 (#TBD).

Surfaces the two silent-skip paths that previously let a research script
with raw `pd.read_parquet` / `np.load` calls lint clean:

* **L1 — plugin discovery skipped**. If the entry-point group
  ``scitex_dev.linter.plugins`` resolves to ZERO IO / PA / ST category
  plugins, the package that provides those rules (typically
  ``scitex-io``) is not installed in the lint env. Emits a one-shot
  stderr warning at load time so the agent feedback surface (and a
  human running ``scitex-dev linter check-files`` directly) SEES it.

* **L2 — ``requires`` gate skipped**. Every IO/PA/ST rule has
  ``requires="scitex"``; when the umbrella isn't import-detectable the
  checker silently drops the rule on each file. We count the drops and
  emit a one-shot summary the first time the count goes non-zero so the
  miss can't pass silently for the whole run.

Both notices go to ``sys.stderr`` so the PostToolUse ``run_lint.sh``
hook's existing ``>&2`` convention propagates them to the agent.
``SCITEX_DEV_LINTER_QUIET=1`` suppresses both — used by the test suite
and by humans who genuinely want a silent run.

Operator context (2026-06-12 ripple-wm dogfood, lead msg
03968015919e48d9): a research script bypassing scitex.io.load/save via
``pd.read_parquet`` linted clean in two agent envs because scitex-io
was not installed — the IO003 rule never got a chance to evaluate, and
the linter said "All files clean". That silent-skip is what these
notices kill.
"""

from __future__ import annotations

import os
import sys
import threading


# Categories that signal "this is IO / path / structural coverage" — if a
# plugin registers ANY rule in one of these categories we count it for L1.
# `clew` plugin registers ``category="clew"`` which is OUT of scope (lead
# msg approved — L1 only fires for IO/PA/ST emptiness).
_IO_CATEGORIES = frozenset({"io", "path", "structure"})


# Module-state. One process-wide set of counters; reset() resets it (for
# tests). The threading lock guards the emit-once flags so two threads
# racing into ``record_rule_skip`` cannot double-emit L2.
_lock = threading.Lock()
_loaded = False
_io_rule_count = 0
_pa_rule_count = 0
_st_rule_count = 0
_skip_counts: dict[str, int] = {}
_emitted_l1 = False
_emitted_l2 = False


def _quiet() -> bool:
    """Return True when fail-loud notices are suppressed.

    Honours both ``SCITEX_DEV_LINTER_QUIET=1`` (the documented switch)
    and ``SCITEX_DEV_NO_AUDIT_DISCLAIMER=1`` (the legacy switch already
    used by ``audit-all`` to silence sub-process noise). Either one
    silences the notices; an empty string or ``0`` does NOT silence.
    """
    for env in ("SCITEX_DEV_LINTER_QUIET", "SCITEX_DEV_NO_AUDIT_DISCLAIMER"):
        val = os.environ.get(env, "")
        if val and val not in ("0", "false", "False", ""):
            return True
    return False


def _scitex_io_installed() -> bool:
    """Return True iff ``scitex_io`` is importable in the current env."""
    try:
        import importlib

        importlib.import_module("scitex_io")
        return True
    except Exception:
        return False


def record_plugin_load(plugin_results: list[dict]) -> None:
    """Record what ``_plugin_loader.load_plugins`` discovered.

    Called once at the end of ``load_plugins``. ``plugin_results`` is a
    list of the per-plugin dicts (each with a ``rules`` key — list of
    Rule objects). We tally how many IO / PA / ST category rules ended
    up registered and emit L1 if the count is zero AND scitex-io is not
    installed (so the notice points at the actual remediation).
    """
    global _loaded, _io_rule_count, _pa_rule_count, _st_rule_count
    with _lock:
        _loaded = True
        for plugin in plugin_results:
            for rule in plugin.get("rules", []):
                cat = getattr(rule, "category", "")
                if cat == "io":
                    _io_rule_count += 1
                elif cat == "path":
                    _pa_rule_count += 1
                elif cat == "structure":
                    _st_rule_count += 1
        _maybe_emit_l1()


def record_rule_skip(rule_requires: str) -> None:
    """Record a rule that was skipped via the ``requires`` gate.

    Called from ``SciTeXChecker._add`` on every drop. We aggregate by
    the ``requires`` string (typically ``"scitex"``) so the L2 message
    can name the specific missing package.
    """
    if not rule_requires:
        return
    with _lock:
        _skip_counts[rule_requires] = _skip_counts.get(rule_requires, 0) + 1
        _maybe_emit_l2()


def _maybe_emit_l1() -> None:
    """Emit the L1 notice once when conditions are met. Caller holds the lock."""
    global _emitted_l1
    if _emitted_l1 or _quiet():
        return
    io_pa = _io_rule_count + _pa_rule_count
    # Only fire when the IO/PA tier is empty AND scitex-io is the obvious
    # missing piece — avoids noise on packages that legitimately have a
    # narrower plugin set (e.g. an MCP-only leaf with no I/O concerns).
    if io_pa > 0:
        return
    if _scitex_io_installed():
        # Plugin is installed but registered 0 IO rules — that is its
        # own bug (broken get_plugin return shape) but we don't have
        # enough signal here to be certain; skip L1 to avoid false
        # positives. The structural-rule case stays covered by L2.
        return
    _emitted_l1 = True
    print(
        "\033[33m[scitex-dev linter] WARNING: no IO/PA category rules "
        "registered — scitex-io plugin is NOT installed in this venv. "
        "All `pd.read_*` / `np.load/save` / `pickle.dump/load` / "
        "`df.to_*` / `open()` checks (STX-IO001-014, STX-PA001-005) are "
        "SILENTLY skipped. Run `pip install scitex-io` to enable. Set "
        "SCITEX_DEV_LINTER_QUIET=1 to suppress this notice.\033[0m",
        file=sys.stderr,
    )


def _maybe_emit_l2() -> None:
    """Emit the L2 notice once when conditions are met. Caller holds the lock."""
    global _emitted_l2
    if _emitted_l2 or _quiet():
        return
    if not _skip_counts:
        return
    _emitted_l2 = True
    parts = []
    for req, n in sorted(_skip_counts.items()):
        parts.append(f"{n} rule(s) requiring `{req}` (not importable)")
    summary = "; ".join(parts)
    print(
        f"\033[33m[scitex-dev linter] WARNING: {summary} silently "
        "skipped via `requires=` gate. The package that provides "
        "these rules is registered but the dependency the rules check "
        "for is missing from this venv. Install the missing dep (e.g. "
        "`pip install scitex` for the umbrella) to enable them. Set "
        "SCITEX_DEV_LINTER_QUIET=1 to suppress.\033[0m",
        file=sys.stderr,
    )


def health_snapshot() -> dict:
    """Return a snapshot of linter health — used by ``linter doctor``."""
    with _lock:
        return {
            "loaded": _loaded,
            "io_rule_count": _io_rule_count,
            "pa_rule_count": _pa_rule_count,
            "st_rule_count": _st_rule_count,
            "skip_counts": dict(_skip_counts),
            "scitex_io_installed": _scitex_io_installed(),
            "emitted_l1": _emitted_l1,
            "emitted_l2": _emitted_l2,
        }


def reset() -> None:
    """Reset all module state. For tests only — production never calls this."""
    global _loaded, _io_rule_count, _pa_rule_count, _st_rule_count
    global _skip_counts, _emitted_l1, _emitted_l2
    with _lock:
        _loaded = False
        _io_rule_count = 0
        _pa_rule_count = 0
        _st_rule_count = 0
        _skip_counts = {}
        _emitted_l1 = False
        _emitted_l2 = False
