"""AST-based checker that detects SciTeX anti-patterns."""

__all__ = ["Issue", "is_script", "lint_file", "lint_source"]

import ast
from dataclasses import dataclass, replace

from . import rules
from ._checks import (
    CallChecksMixin,
    ErrorHandlingMixin,
    ImportChecksMixin,
    TestQualityMixin,
    own_scitex_package,
)
from ._rules import lookup as _lk
from ._source_helpers import _is_allowed_by_comment, is_script
from .rules import Rule


@dataclass
class Issue:
    rule: Rule
    line: int
    col: int
    source_line: str = ""


class SciTeXChecker(
    ImportChecksMixin,
    CallChecksMixin,
    ErrorHandlingMixin,
    TestQualityMixin,
    ast.NodeVisitor,
):
    """AST visitor detecting non-SciTeX patterns."""

    def __init__(self, source_lines: list, filepath: str = "<stdin>", config=None):
        from .config import load_config

        self.source_lines = source_lines
        self.filepath = filepath
        self.config = config or load_config(start_path=filepath)
        self.issues: list = []
        # Package availability for rule gating
        from ._packages import detect as _detect_pkgs

        self._available = _detect_pkgs()
        # Tracking state
        self._has_stx_import = False
        self._has_main_guard = False
        self._has_session_decorator = False
        self._has_module_decorator = False
        self._session_func_returns_int = False
        self._imports: dict = {}  # alias -> full module path
        self._own_package = own_scitex_package(filepath)  # for STX-I008
        self._is_script = is_script(filepath, self.config)
        self._func_depth = 0  # >0 means inside a function body
        # STX-P010 — top-level figrecipe usage inside an @stx.session
        # module. Recorded during the visit (import + call sites) and
        # emitted in get_issues() ONCE the whole module is seen, because
        # the `import figrecipe as fr` line is visited BEFORE the
        # `@stx.session def main` further down — we can't know the module
        # is session-decorated at import-visit time. (line, col, src) tuples.
        self._figrecipe_usages: list = []
        from ._plugin_loader import load_plugins

        _plugins = load_plugins()
        # Filter plugin rules by config.enable (FM rules need opt-in)
        _enabled = set(self.config.enable) if self.config else set()
        _CAT_ENABLE = {"figure": "FM"}  # categories requiring opt-in
        self._plugin_call_rules = {
            k: r
            for k, r in _plugins["call_rules"].items()
            if r.category not in _CAT_ENABLE or _CAT_ENABLE[r.category] in _enabled
        }
        self._plugin_checkers = _plugins["checkers"]

    # -- Assignment visitors --

    def visit_Assign(self, node: ast.Assign) -> None:
        from ._naming_checker import check_assignment

        check_assignment(self, node)
        self.generic_visit(node)

    # -- Numeric-literal visitor (NL001) --

    def visit_Constant(self, node: ast.Constant) -> None:
        """Flag integer literals ≥ 1_000 written without `_` separators
        (STX-NL001 / PEP 515 — see
        `_skills/general/03_interface/01_python-api/14_numeric-literals.md`).

        Carve-outs:
        - bool / float / complex / str / bytes / None — skipped.
        - abs(value) < 1000 — under threshold.
        - source segment already contains `_` — already conformant.
        - source segment is non-decimal (`0x…`, `0o…`, `0b…`) — left
          alone; the PEP applies but the rule keeps its scope narrow.
        - `# noqa: STX-NL001` on the line — explicit suppression for
          identifiers that read as a whole (years, ports, codes).
        """
        # STX-HPC001 — SSH multiplexing disabled on the HPC path: a string
        # literal that turns off the ssh control-master / control-path opens a
        # fresh login-node connection per call (Spartan admin incident
        # 2026-06-17: 440+ connections). The match tokens are split (`"=" + "no"`)
        # so this detector's OWN source does not trip the rule.
        _hpc_nomux = ("ControlMaster=" + "no", "ControlPath=" + "none")
        if isinstance(node.value, str) and any(t in node.value for t in _hpc_nomux):
            hpc_line = (
                self.source_lines[node.lineno - 1]
                if node.lineno - 1 < len(self.source_lines)
                else ""
            )
            if not _is_allowed_by_comment(hpc_line, "STX-HPC001"):
                self._add(rules.HPC001, node.lineno, node.col_offset, hpc_line)

        # Only int literals; explicitly reject bool (`True is 1`).
        if not isinstance(node.value, int) or isinstance(node.value, bool):
            self.generic_visit(node)
            return
        if abs(node.value) < 1000:
            self.generic_visit(node)
            return
        # Need the original source segment to see if `_` was used —
        # `node.value` normalises `21_600` and `21600` to the same int.
        src = ast.get_source_segment("\n".join(self.source_lines), node)
        if src is None or "_" in src:
            self.generic_visit(node)
            return
        if src.startswith(("0x", "0o", "0b", "0X", "0O", "0B")):
            # Non-decimal — same PEP applies but the rule keeps its
            # scope narrow to base-10 quantities for now.
            self.generic_visit(node)
            return
        line = (
            self.source_lines[node.lineno - 1]
            if node.lineno - 1 < len(self.source_lines)
            else ""
        )
        if _is_allowed_by_comment(line, "STX-NL001"):
            self.generic_visit(node)
            return
        self._add(rules.NL001, node.lineno, node.col_offset, line)
        self.generic_visit(node)

    # -- Function/decorator visitors --

    @property
    def _REQUIRED_INJECTED(self):
        return set(self.config.required_injected)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # NM002 — `mocker` / `monkeypatch` fixture parameters (no exceptions).
        for arg in (
            list(node.args.args)
            + list(node.args.kwonlyargs)
            + list(getattr(node.args, "posonlyargs", []))
        ):
            if arg.arg in self._MOCK_FIXTURE_PARAMS:
                line = self._get_source(arg.lineno)
                self._add(rules.NM002, arg.lineno, arg.col_offset, line)
        # TQ001 / TQ002 / TQ003 / TQ006 / TQ007 — test-function rules
        # (gated on test files).
        if node.name.startswith("test_") and self._tq001_is_test_file():
            # TQ001 — no assertion → green-bar theater.
            assertion_count = self._tq007_count_assertions(node)
            if assertion_count == 0:
                line = self._get_source(node.lineno)
                self._add(rules.TQ001, node.lineno, node.col_offset, line)
            # TQ007 — more than one assertion in one test (when first
            # assert fails, the rest is silently skipped).
            elif assertion_count > 1:
                line = self._get_source(node.lineno)
                self._add(rules.TQ007, node.lineno, node.col_offset, line)
            # TQ002 — AAA marker comments must be present and in order.
            aaa_reason = self._tq002_missing_aaa_markers(node)
            if aaa_reason:
                line = self._get_source(node.lineno)
                self._add(rules.TQ002, node.lineno, node.col_offset, line)
            # TQ003 — test name has <3 word-tokens after `test_`.
            if self._tq003_name_word_count(node.name) < 3:
                line = self._get_source(node.lineno)
                self._add(rules.TQ003, node.lineno, node.col_offset, line)
            # TQ006 — top-level if/else inside a parametrized test.
            if self._tq_has_parametrize(node) and self._tq006_body_has_toplevel_if(
                node
            ):
                line = self._get_source(node.lineno)
                self._add(rules.TQ006, node.lineno, node.col_offset, line)

        # TQ004 / TQ005 — fixture rules (gated on test files; any function
        # with @pytest.fixture, name doesn't have to start with `test_`).
        if self._tq001_is_test_file():
            is_fixture, scope = self._tq_is_pytest_fixture(node)
            if is_fixture:
                # TQ004 — session/module scope + state-mutation body.
                if scope in {"session", "module", "package"} and (
                    self._tq004_body_mutates_state(node)
                ):
                    line = self._get_source(node.lineno)
                    self._add(rules.TQ004, node.lineno, node.col_offset, line)
                # TQ005 — resource acquisition + return-not-yield.
                if self._tq005_acquires_resource(
                    node
                ) and self._tq005_returns_not_yields(node):
                    line = self._get_source(node.lineno)
                    self._add(rules.TQ005, node.lineno, node.col_offset, line)

        if self._has_session_deco(node):
            self._has_session_decorator = True
            self._check_session_return(node)
            self._check_injected_params(node)
        elif self._has_module_deco(node):
            self._has_module_decorator = True
        self._func_depth += 1
        self.generic_visit(node)
        self._func_depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def _has_session_deco(self, node: ast.FunctionDef) -> bool:
        """Check if function has @stx.session or @session decorator."""
        for deco in node.decorator_list:
            # @stx.session
            if isinstance(deco, ast.Attribute):
                if (
                    isinstance(deco.value, ast.Name)
                    and deco.value.id in ("stx", "scitex", "scitex_io")
                    and deco.attr == "session"
                ):
                    return True
            # @session (bare)
            if isinstance(deco, ast.Name) and deco.id == "session":
                return True
        return False

    def _has_module_deco(self, node: ast.FunctionDef) -> bool:
        """Check if function has @stx.module(...) decorator."""
        for deco in node.decorator_list:
            # @stx.module(...) — Call wrapping Attribute
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute):
                if (
                    isinstance(deco.func.value, ast.Name)
                    and deco.func.value.id in ("stx", "scitex", "scitex_io")
                    and deco.func.attr == "module"
                ):
                    return True
            # @stx.module (bare, no parens)
            if isinstance(deco, ast.Attribute):
                if (
                    isinstance(deco.value, ast.Name)
                    and deco.value.id in ("stx", "scitex", "scitex_io")
                    and deco.attr == "module"
                ):
                    return True
            # @module(...) (bare call)
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Name):
                if deco.func.id == "module":
                    return True
        return False

    def _check_session_return(self, node: ast.FunctionDef) -> None:
        """Check that session function returns an int."""
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and child.value is not None:
                if isinstance(child.value, ast.Constant) and isinstance(
                    child.value.value, int
                ):
                    self._session_func_returns_int = True
                    return
        # No int return found
        line = self._get_source(node.lineno)
        self._add(_lk("STX-S004"), node.lineno, node.col_offset, line)

    def _check_injected_params(self, node: ast.FunctionDef) -> None:
        """Check that @stx.session function declares all INJECTED parameters.

        Considers positional, positional-only, AND keyword-only args — the
        injected pattern can legitimately live behind a ``*`` separator
        (e.g. ``def main(data: str, *, CONFIG=stx.session.INJECTED, ...)``).
        The previous ``args.args``-only scan missed kwonly INJECTED decls
        and produced false-positive S006s on neurovista-style scripts.

        Argument *values/annotations* are never dereferenced here — only
        the bare ``arg.arg`` name string is read. This avoids the
        ``AttributeError: 'NoneType' object has no attribute 'id'`` NPE
        the legacy ``scitex._linter_plugin`` S006 raised on annotated
        injected params (#60).
        """
        declared = {
            arg.arg
            for arg in (
                list(node.args.args)
                + list(node.args.kwonlyargs)
                + list(getattr(node.args, "posonlyargs", []))
            )
        }
        missing = sorted(self._REQUIRED_INJECTED - declared)
        if missing:
            line = self._get_source(node.lineno)
            missing_str = ", ".join(missing)
            s006 = _lk("STX-S006")
            dynamic_rule = Rule(
                id=s006.id,
                severity=s006.severity,
                category=s006.category,
                message=(
                    f"@stx.session function missing INJECTED parameters: {missing_str}. "
                    f"All 5 must be declared: CONFIG, COLORS, logger, plt, rngg"
                ),
                suggestion=s006.suggestion,
                requires=s006.requires,
            )
            self._add(dynamic_rule, node.lineno, node.col_offset, line)

    # -- Module-level checks (run after visiting entire tree) --

    def visit_If(self, node: ast.If) -> None:
        """Detect if __name__ == '__main__' guard."""
        if self._is_main_guard(node):
            self._has_main_guard = True
        self.generic_visit(node)

    def _is_main_guard(self, node: ast.If) -> bool:
        test = node.test
        if isinstance(test, ast.Compare):
            if (
                isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"
            ):
                return True
        return False

    # -- Finalization --

    def get_issues(self) -> list:
        """Return all issues, including post-visit structural checks."""
        # STX-S009 / STX-S010 — research script-organization (path/filename
        # rules). They target files UNDER a configured script dir, which
        # is_script() deliberately excludes, so they run BEFORE the is_script
        # early-return and are gated on the research project-type instead.
        org_emitted = False
        if "research" in (getattr(self.config, "project_types", None) or ()):
            from ._rules._script_organization import check_script_organization

            org_emitted = check_script_organization(self)

        if not self._is_script:
            if org_emitted:
                from .rules import SEVERITY_ORDER

                self.issues.sort(
                    key=lambda i: (-SEVERITY_ORDER[i.rule.severity], i.line)
                )
            return self.issues

        if not self._has_main_guard:
            self._add(_lk("STX-S002"), 1, 0, "")

        if self._has_main_guard and not (
            self._has_session_decorator or self._has_module_decorator
        ):
            self._add(_lk("STX-S001"), 1, 0, "")

        if self._has_main_guard and not self._has_stx_import:
            self._add(_lk("STX-S005"), 1, 0, "")

        # STX-P010 — top-level figrecipe used inside an @stx.session module.
        # Only emit when the module actually declares a session-decorated
        # main; otherwise top-level figrecipe is the *correct* API (e.g. a
        # plain plotting script or library helper) and must NOT be flagged.
        if self._has_session_decorator and self._figrecipe_usages:
            p010 = _lk("STX-P010")
            for line, col, src in self._figrecipe_usages:
                self._add(p010, line, col, src)

        # Central category-severity-override floor (figure-family v1). Plugin
        # checkers shipped by figrecipe honour only per_rule_severity and
        # ignore category_severity_override; apply it here over the combined
        # issue list (per-rule pins still WIN). See _severity_promotion.py.
        from ._severity_promotion import promote_category_severity

        self.issues = promote_category_severity(self.issues, self.config)

        # Sort: errors first, then by line
        from .rules import SEVERITY_ORDER

        self.issues.sort(key=lambda i: (-SEVERITY_ORDER[i.rule.severity], i.line))
        return self.issues

    def _add(self, rule: Rule | None, line: int, col: int, source_line: str) -> None:
        if rule is None:
            return
        if rule.requires and rule.requires not in self._available:
            # Pillar-0 fail-loud (#TBD): tally the silent-skip so the
            # health module can emit an L2 stderr summary the first
            # time the count goes non-zero. Without this the
            # `requires=` gate evaporates IO0xx coverage with zero
            # indication — exactly the 2026-06-12 ripple-wm class.
            try:
                from ._health import record_rule_skip

                record_rule_skip(rule.requires)
            except Exception:  # pragma: no cover
                pass
            return
        if rule.id in self.config.disable:
            return
        if _is_allowed_by_comment(source_line, rule.id):
            return
        sev = self.config.per_rule_severity.get(rule.id)
        if not sev:
            # Pillar 3 (#TBD) — category-wide severity override (e.g.
            # research project-type flips io/path from warning→error).
            # Per-rule override (above) still wins; category map is the
            # floor not the ceiling. See LinterConfig.
            cat_override = getattr(self.config, "category_severity_override", {}) or {}
            sev = cat_override.get(rule.category)
        if sev:
            rule = replace(rule, severity=sev)
        self.issues.append(
            Issue(rule=rule, line=line, col=col, source_line=source_line)
        )

    def _get_source(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].rstrip()
        return ""


