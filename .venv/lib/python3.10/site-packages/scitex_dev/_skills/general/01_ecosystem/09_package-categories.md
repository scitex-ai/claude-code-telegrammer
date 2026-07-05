---
description: |
  [TOPIC] Package categories declared in pyproject.toml.
  [DETAILS] Every SciTeX package self-declares a category under
  `[tool.scitex_dev] category = "..."`. The audit applies category-specific
  rules (workflow presence, smoke/e2e expectations) so adjustments happen
  via category, not per-rule opt-outs. Defaults to `library` when omitted.
tags: [scitex-general-ecosystem-package-categories]
---

# Package Categories (SciTeX)

## Why categories

Different SciTeX packages have different shapes — a public API library
(`scitex-io`), a CLI-first tool (`scitex-agent-container`), a tooling /
infrastructure package (`scitex-dev`). The audit can't treat them
identically: a `library` doesn't need runtime CLI smoke workflows; a
`cli-tool` does. Rather than scattering per-rule opt-outs (`no_cli`,
`no_e2e`, …), each package self-declares its category and the audit
applies the right ruleset.

## Declaration

In `pyproject.toml`:

```toml
[tool.scitex_dev]
category = "library"      # or "cli-tool" or "infrastructure"
```

When the key is missing, the audit defaults to `library`. Unknown values
also fall back to `library` (so a typo doesn't silently disable rules).

## Recognised categories

| Category         | Examples                              | Audit behaviour                                                                            |
|------------------|---------------------------------------|--------------------------------------------------------------------------------------------|
| `library`        | scitex-io, scitex-plt, scitex-stats   | Default. Baseline workflows only. Smoke / e2e layers not required (PS-211 / PS-212 skip).  |
| `cli-tool`       | scitex-agent-container                | Baseline + `sdk-runtime-smoke` workflow. Smoke + e2e layers required (PS-211 / PS-212).    |
| `infrastructure` | scitex-dev                            | Baseline workflows. Same surface as `library` for now; held as a separate name for future. |

## Required workflows per category

Audited by PS-165. See `02_package/07b_workflow-presence.md` for the
full per-category matrix.

All categories require:

- `cla.yml`
- `pytest-*-on-*.yml`
- `import-smoke-*-on-*.yml`
- `pypi-publish-*-on-tag.yml`
- `scitex-dev-quality-audit-on-*.yml`
- `sync-main-to-release-tag-on-push.yml`
- `rtd-sphinx-build-on-*.yml` *(only if `docs/` ships)*

`cli-tool` additionally requires:

- `sdk-runtime-smoke-on-*.yml` (or `cli-smoke-on-*.yml`) — runtime CLI
  exercised end-to-end on the installed wheel.

## Relation to the ecosystem registry

`scitex_dev._ecosystem._core.ECOSYSTEM` also carries a `category` field
(`umbrella`, `library`, `external-lib`, `template`, `dataset`, …) used
by the orchestrator for things like skip lists. The `[tool.scitex_dev]
category` declared in `pyproject.toml` is the *package's own* statement
about what kind of project it is, and is the source of truth for
PS-165 (workflow presence). The two should agree for in-ecosystem
packages, but the in-repo declaration wins for the audit so a new
package can self-bootstrap before the orchestrator registry is updated.
