"""Project-structure auditor — engine + rules.

Mirrors the shape of `_cli_audit_api` and `_cli_audit_skills`. Public names:

* `RULES` — dict[code, Rule]
* `Rule` — dataclass(code, section, message)
* `Violation` — dataclass(rule, where, detail)
* `audit_project(repo: Path, *, ...) -> int` — entry point used by the CLI
"""

from ._audit import RULES, Rule, Violation, audit_project

__all__ = ["RULES", "Rule", "Violation", "audit_project"]
