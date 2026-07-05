"""Discover and load linter rule plugins via entry points."""

import logging
import os
import sys

_logger = logging.getLogger(__name__)
_cache = None


def _quiet() -> bool:
    """Return True when the fail-loud plugin-load notice is suppressed.

    Mirrors :func:`scitex_dev.linter._health._quiet` — both the
    documented ``SCITEX_DEV_LINTER_QUIET`` switch and the legacy
    ``SCITEX_DEV_NO_AUDIT_DISCLAIMER`` (used by ``audit-all`` to silence
    sub-process noise) silence the notice. An empty string / ``0`` /
    ``false`` does NOT silence.
    """
    for env in ("SCITEX_DEV_LINTER_QUIET", "SCITEX_DEV_NO_AUDIT_DISCLAIMER"):
        val = os.environ.get(env, "")
        if val and val not in ("0", "false", "False", ""):
            return True
    return False


def _remediation_hint(ep_name: str, exc: Exception) -> str:
    """Return an ACTIONABLE next-step for a plugin that failed to load.

    A plugin advertised via the ``scitex_dev.linter.plugins`` entry-point
    group but unimportable is almost always one of two cases, each with a
    different fix:

    * **Stale build / vestigial entry point.** The distribution declares
      an entry point pointing at a module the *installed* build no longer
      ships (``No module named '<pkg>._linter_plugin'``). The umbrella
      ``scitex`` package is the canonical example — it dropped
      ``scitex._linter_plugin`` in the umbrella-thinning refactor, so an
      env carrying an OLDER ``scitex`` wheel still advertises the entry
      point while the module is gone (neurovista symptom 2026-06-14). Fix:
      upgrade/reinstall that distribution so its metadata and code agree.

    * **Broken plugin module.** The module exists but raises on import
      (e.g. a circular import — figrecipe's figure-style checkers hit this
      for months). Fix: repair the plugin's import path.
    """
    if isinstance(exc, ModuleNotFoundError):
        missing = getattr(exc, "name", "") or str(exc)
        # `<pkg>._linter_plugin` missing → the entry point outlived the
        # module it points at. Name the distribution + the reinstall fix.
        if "._linter_plugin" in missing:
            dist = missing.split(".", 1)[0] or ep_name
            return (
                f"the {ep_name!r} plugin advertises module {missing!r} "
                f"which this build does NOT ship — the entry point is "
                f"STALE (the installed {dist!r} wheel is older than its "
                f"declared metadata). FIX: `pip install -U "
                f"--force-reinstall --no-deps {dist}` so its entry points "
                f"match the shipped modules. If {dist!r} intentionally no "
                f"longer provides linter rules, the stale wheel is the only "
                f"thing keeping this dead entry point alive."
            )
    # Generic import failure (circular import, ImportError, …).
    return (
        f"the {ep_name!r} plugin module raised on import — its rules / "
        f"checkers are NOT active. FIX: import `{ep_name}` (or its "
        f"`_linter_plugin`) directly and resolve the error above "
        f"(commonly a circular import)."
    )


def _iter_entry_points(group):
    """Yield entry points, compatible with Python 3.9+."""
    if sys.version_info >= (3, 10):
        from importlib.metadata import entry_points

        return entry_points(group=group)
    else:
        from importlib.metadata import entry_points

        eps = entry_points()
        return eps.get(group, [])


