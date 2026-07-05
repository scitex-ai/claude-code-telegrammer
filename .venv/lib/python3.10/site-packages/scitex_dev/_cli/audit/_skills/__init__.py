"""Skills auditor — checks a SciTeX package's `_skills/<pip-name>/` against the
`general/03_interface/04_skills/12_quality-checklist.md` rules.

Foundation scope: static filesystem + frontmatter checks across §1 (layout),
§2 (naming), §2a (no header/footer above frontmatter), §3 (SKILL.md as index),
§4 (size limits), §6 (no `import scitex as stx`), and FM (frontmatter
required fields).

Resolution order for the package under audit:
    1. `--package` / positional argument names the *distribution* (e.g. `scitex-io`).
    2. We resolve the *import name* via `_discovery._resolve_distribution`.
    3. We probe `<pkg>/_skills/<pip-name>/` under the installed package dir.
"""

from __future__ import annotations

__all__ = ["audit_skills", "Violation", "RULES"]

from ._audit import RULES, Violation, audit_skills
