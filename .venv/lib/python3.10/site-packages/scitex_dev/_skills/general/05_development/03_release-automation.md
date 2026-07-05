---
description: |
  [TOPIC] Version Control Release Automation
  [DETAILS] Ecosystem-wide release automation via `scitex-dev` — the `ecosystem` subcommand tree (`list`, `sync`, `sync-remote`, `fix-mismatches`, `start-dashboard`), the dashboard web UI at `http://localhost:8050` for at-a-glance version reconciliation across all scitex-* packages, the matching Python API in `scitex_dev.ecosystem`, and the MCP tools so agents can drive the same release flow. Complements `05_development/01_version-control.md` (manual workflow) with the automated path used during multi-package release waves. Use when bumping versions across the ecosystem, resolving cross-package version drift, or scripting a release.
tags: [scitex-general-development-release-automation]
---

# Version Control — Release Automation

Companion to [05_development/01_version-control.md](01_version-control.md). This skill documents the **automation commands** (CLI, MCP, Python API) that support the release workflow.

## Full Ecosystem Update

When user says "update all packages" or "full release", for each package:

1. **Check CI** — verify GitHub Actions pass (`gh run list`).
2. Check commits since last tag and classify (`feat:` → minor, `fix:` → patch).
3. Skip alpha/beta packages unless explicitly requested.
4. For each needing update: bump pyproject.toml → commit → tag → push → gh release → wait for PyPI → pip install -e → fix mismatches → sync to other hosts.
5. Use parallel subagents for independent repos.

**Key tools for the full update workflow:**

- `mcp__scitex__dev_ecosystem_list` — initial status check across all packages
- `mcp__scitex__dev_ecosystem_fix_mismatches` — auto-fix installed vs pyproject.toml mismatches after PyPI publish
- CLI equivalent: `scitex-dev ecosystem fix-mismatches --confirm`

## Dashboard

```bash
scitex-dev ecosystem list --json
scitex-dev ecosystem start-dashboard                      # Web GUI (0.0.0.0:8050)
scitex-dev ecosystem start-dashboard --background         # background process
scitex-dev ecosystem start-dashboard --host 0.0.0.0 --port 8050 --force
```

The dashboard reads `~/.scitex/dev/config.yaml` (or `<project>/.scitex/dev/config.yaml` if present — project overrides user; see `01_ecosystem/06_dot_scitex_directory.md`). Project-scope config.yaml wins when both exist.

## CLI Commands

### Read-only

```bash
scitex-dev ecosystem list                         # Packages with version status
scitex-dev ecosystem list --json                  # JSON output
scitex-dev ecosystem list -p scitex               # Specific package
scitex-dev show-stats                             # Ecosystem-wide stats (count/LOC/tests)
scitex-dev show-config                            # Show resolved dev config
scitex-dev search-docs <query>                    # Search package docs
```

### Sync

```bash
scitex-dev ecosystem sync                         # Local editable reinstall (dry-run default)
scitex-dev ecosystem sync --confirm               # Execute
scitex-dev ecosystem sync-remote --host nas       # Push to remote host over SSH
scitex-dev ecosystem sync-remote --confirm --host all
```

### Fix version mismatches

```bash
scitex-dev ecosystem fix-mismatches               # Preview
scitex-dev ecosystem fix-mismatches --confirm     # Execute
```

Aligns installed version, pyproject toml version, and git tag for every package.

### Utilities

```bash
scitex-dev doctor                                 # Check scitex-dev + dependencies
scitex-dev mcp start                              # Start MCP server for agents
scitex-dev mcp show-installation                  # Print MCP client config
scitex-dev install-tab-completion --shell bash    # Install shell tab-completion
scitex-dev print-tab-completion --shell bash      # Print completion script to stdout
scitex-dev quality audit-cli <package>            # Audit a package's CLI (warn-only)
scitex-dev quality audit-docs                     # Audit docs drift
scitex-dev quality audit-scope                    # Audit test-coverage scope
scitex-dev quality audit-lines                    # Audit per-file line limits
```

