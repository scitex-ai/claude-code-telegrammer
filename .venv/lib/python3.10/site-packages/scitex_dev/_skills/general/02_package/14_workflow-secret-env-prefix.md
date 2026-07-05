---
description: |
  [TOPIC] GitHub Actions secret + env-var naming convention (per-package prefix).
  [DETAILS] Per-project secrets and env vars referenced inside
  `.github/workflows/*.yml` MUST carry a `<PKG>_` prefix where `<PKG>` is the
  package's distribution name uppercased with hyphens converted to underscores
  (e.g. `newb` → `NEWB_`, `scitex-agent-container` → `SCITEX_AGENT_CONTAINER_`).
  A short ecosystem-default exception list covers cross-cutting names that
  `scitex-dev creds rotate-all` deliberately targets (`CLAUDE_CODE_CREDENTIALS_JSON`),
  tool-pinned envs (`GH_TOKEN`, `GITHUB_TOKEN`), and third-party-named tokens
  (`CODECOV_TOKEN`, `GHCR_PAT`). A package may EXTEND that default (never
  replace it) with per-package extras under
  `[tool.scitex_dev.audit] ps168_secret_exceptions` in its `pyproject.toml`.
  Audited by PS-168.
tags: [scitex-general-package-workflow-secret-env-prefix]
---

# GitHub Actions — Per-Package Secret / Env-Var Prefix (SciTeX)

## Rule (PS-168)

Inside any `.github/workflows/*.yml`, every `${{ secrets.<NAME> }}` or
`${{ env.<NAME> }}` reference whose `<NAME>` is project-specific MUST use
the form

```
<PKG>_<UPPERCASE_NAME>
```

where `<PKG>` is the package's distribution name (the project name shown
in `pyproject.toml [project] name`) **uppercased** with hyphens replaced
by underscores. Examples:

| Package distribution         | Prefix                       | Example secret                              |
|------------------------------|------------------------------|---------------------------------------------|
| `newb`                       | `NEWB_`                      | `NEWB_CLAUDE_CODE_CREDENTIALS_JSON`         |
| `scitex-agent-container`     | `SCITEX_AGENT_CONTAINER_`    | `SCITEX_AGENT_CONTAINER_NAS_SSH_KEY`        |
| `scitex-dev`                 | `SCITEX_DEV_`                | `SCITEX_DEV_PYPI_API_TOKEN`                 |
| `socialia`                   | `SOCIALIA_`                  | `SOCIALIA_OPENAI_API_KEY`                   |

Workflow YAML usage:

```yaml
# YES — prefixed, distinguishable from cross-cutting names
env:
  CLAUDE_CODE_CREDENTIALS_JSON: ${{ secrets.NEWB_CLAUDE_CODE_CREDENTIALS_JSON }}

# NO — un-prefixed; rotate-all can't tell whether this is the shared
# ecosystem credential or a per-project copy with the same surface name
env:
  CLAUDE_CODE_CREDENTIALS_JSON: ${{ secrets.CLAUDE_CREDENTIALS_JSON }}
```

## Why

