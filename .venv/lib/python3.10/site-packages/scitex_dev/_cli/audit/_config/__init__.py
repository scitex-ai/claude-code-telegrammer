"""Project-type config — `.scitex/dev/config.yaml`.

Tells the auditor which rule families apply to a project (pip, research,
or both). Spec: GITIGNORED/RULES_FOR_SCIENTIFIC_PROJECTS.md §"Project-type
config".

Both `audit-project` and (since 0.16.1) `audit-python-apis` honour the
`audit.skip` list, so a deferred rule no longer drives the error-level exit
code that `audit-all` gates on. In addition, a `django` project-type relaxes
the no-mocks rule (PA-306) from error to warning, since Django apps
legitimately use test doubles for external services (HTTP/browser/telegram/
ssh); PA-307 (test-quality) still applies at full severity.
"""

from ._loader import (
    CAPABILITY_RULES,
    KNOWN_CAPABILITIES,
    PROJECT_TYPES,
    ProjectConfig,
    capability_for_rule,
    detect_project_types,
    load_config,
    write_config,
)

__all__ = [
    "CAPABILITY_RULES",
    "KNOWN_CAPABILITIES",
    "PROJECT_TYPES",
    "ProjectConfig",
    "capability_for_rule",
    "detect_project_types",
    "load_config",
    "write_config",
]
