"""Central category-severity-override promotion pass (figure-family v1).

``SciTeXChecker._add`` and ``FMChecker._add`` already apply
``LinterConfig.category_severity_override`` at emit time, but the
plugin checkers shipped by **figrecipe** honour only
``per_rule_severity`` and IGNORE the category override:

- ``FigureMethodChecker`` → STX-FM010 / STX-FM011  (category ``figure``)
- ``AxisAlignmentChecker`` → STX-FIG001            (category ``figure``)
- ``StyleKwargChecker``    → STX-P006..P009         (category ``plot``)

Those modules live in figrecipe (read-only here), so we cannot fix them
at the emit site. Instead ``lint_source`` extends every checker's issues
into one list, and ``SciTeXChecker.get_issues`` calls
``promote_category_severity`` on that combined list as a final floor — so
the WHOLE figure-family v1 set (FM001-FM011 + FIG001 + P001-P009) promotes
uniformly under ``project-type: research`` regardless of which checker
emitted it.

Precedence is preserved exactly: a rule the operator pinned in
``per_rule_severity`` is left untouched (per-rule WINS over the category
floor). The ``# stx-allow: STX-<ID>`` per-line opt-out is honoured upstream
in each checker's ``_add`` / ``_emit`` (an opt-out issue never reaches here).
"""

from __future__ import annotations

from dataclasses import replace


def promote_category_severity(issues, config):
    """Return *issues* with category-severity-override applied as a floor.

    Args:
        issues: list of ``Issue`` (each carries a ``rule`` with ``category``
            and ``severity``).
        config: ``LinterConfig`` — reads ``category_severity_override`` (the
            category→severity floor) and ``per_rule_severity`` (per-rule pins
            that WIN over the floor).

    Returns:
        A new list. Issues whose rule is pinned in ``per_rule_severity`` are
        passed through unchanged; otherwise, if the rule's category has an
        override, the issue's rule severity is replaced with it.
    """
    cat_override = getattr(config, "category_severity_override", {}) or {}
    if not cat_override:
        return issues

    per_rule = getattr(config, "per_rule_severity", {}) or {}
    out = []
    for issue in issues:
        rule = issue.rule
        # Per-rule pin wins over the category floor — leave it as emitted.
        if rule.id in per_rule:
            out.append(issue)
            continue
        sev = cat_override.get(rule.category)
        if sev and sev != rule.severity:
            issue = replace(issue, rule=replace(rule, severity=sev))
        out.append(issue)
    return out


__all__ = ["promote_category_severity"]

# EOF