## MCP Tools

Mirror the CLI verbs; names follow `dev_<noun>_<verb>` (see `03_interface/03_mcp/SKILL.md`):

| Tool | Purpose |
|------|---------|
| `dev_ecosystem_list` | List every package with local/toml/git/PyPI version |
| `dev_ecosystem_sync` | Local editable reinstall (confirm=False for preview) |
| `dev_ecosystem_sync_remote` | Push to remote hosts over SSH |
| `dev_ecosystem_fix_mismatches` | Align installed ↔ toml ↔ git tag (confirm=False for preview) |
| `dev_quality_audit_cli` | Per-package noun-verb audit (warn-only) |
| `dev_quality_audit_docs` | Docs-drift audit |
| `dev_show_stats` | Ecosystem stats |
| `dev_show_config` | Resolved dev config |

## Python API

```python
from scitex._dev import sync_all, sync_local, sync_tags
from scitex._dev import remote_diff, remote_commit, pull_local

# Push (preview by default)
sync_all(confirm=True)                    # Parallel across hosts
sync_all(hosts=["nas"], confirm=True)     # Specific host
sync_local(confirm=True)                  # Local reinstall
sync_tags(confirm=True)                   # Push tags

# Pull (preview by default)
diffs = remote_diff()                     # Read-only
remote_commit(host="nas", confirm=True)   # Commit + push
pull_local(confirm=True)                  # Git pull all
```

## Standard Workflow

```bash
# 1. Check both sides
scitex dev versions diff                     # Remote state
scitex dev versions list                     # Version alignment
git status                                   # Local state

# 2. Triage remote changes — read diffs, classify each
scitex dev versions diff --host nas --json
scitex dev versions commit --host nas -p scitex -m "feat: work from NAS" --confirm

# 3. Pull, work, push
scitex dev versions pull --confirm
# ... do local work ...
scitex dev versions sync --confirm

# 4. Verify
scitex dev versions list
scitex dev versions diff                     # Should be clean
```

## Ecosystem-Wide Check

Run `scitex-dev ecosystem list` for the authoritative roster and current version states. Flag mismatches: toml != tag → needs tag. tag != PyPI → needs release/publish.

### Consistency Checker (scitex-dev built-in)

Detects both **version mismatches** (toml != tag != PyPI) and **code-version mismatches** (commits exist since last tag but version not bumped).

```bash
scitex-dev ecosystem fix-mismatches              # Preview mismatches
scitex-dev ecosystem fix-mismatches --confirm    # Fix them
```

Or via MCP: `mcp__scitex__dev_ecosystem_fix_mismatches`.

Python API:

```python
from scitex_dev.versions import get_mismatches, get_commits_since_tag
from scitex_dev.fix import fix_mismatches

mismatches = get_mismatches()                          # {pkg: {status, issues, ...}}
# Issues include: "N commit(s) since vX.Y.Z but version not bumped"
fix_mismatches(confirm=True)                           # Fix all (local + remote)
```

The `commits_since_tag` field in `list_versions()` output tells you how many commits exist since the last tag — if > 0 and version matches tag, a version bump is needed.

## End-to-end release flow (develop → PyPI) — **opt-in only, per release**

> 🛑 **Default: NEVER auto-release.** Pushing to develop, opening a PR,
> or merging to main does NOT authorize an agent to tag and publish to
> PyPI. PyPI uploads are one-way (yanks are visible-but-not-removable),
> so each release needs its own fresh authorization — a previous
> "ship it" does not carry over to the next version.
>
> **Authorization is per-release and must be explicit.** Acceptable
> triggers:
>
> - User says "release X.Y.Z to PyPI" or "publish 0.10.18 now".
> - User says `/loop until pypi` *in the same conversation as the work
>   being released*. A `/loop` from a previous session does not roll
>   forward.
> - User confirms a `gh pr create` step explicitly mentions PyPI as
>   the intended endpoint.
>
> **Not authorization:**
>
> - "ship it", "land it", "merge it" — these are merge requests, not
>   release requests; stop after the PR merges.
> - CI being green — green CI is a precondition, not a trigger.
> - A standing `/loop` running in the background — re-confirm if the
>   release window is more than ~1 hour from the original ask.
>
> If in doubt: stop after the GitHub release step and ask before
> pushing the `v*` tag (that tag is the trigger that PyPI cannot
> undo).
>
> **Trust boundary: `git push origin <v-tag>`, not the tag itself.**
> Local `git tag -a vX.Y.Z -m ...` is a free, reversible scratch
> action — `git tag -d` cleans it up. Nothing on PyPI fires until
> the tag is *pushed*: `publish-pypi.yml` triggers on the GitHub
> `push` event filtered by `tags: [v*]`. So drafting a tag locally
> for review is fine; the moment of authorization is the push.

