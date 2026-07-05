"""Django "apps and config" auditor — engine + rules.

Mirrors the shape of `_cli_audit_project` / `_cli_audit_api` /
`_cli_audit_skills`. Public names:

* `RULES` — dict[code, Rule]
* `Rule` — dataclass(code, section, message, severity, slug)
* `Violation` — dataclass(rule, where, detail)
* `audit_django(distribution, *, ...) -> int` — entry point used by the CLI

The checked standard is ADR 0002 (scitex-django-app-standard): Django
project in `config/`, apps under `apps/`, settings split, the
`src/scitex_<name>/` ↔ Django relationship, and `[all]`-extra deps.
`scitex-hub` is the reference implementation and passes by definition.
"""

from ._audit import RULES, Rule, Violation, audit_django

__all__ = ["RULES", "Rule", "Violation", "audit_django"]
