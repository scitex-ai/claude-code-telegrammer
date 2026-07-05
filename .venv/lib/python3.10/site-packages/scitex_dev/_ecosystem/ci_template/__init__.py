"""CI-template applier — rolls canonical CI-speedup workflows to scitex-* repos.

Lives under the underscore-private ``scitex_dev._ecosystem`` namespace
because the existing public ``scitex_dev.ecosystem`` (no underscore) is
a flat re-export module, not a package. The Click wiring at
``scitex_dev._cli.ecosystem._cmds._ci_template`` imports from here.

Internal surface
----------------
``apply(repo_dir, ...) -> ApplyResult``
    Programmatic entry-point used by the Click wiring and by tests.

``emitted_job_names(python_versions)``
    Deterministic set of branch-protection-context strings the rendered
    templates publish. Lives next to ``apply`` so the gate's intent and
    the templates' content cannot drift.

``render(template_name, ...)``
    Pure substitution helper, exposed for tests.

Vendored templates live under ``ci_template/templates/``. The directory
ships as package-data via ``pyproject.toml`` so the installed wheel can
read them without a source checkout.
"""

from __future__ import annotations

from ._apply import (
    ApplyError,
    ApplyResult,
    BranchProtectionGateError,
    apply,
    emitted_job_names,
    render,
)

__all__ = [
    "apply",
    "ApplyError",
    "ApplyResult",
    "BranchProtectionGateError",
    "emitted_job_names",
    "render",
]