**Pre-flight checklist before invoking the flow** (every box must be
true; if any is false, ship a regular dev push instead):

- [ ] User explicitly asked for a release (not "make this work" or
      "land the change" — those are merge requests, not release
      requests).
- [ ] The version bump is intentional and matches the change scope
      (patch / minor / major).
- [ ] CHANGELOG / release notes capture what shipped — drafted, not
      auto-generated boilerplate.
- [ ] Tests are green on develop, and the green run includes the
      latest commit (not a stale prior run).
- [ ] No `WIP`, `XXX`, `FIXME-blocking`, or known-broken markers in
      the diff that would trip downstream consumers.
- [ ] You can articulate, in one sentence, what would happen if this
      release contained a regression. (If the answer involves
      "everyone's CI breaks", get a second pair of eyes first.)

The full release sequence below is what `/loop until pypi` exercises
once those preconditions hold:

```bash
# 0. Confirm CI is green on develop.
gh run list --repo ywatanabe1989/<pkg> --branch develop --limit 3

# 1. Open release PR develop → main.
#    The pre-push hook in .git/hooks/pre-push BLOCKS direct pushes to
#    main, so always go via PR (do NOT use --no-verify).
gh pr create --repo ywatanabe1989/<pkg> --base main --head develop \
  --title "Release X.Y.Z — <one-line summary>" \
  --body "<changelog body — bullet points + Test plan>"

# 2. Auto-merge once required checks pass.
gh pr merge <PR#> --repo ywatanabe1989/<pkg> --merge --auto

# 3. After merge lands, tag origin/main and push the tag.
#    The publish-pypi.yml workflow triggers on `v*` tags.
git -C <repo> fetch origin main
git -C <repo> tag -a vX.Y.Z origin/main -m "vX.Y.Z — <summary>"
git -C <repo> push origin vX.Y.Z

# 4. Create the GitHub release (release notes for humans).
gh release create vX.Y.Z --repo ywatanabe1989/<pkg> \
  --title "vX.Y.Z — <summary>" \
  --notes "<release notes>"

# 5. Watch the publish workflow run.
gh run list --repo ywatanabe1989/<pkg> --workflow publish-pypi.yml --limit 1
```

Guards built into the flow:

- **Pre-push hook** (`.git/hooks/pre-push`) refuses direct pushes to
  `main`/`master`. Forces the PR path. Never bypass with `--no-verify`.
- **Branch-protection** on `main` requires CI green before merge — the
  PR-merge step waits for checks even with `--auto`.
- **PEP 610 `direct_url.json`** is read by the editable-install drift
  warning; if you forget to bump and re-tag, downstream editable
  consumers see a one-line stderr nudge on next `import <pkg>`.

## PyPI Trusted Publisher Setup (one-time per package)

First PyPI release must be a manual `twine upload` (trusted publishing cannot create a *new* project — it can only publish to an *existing* one). After that, configure the trusted publisher so tag-triggered GitHub Actions can publish without tokens.

Per-package settings URL:

```
https://pypi.org/manage/project/<pkg-name>/settings/publishing/
```

Fill in:

