"""FM (Figure/Millimeter) rule detection — opt-in category.

Detects inch-based matplotlib patterns and suggests mm-based alternatives.
Used as a second-pass AST visitor from lint_source when "FM" is enabled.
"""

import ast

from . import rules
from ._packages import detect as _detect_pkgs
from .checker import Issue


def _is_exempt_call(node):
    """Check if the call is on a stx.* or fr.* object (exempt from FM rules)."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if isinstance(func.value, ast.Name) and func.value.id in ("stx", "scitex", "fr"):
        return True
    if isinstance(func.value, ast.Attribute):
        if isinstance(func.value.value, ast.Name) and func.value.value.id in (
            "stx",
            "scitex",
            "fr",
        ):
            return True
    return False


def _has_kwarg(node, name, value=None):
    """Check if call has a specific keyword argument."""
    for kw in node.keywords:
        if kw.arg == name:
            if value is None:
                return True
            if isinstance(kw.value, ast.Constant) and kw.value.value == value:
                return True
    return False


# Suggestion variants: {rule_id: {context: suggestion}}
_SUGGESTIONS = {
    "STX-FM001": {
        "both": (
            "Use mm-based sizing: `stx.plt.subplots(axes_width_mm=40, axes_height_mm=28)` "
            "or `fr.subplots(axes_width_mm=40, axes_height_mm=28)`."
        ),
        "stx": "Use mm-based sizing: `stx.plt.subplots(axes_width_mm=40, axes_height_mm=28)`.",
        "fr": "Use mm-based sizing: `fr.subplots(axes_width_mm=40, axes_height_mm=28)`.",
    },
    "STX-FM002": {
        "both": (
            "Use mm-based margins: `stx.plt.subplots(margin_left_mm=15, margin_bottom_mm=12)` "
            "or `fr.subplots(margin_left_mm=15, margin_bottom_mm=12)`."
        ),
        "stx": "Use mm-based margins: `stx.plt.subplots(margin_left_mm=15, margin_bottom_mm=12)`.",
        "fr": "Use mm-based margins: `fr.subplots(margin_left_mm=15, margin_bottom_mm=12)`.",
    },
    "STX-FM003": {
        "both": "Use `stx.io.save(fig, './plot.png')` or `fr.save(fig, './plot.png')` for intelligent cropping.",
        "stx": "Use `stx.io.save(fig, './plot.png')` which handles cropping intelligently.",
        "fr": "Use `fr.save(fig, './plot.png')` which handles cropping intelligently.",
    },
    "STX-FM004": {
        "both": "Use mm-based layout from `stx.plt.subplots()` or `fr.subplots()` instead.",
        "stx": "Use mm-based layout from `stx.plt.subplots()` instead of constrained_layout.",
        "fr": "Use mm-based layout from `fr.subplots()` instead of constrained_layout.",
    },
    "STX-FM005": {
        "both": (
            "Use mm-based spacing: `stx.plt.subplots(space_w_mm=8, space_h_mm=10)` "
            "or `fr.subplots(space_w_mm=8, space_h_mm=10)`."
        ),
        "stx": "Use mm-based spacing: `stx.plt.subplots(space_w_mm=8, space_h_mm=10)`.",
        "fr": "Use mm-based spacing: `fr.subplots(space_w_mm=8, space_h_mm=10)`.",
    },
    "STX-FM006": {
        "both": "Use `stx.io.save(fig, './plot.png')` or `fr.save(fig, './plot.png')` for provenance tracking.",
        "stx": "Use `stx.io.save(fig, './plot.png')` for provenance tracking.",
        "fr": "Use `fr.save(fig, './plot.png')` for recipe tracking.",
    },
    "STX-FM007": {
        "both": "Use `stx.plt` style presets or `fr.load_style('SCITEX')` for consistent styling.",
        "stx": "Use `stx.plt` style presets for consistent styling.",
        "fr": "Use `fr.load_style('SCITEX')` for consistent styling.",
    },
    "STX-FM008": {
        "both": (
            "Use mm-based sizing: `stx.plt.subplots(axes_width_mm=40, axes_height_mm=28)` "
            "or `fr.subplots(axes_width_mm=40, axes_height_mm=28)`."
        ),
        "stx": "Use mm-based sizing: `stx.plt.subplots(axes_width_mm=40, axes_height_mm=28)`.",
        "fr": "Use mm-based sizing: `fr.subplots(axes_width_mm=40, axes_height_mm=28)`.",
    },
    "STX-FM009": {
        "both": (
            "Use mm-based margins: `stx.plt.subplots(margin_left_mm=15, margin_bottom_mm=12)` "
            "or `fr.subplots(margin_left_mm=15, margin_bottom_mm=12)`."
        ),
        "stx": "Use mm-based margins: `stx.plt.subplots(margin_left_mm=15, margin_bottom_mm=12)`.",
        "fr": "Use mm-based margins: `fr.subplots(margin_left_mm=15, margin_bottom_mm=12)`.",
    },
}


class FMChecker(ast.NodeVisitor):
    """AST visitor for FM (Figure/Millimeter) rules."""

    category = "figure"

    def __init__(self, source_lines, config):
        self.source_lines = source_lines
        self.config = config
        self.issues = []
        pkgs = _detect_pkgs()
        has_fr = pkgs.get("figrecipe", False)
        # Always active when FM rules enabled in config (detect patterns
        # regardless of whether figrecipe is installed)
        self._active = True
        has_stx = pkgs.get("scitex", False)
        if has_fr and has_stx:
            self._ctx = "both"
        elif has_stx:
            self._ctx = "stx"
        else:
            self._ctx = "fr"

    def _get_source(self, lineno):
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].rstrip()
        return ""

    def _add(self, rule, line, col, source_line):
        from dataclasses import replace as _replace

        # FM rules ship with the figrecipe plugin. When figrecipe isn't
        # installed in the linter's interpreter, lookup returns None.
        # Skip silently rather than crash — the rule simply isn't enforced.
        if rule is None:
            return
        if rule.id in self.config.disable:
            return
        from .checker import _is_allowed_by_comment

        if _is_allowed_by_comment(source_line, rule.id):
            return
        # Swap suggestion based on available packages
        suggestion = rule.suggestion
        variants = _SUGGESTIONS.get(rule.id)
        if variants:
            suggestion = variants.get(self._ctx, suggestion)
        rule = _replace(rule, suggestion=suggestion)
        sev = self.config.per_rule_severity.get(rule.id)
        if not sev:
            # Mirror checker.SciTeXChecker._add: category-wide severity
            # override (e.g. research project-type flips figure/plot from
            # warning→error). Per-rule override (above) still WINS; the
            # category map is the floor, not the ceiling. See LinterConfig.
            cat_override = (
                getattr(self.config, "category_severity_override", {}) or {}
            )
            sev = cat_override.get(rule.category)
        if sev:
            rule = _replace(rule, severity=sev)
        self.issues.append(
            Issue(rule=rule, line=line, col=col, source_line=source_line)
        )

    def visit_Call(self, node):
        if self._active:
            self._check_call(node)
        self.generic_visit(node)

    def visit_Assign(self, node):
        if self._active:
            self._check_assign(node)
        self.generic_visit(node)

    def _check_call(self, node):
        """Check Call nodes for FM001-FM006."""
        if _is_exempt_call(node):
            return

        func = node.func
        if not isinstance(func, ast.Attribute):
            return

        func_name = func.attr
        line = self._get_source(node.lineno)

        # FM002: tight_layout()
        if func_name == "tight_layout":
            self._add(rules.FM002, node.lineno, node.col_offset, line)
            return

        # FM005: subplots_adjust()
        if func_name == "subplots_adjust":
            self._add(rules.FM005, node.lineno, node.col_offset, line)
            return

        # FM006: savefig() + FM003: bbox_inches="tight"
        if func_name == "savefig":
            if _has_kwarg(node, "bbox_inches", "tight"):
                self._add(rules.FM003, node.lineno, node.col_offset, line)
            self._add(rules.FM006, node.lineno, node.col_offset, line)
            return

        # FM008: set_size_inches()
        if func_name == "set_size_inches":
            self._add(rules.FM008, node.lineno, node.col_offset, line)
            return

        # FM009: set_position()
        if func_name == "set_position":
            self._add(rules.FM009, node.lineno, node.col_offset, line)
            return

        # FM001: figsize= kwarg on figure()/subplots()
        # FM004: constrained_layout=True kwarg
        if func_name in ("figure", "subplots", "Figure"):
            if _has_kwarg(node, "figsize"):
                self._add(rules.FM001, node.lineno, node.col_offset, line)
            if _has_kwarg(node, "constrained_layout", True):
                self._add(rules.FM004, node.lineno, node.col_offset, line)

    def _check_assign(self, node):
        """Check Assign nodes for FM007 (rcParams modification)."""
        for target in node.targets:
            if not isinstance(target, ast.Subscript):
                continue
            val = target.value
            if not isinstance(val, ast.Attribute) or val.attr != "rcParams":
                continue
            if isinstance(val.value, ast.Name) and val.value.id in (
                "plt",
                "mpl",
                "matplotlib",
            ):
                line = self._get_source(node.lineno)
                self._add(rules.FM007, node.lineno, node.col_offset, line)
                break
