"""Violation dataclass for the project-structure auditor.

Split out of `_audit.py` (issue #103) — pure refactor, no behaviour change.
Re-exported from `_audit` for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._registry import RULES


@dataclass
class Violation:
    rule: str
    where: str
    detail: str

    def format(self) -> str:
        r = RULES.get(self.rule)
        section = r.section if r else "?"
        sev = r.severity if r else "W"
        slug = f" {r.slug}" if r and r.slug else ""
        return f"  [{sev}] [{self.rule} {section}{slug}] {self.where}: {self.detail}"

    @property
    def severity(self) -> str:
        r = RULES.get(self.rule)
        return r.severity if r else "W"