def lint_source(
    source: str, filepath: str = "<stdin>", config=None, plugins=None
) -> list:
    """Lint Python source code and return list of Issues.

    ``plugins`` is the plugin-payload seam (defaults to ``load_plugins()``);
    tests pass a hand-rolled payload to drive the fail-loud path without
    patching the loader (PA-306: real fakes, no monkeypatch).
    """
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    lines = source.splitlines()
    checker = SciTeXChecker(lines, filepath=filepath, config=config)
    checker.visit(tree)
    if config and "FM" in config.enable:
        from ._fm_checker import FMChecker

        fm = FMChecker(lines, config)
        fm.visit(tree)
        checker.issues.extend(fm.issues)

    # Plugin-contributed checkers (respect opt-in gating)
    from ._plugin_loader import load_plugins

    payload = plugins if plugins is not None else load_plugins()
    _enabled = set(config.enable) if config else set()
    for checker_cls in payload["checkers"]:
        # Gate FM-category checkers behind config.enable=["FM"]
        cat = getattr(checker_cls, "category", None)
        if cat == "figure" and "FM" not in _enabled:
            continue
        try:
            # Pass the RESOLVED config (never None): SciTeXChecker defaults a
            # None config via load_config(), but plugin checkers deref
            # self.config.disable directly — a raw None here crashes them.
            extra = checker_cls(lines, checker.config)
            extra.visit(tree)
            checker.issues.extend(extra.issues)
        except Exception as exc:
            # Pillar 0: NEVER swallow. Surface to stderr so a dropped
            # plugin checker is visible in CI logs + interactive sessions.
            # Per neurovista elevation 2026-06-14: a silent except-pass
            # here hid figrecipe's figure-style checkers (FM P006..P011)
            # being dropped at load-time for months because of a
            # circular-import in figrecipe's plugin module. Operator
            # policy: fail-loud / no-silent-fallback.
            _name = getattr(checker_cls, "__name__", repr(checker_cls))
            import logging as _logging
            import os as _os
            import sys as _sys

            # Operator opt-out: SCITEX_DEV_LINTER_QUIET silences the WHOLE
            # fail-loud surface. Both paths can reach stderr — the logger
            # falls back to stderr (logging.lastResort / scitex-dev's own
            # "WARN:" handler) when emitting, and the explicit write feeds
            # the agent feedback hook (run_lint.sh) + interactive use.
            # Gating only the explicit write left the logger leaking the
            # message past QUIET; gate both so the off-switch is honest.
            if not _os.environ.get("SCITEX_DEV_LINTER_QUIET"):
                _logging.getLogger(__name__).warning(
                    "linter: plugin checker %s raised on visit: %s",
                    _name,
                    exc,
                )
                _sys.stderr.write(
                    f"[scitex-dev linter] WARNING: plugin checker "
                    f"{_name} raised on visit of {filepath}: "
                    f"{type(exc).__name__}: {exc}\n"
                )

    return checker.get_issues()


from ._dispatch import lint_file  # noqa: E402,F401  re-export