| Field | Value |
|---|---|
| PyPI project name | `<pkg-name>` (auto) |
| Owner | `ywatanabe1989` |
| Repository name | `<pkg-name>` |
| Workflow filename | `publish-pypi.yml` |
| Environment name | `pypi` |

**Verify it saved.** After submit, the publisher must appear under **Manage current publishers**. If that list still says "No publishers are currently configured", the save silently failed — re-enter the form. This is the most common cause of `invalid-publisher: Publisher with matching claims was not found` errors on tag push, even when PyPI shows the package existing.

If a tag already failed to publish because trusted-publishing was missing, just `gh run rerun <id>` after configuring — no retag needed.

## Gotchas across the release pipeline

These are recurring failure modes when releasing scitex-* packages. None of
them are obvious from a green local audit — keep this section handy.

### gh-CI is the ONLY trustworthy merge gate (local `audit-all` can lie)

An **editable** local `scitex-dev` install can be older than the PyPI build
pinned by a target repo's CI (e.g. CI pins `scitex-dev[cli-audit]==<latest>`
while local is two patches behind → missing audit rules like PA-306 no-mocks
or PA-307 TQ). Local `audit-all` then reports green while CI fails the same
checks.

Always verify the **gh-CI** state before merging:

```bash
gh pr checks <PR#>           # required checks on the PR
gh run list --branch develop --limit 3
```

Subagents that report "local green" should re-verify in a throwaway venv
with the CI-pinned auditor before claiming a clean state.

### `enforce_admins=true` cannot be bypassed by `gh pr merge --admin`

When a repo's `develop` (or `main`) has branch protection with
`enforce_admins: true` (socialia, str, scholar, …), even `gh pr merge --admin`
won't override a FAILING required check. The work must be genuinely complete
(CI green), not "merged anyway". If a check is wrong, fix the check or the
ruleset — don't escalate to admin-merge as a habit.

### No-retag rule — burned/stale tag → PATCH bump

If a tag push fired the publish workflow but the upload failed (e.g. the
trusted-publisher save silently dropped above, or `pytest tests/ -x` red),
**never delete and recreate the tag.** PyPI remembers the (project, version)
pair as taken even on failed uploads; a deleted-then-recreated tag is
effectively a burned slot. Re-release via a PATCH bump (`0.2.20` burned
→ `0.2.21`). Same rule for filename-level collisions (different sdist/wheel
hash for the same version).

### PyPI 400 `Duplicate filename in local headers` (hatchling)

If publishing throws

```
HTTPError: 400 Bad Request from https://upload.pypi.org/legacy/
Duplicate filename in local headers
```

this is **hatchling-specific**: `force-include` of `_sphinx_html` (or any
path already covered by the auto-discovered `packages=` setting) emits the
file twice in the wheel header table. Drop the redundant
`tool.hatch.build.targets.wheel.force-include` entry. setuptools-built
packages are not affected.

### CLA Assistant allowlist must end with `,ywatanabe1989`

Bare `bot*` blocks **maintainer-authored release PRs** because the release
flow opens the develop→main PR as a human commit, not a bot. The allowlist
must read:

```yaml
allowlist: bot*,ywatanabe1989
```

`pull_request_target` reads `cla.yml` from the **base branch (main)**, so if
the allowlist is correct on develop but stale on main the gate still fails
on the release PR. Fix on main, not develop.

### Releasing under quota pressure (parallel-publish bottleneck)

When ~N packages need releasing in the same window and the lead's Anthropic
Max account is rate-limited, **don't serialise the campaign as a "fix"** —
that just stretches the wall-clock without addressing the cause. Spread the
release work across the 3 Max accounts (lead session
`ywatanabe@scitex.ai`; campaign agents `wyusuuke@gmail.com` /
`ywata1989@gmail.com`) and stagger dispatches ~45 s apart to avoid a
first-turn spike. Distinguish:

- **429 / "out of extra usage"** → per-account; rotate the responsible
  agent to a different account.
- **529 overload** → Anthropic server-side, transient; switching accounts
  does NOT help. Wait.

These are operational notes; the structural release flow above is
unaffected.