def load_plugins(*, entry_points_iter=None):
    """Load all registered linter plugins. Cached after first call.

    Returns dict with keys: rules, call_rules, axes_hints, checkers.

    ``entry_points_iter`` is a test-injection seam (mirrors
    ``scitex_dev._core.discovery.discover_packages``'s ``entry_points_fn``):
    a zero-arg callable returning an iterable of entry-point-shaped objects
    (each with ``.name`` + ``.load()``). The default (``None``) reads the
    real ``scitex_dev.linter.plugins`` group. When supplied, the result is
    NOT cached — so a test can drive the fail-loud path with a real fake
    entry point (one whose ``.load()`` raises ``ModuleNotFoundError``)
    without monkeypatching ``importlib.metadata`` and without polluting the
    process-lifetime cache. No mocks (PA-306).

    Pillar-0 instrumentation (#TBD): after the entry-point scan we hand
    the list of successfully-loaded plugin payloads to
    :mod:`scitex_dev.linter._health` so it can emit an L1 stderr notice
    if no IO/PA category rules registered AND scitex-io is missing.
    That makes the silent-skip path visible to the agent feedback
    surface (run_lint.sh hook) instead of going quiet.
    """
    global _cache
    injected = entry_points_iter is not None
    if _cache is not None and not injected:
        return _cache

    merged = {
        "rules": {},
        "call_rules": {},
        "axes_hints": {},
        "checkers": [],
    }
    plugin_payloads: list = []

    # Canonical entry-point group. The legacy `scitex_linter.plugins`
    # group is no longer read — all leaf packages now register under
    # the new name (the dual-registration window has closed).
    #
    # NOTE on the two distinct silent paths (fail-loud doctrine):
    #   * NO entry points declared (empty iterable below) is FINE — a venv
    #     with no plugin-providing packages legitimately runs only the
    #     engine rules. We do NOT warn for that case (the loop body never
    #     runs), so "no plugins declared" stays silent by construction.
    #   * An entry point that IS declared but fails to import is a real
    #     misconfiguration (stale wheel / broken module) — that gets the
    #     LOUD, actionable notice below. The two cases must never be
    #     conflated.
    if injected:
        _eps = entry_points_iter()
    else:
        _eps = _iter_entry_points("scitex_dev.linter.plugins")
    for ep in _eps:
        try:
            get_plugin = ep.load()
            plugin = get_plugin()
        except Exception as exc:
            # Pillar 0: fail-loud on plugin-load failure. Previously
            # this was a ``logger.debug`` (suppressed by default) which
            # hid figrecipe's circular-import-induced load failures
            # from operators for months — figure-style checkers were
            # silently dropped, lint passed false-green. Per neurovista
            # elevation 2026-06-14: surface load failures the same way
            # the visit-time fail-loud in ``checker.lint_source`` does.
            #
            # SINGLE channel: emit ONE prominent stderr line (the
            # run_lint.sh hook propagates stderr to the agent feedback
            # surface). The previous code ALSO did `_logger.warning`,
            # producing a DUPLICATE visible copy whenever logging was
            # configured (neurovista saw the bare un-actionable
            # `failed to load plugin scitex: ModuleNotFoundError ...`
            # line). The logger now records at debug level only — a quiet
            # breadcrumb for log-capture, not a second user-facing line.
            hint = _remediation_hint(ep.name, exc)
            _logger.debug(
                "linter: failed to load plugin %s: %s: %s",
                ep.name,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            if not _quiet():
                sys.stderr.write(
                    f"\033[33m[scitex-dev linter] WARNING: failed to load "
                    f"plugin {ep.name!r}: {type(exc).__name__}: {exc}\n"
                    f"  → {hint}\n"
                    f"  (set SCITEX_DEV_LINTER_QUIET=1 to suppress this "
                    f"notice.)\033[0m\n"
                )
            continue

        plugin_payloads.append(plugin)
        for rule in plugin.get("rules", []):
            merged["rules"][rule.id] = rule
        merged["call_rules"].update(plugin.get("call_rules", {}))
        merged["axes_hints"].update(plugin.get("axes_hints", {}))
        merged["checkers"].extend(plugin.get("checkers", []))

    # Injected (test) runs bypass BOTH the process cache and the L1/L2
    # health tally — the seam exists to exercise the load-failure branch in
    # isolation, not to drive the IO-plugin-missing notice (that has its own
    # dedicated tests). Return the freshly-merged payload without touching
    # module state.
    if injected:
        return merged

    # Fail-loud — emits L1 notice on stderr if no IO/PA plugins registered
    # and scitex-io is absent from the env. See _health.record_plugin_load
    # for the exact predicate and the SCITEX_DEV_LINTER_QUIET escape.
    try:
        from . import _health as _h

        _h.record_plugin_load(plugin_payloads)
    except Exception:  # pragma: no cover - health module must NEVER break loading
        _logger.debug("plugin-load health record failed", exc_info=True)

    _cache = merged
    return _cache


def reset():
    """Reset cache (for testing).

    Also resets :mod:`scitex_dev.linter._health` state so a test can
    re-trigger the L1/L2 notices in the same process. Production callers
    never invoke this — the cache is process-lifetime by design.
    """
    global _cache
    _cache = None
    try:
        from . import _health as _h

        _h.reset()
    except Exception:  # pragma: no cover
        pass