`scitex-dev creds rotate-all` rotates a fixed set of *cross-cutting*
secret names (e.g. `CLAUDE_CODE_CREDENTIALS_JSON`) across every
ecosystem package's GitHub repo. If a per-project secret picks an
un-prefixed name like `CLAUDE_CREDENTIALS_JSON`, rotate-all has no way
to know whether to overwrite it (cross-cutting?) or leave it alone
(project-specific?). The historical behaviour was to skip — silently —
which broke `newb`'s CI when its hand-rolled `CLAUDE_CREDENTIALS_JSON`
went stale while the canonically-named ecosystem secret was rotated
into freshness around it (newb PR #1, 2026-05-18).

The fix is the prefix discipline: anything starting with `<PKG>_` is
*by construction* not the rotate-all target, and the unprefixed names
in the exception list below ARE the rotate-all targets. The two sets
no longer overlap; rotate-all and per-package CI stop stepping on each
other.

## Exception list (un-prefixed names that are NOT violations)

These names are deliberately ecosystem-wide or tool-pinned and therefore
allowed without a `<PKG>_` prefix:

| Name                          | Reason                                                                     |
|-------------------------------|----------------------------------------------------------------------------|
| `CLAUDE_CODE_CREDENTIALS_JSON`| The `creds rotate-all` ecosystem-wide target.                              |
| `GH_TOKEN`                    | Honored by the `gh` CLI as the GitHub auth token (tool-pinned name).       |
| `GITHUB_TOKEN`                | Injected by GitHub Actions itself; cannot be renamed.                      |
| `CODECOV_TOKEN`               | Codecov's third-party-pinned token name.                                   |
| `GHCR_PAT`                    | GitHub Container Registry pull/push PAT — common cross-package convention. |
| `NPM_TOKEN`                   | npm publish convention.                                                    |
| `PYPI_API_TOKEN`              | Reserved name for PyPI publish (we use OIDC, but legacy workflows exist).  |
| `ACTIONS_RUNNER_DEBUG`        | GitHub Actions diagnostic toggle.                                          |
| `ACTIONS_STEP_DEBUG`          | GitHub Actions diagnostic toggle.                                          |
| `CLA_PERSONAL_ACCESS_TOKEN`   | contributor-assistant action PAT — per-action convention, same value across repos that opt into the CLA gate. |

If a future cross-cutting credential joins the rotate-all corpus, add
its bare name here and update the auditor's exception list in the same
PR.

## Per-package exceptions (pyproject extras)

The ecosystem-default list above is the right home for *cross-cutting*
names. A name that only one package legitimately needs — a one-off
legacy token, a vendor secret that genuinely can't carry the `<PKG>_`
prefix — belongs in that package's own `pyproject.toml`, not in the
central list. Declare it under `[tool.scitex_dev.audit]`:

```toml
[tool.scitex_dev.audit]
ps168_secret_exceptions = [
    "LEGACY_DEPLOY_TOKEN",   # one comment per entry explaining WHY
]
```

The auditor reads this list for the package under audit and **unions**
it with the ecosystem default — the package list *extends*, never
*replaces*, the default. A package that declares nothing still inherits
the full ecosystem default.

Why per-package instead of central:

- **Scope** — an exception is package-scoped knowledge; the package
  owns it.
- **Reviewability** — the package's PR carries both the workflow that
  uses the secret AND the exception entry; one place for the reviewer.
- **No central drift** — a one-off in one repo never pollutes the
  shared list every other package inherits.

Notes:

- The canonical TOML namespace is `[tool.scitex_dev.audit]` (underscore).
  The hyphenated `[tool.scitex-dev.audit]` is also accepted.
- A malformed `pyproject.toml`, a wrong type (anything other than a list
  of strings), or a missing section yields **no** extras — PS-168 falls
  back to the ecosystem default. A broken pyproject can never silently
  widen the allow-list.
- Non-string entries in the list are dropped silently.

## Audit (PS-168)

`PS-168` (severity `E`) scans every `.github/workflows/*.yml` under the
repo. For each `${{ secrets.<NAME> }}` reference it applies four
filters in order — the rule only fires when ALL of them say "in scope
AND non-conformant":

1. **Key-like only.** `<NAME>` must look like a credential / token —
   end of name (or word-bounded) `_TOKEN`, `_KEY`, `_SECRET`,
   `_CREDENTIAL(S)`, `_PASSWORD`, `_PAT`, `_AUTH`, `_OAUTH`. A plain
   `BUILD_NUMBER` or `DEBUG_FLAG` secret isn't subject to the
   rotation discipline PS-168 protects and would just be noise.
2. **Not in the merged exception list** — the ecosystem default above
   UNION the package's own `ps168_secret_exceptions` pyproject extras.
3. **Doesn't start with the package's own `<PKG>_` prefix.**
4. **Doesn't start with another ECOSYSTEM package's `<PKG>_` prefix.**
   Cross-package borrows are legitimate: a workflow that invokes
   another scitex package's CLI (e.g. `newb`) using its own secret
   (`NEWB_ANTHROPIC_API_KEY`) is adopting the source package's prefix
   discipline — it's not free-styling.

When all four say "violation", the auditor reports:

```
ERRO: <pkg>: [PS-168 §1 secret-env-prefix-missing] <relpath>:<lineno>:
      secret name "<NAME>" should be prefixed "<PKG>_<NAME>"
```

The same check is applied to `${{ env.<NAME> }}` references when the
right-hand side resolves to `secrets.<...>` — a workflow that stuffs a
secret through `env:` doesn't bypass the rule.

## Migration

For a package with a non-prefixed secret already in flight:

```bash
# 1. Add the prefixed secret to the GitHub repo's Settings → Secrets.
gh secret set NEWB_CLAUDE_CODE_CREDENTIALS_JSON < /path/to/creds.json

# 2. Update the workflow:
sed -i 's/secrets\.CLAUDE_CREDENTIALS_JSON/secrets.NEWB_CLAUDE_CODE_CREDENTIALS_JSON/g' \
    .github/workflows/*.yml

# 3. Delete the legacy secret.
gh secret delete CLAUDE_CREDENTIALS_JSON

# 4. Verify rotate-all now sees the package:
scitex-dev creds rotate-all --dry-run
```

## See also

- `01_ecosystem/04_environment-variables.md` — runtime env-var naming
  (this leaf's sibling for `[tool.scitex_dev] env` keys).
- `02_package/07_github-actions.md` — canonical workflow patterns.
- `02_package/12_workflows-naming.md` — workflow filename grammar (PS-164).
- `02_package/07b_workflow-presence.md` — required workflow baseline (PS-165).
