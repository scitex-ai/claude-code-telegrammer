---
description: |
  [TOPIC] Version Control Management
  [DETAILS] Core version-control workflow across the SciTeX ecosystem — branch model (`main` stable + `develop` integration + `feature/*`), semver tagging and `vX.Y.Z` annotated tags, ecosystem release waves (upstream packages published before downstream consumers), release gates (tests + audits + docs build green, no dirty working tree, version bumped in pyproject.toml and `__init__.__version__`), and conflict-resolution policy for multi-repo feature branches. Use when cutting a release, auditing branch hygiene, or planning a cross-package version bump.
tags: [scitex-general-development-version-control]
---

# SciTeX Version Management (Core Workflow)

For automation commands and ecosystem-sync CLI details, see the companion skill [05_development/03_release-automation.md](03_release-automation.md).

## Version Management Levels

| Level | Scope | Actions | When |
|-------|-------|---------|------|
| 1 | **Local** | Edit `pyproject.toml` → commit → `git tag vX.Y.Z` → push | Every release |
| 2 | **GitHub Release** | Level 1 + `gh release create vX.Y.Z --generate-notes` | Every release |
| 3 | **PyPI** | Level 2 + verify `publish-pypi.yml` triggered (or manual twine) | Public packages |
| 4 | **Hosts** | Level 3 + `scitex dev versions sync --confirm` (NAS, Spartan) | Multi-host packages |
| 5 | **Skills** | Level 4 + `scitex-dev skills export` (stamps MANIFEST.md version) | Packages with `_skills/` |

Pick the highest applicable level. Most packages need Level 4. Packages with `_skills/` directories need Level 5.

**PyPI first-publish caveat**: The first publish requires a manual workflow run with twine to register the project on PyPI. Only after that can you configure the trusted publisher (OIDC) on pypi.org. Subsequent releases are automatic via `publish-pypi.yml`.

## How to Present Choices

When invoked via `/scitex-versions`, investigate current state and present like:

```
Current: scitex-dev v0.4.0
  pyproject.toml: 0.4.0 | tag: v0.4.0 | release: v0.4.0 | PyPI: 0.4.0 | NAS: 0.4.0

Recommendation: Level 4 (Hosts)

  1. Local only
  2. + GitHub Release
  3. + PyPI
  4. + Host sync       <-- recommended
  5. + Skills export
```

Speak the recommendation and numbered choices. Wait for user to select a number, then execute that level.

## Preflight: respect the working tree

Before any `ecosystem pull` / `install` / `checkout` (or release-cut
step below), check **each target package's** state. Two conditions
can swallow work or hide regressions:

### 1. Uncommitted local changes

```bash
git -C ~/proj/<pkg> status --porcelain
```

If non-empty, decide per file:

- **Commit** — real work (e.g. a doc revision, a source fix). Stage
  the intentional files only; do not `git add -A` blindly.
- **Stash** — transient experiment you'll come back to. Use a named
  stash (`git stash push -m "<reason>" -- <paths>`).
- **Discard / gitignore** — runtime artefacts (e.g.
  `.scitex/<pkg-short>/runtime/*.sqlite`, build caches). These
  belong in `.gitignore`, not in a stash; if you see them dirty
  repeatedly, fix the ignore pattern.

`ecosystem pull` will fail noisily on dirty trees — that's the
desired behaviour. Do not silence it with `--force` flags.

### 2. Not on `develop`

```bash
git -C ~/proj/<pkg> rev-parse --abbrev-ref HEAD
```

If the current branch isn't `develop`:

- **Feature branch with unmerged work** — finish or abandon
  intentionally; do **not** `ecosystem checkout develop` until the
  branch is reconciled. A pending feature branch with `↑N` commits
  ahead of develop is real work in flight.
- **Feature branch already merged into develop** — delete it:
  ```bash
  git -C ~/proj/<pkg> branch -d <branch>           # local
  git -C ~/proj/<pkg> push origin --delete <branch> # remote
  ```
  Then `git checkout develop` and proceed.
- **Detached HEAD / stale tag checkout** — `git checkout develop`
  first; investigate why HEAD wasn't at a branch tip.

### 3. Upstream tracking

```bash
git -C ~/proj/<pkg> branch -vv | head -5
```

Verify each tracked branch's upstream points at `origin/<branch>`,
not a stale fork or local mirror. A misconfigured upstream
(`scitex/develop` localhost-Gitea instead of `origin/develop`)
produces phantom `↑N` / `↓N` counts and breaks `ecosystem dashboard`.
Fix with:

```bash
git -C ~/proj/<pkg> branch --set-upstream-to=origin/develop develop
```

After preflight, the rest of this skill (and the `/update-scitex`
command) assumes every target is on `develop`, clean, and tracking
the right remote.

## Pre-Push CI Check

**Before pushing any release, check GitHub Actions for failures:**

```bash
gh run list -R ywatanabe1989/PACKAGE --limit 5
gh run view RUN_ID -R ywatanabe1989/PACKAGE
```

If CI is failing, fix the issue before bumping version.

## Ecosystem Roster

Run `scitex-dev ecosystem list` for the authoritative current roster (39+ packages). Do not maintain a hand-list here — it drifts immediately.

## Should We Increment?

Before bumping, check what changed since last tag:

```bash
git -C ~/proj/PACKAGE log $(git -C ~/proj/PACKAGE describe --tags --abbrev=0)..HEAD --oneline
```

**Increment if**: new commits exist since last tag that change behavior, API, or dependencies.
**Skip if**: only docs, skills, or CI changes (unless you want a release for those).

### Minor vs Patch

| Bump | When |
|------|------|
| **Patch** (Z) | Bug fixes, small improvements, dependency updates |
| **Minor** (Y) | New features, new CLI commands, new API functions |
| **Major** (X) | Breaking changes — only when user explicitly requests |

Auto-determine from `git log`: if any commit starts with `feat:` → minor. Otherwise → patch.

### Also: did consumers grow a new minimum?

If your bump exposes a new API that downstream/middle/upstream packages
already use, those packages' `pyproject.toml` lower bounds must be raised
in the same wave. See [08 § When YOU update a package, bump minima in
consumers](../01_ecosystem/02_dependency-and-version-pinning.md#when-you-update-a-package-bump-minima-in-consumers).

Quick check:

```bash
# Which scitex packages import the one you just bumped?
grep -r "^from scitex_io\|^import scitex_io" ~/proj/scitex-*/src \
    | cut -d/ -f5 | sort -u
```

Each hit is a potential minimum-bump candidate — inspect its
`pyproject.toml` to decide if the bound needs to move.

## Version Increment (Core Workflow)

Format: `vX.Y.Z` (X=Major, Y=Minor, Z=Patch, may have -alpha/-beta suffix).

```bash
# 1. Edit pyproject.toml: version = "X.Y.Z"
# 2. Commit and tag
git add pyproject.toml
git commit -m "chore: bump version to X.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin develop --tags
# 3. Sync — see 05_development/03_release-automation.md for commands
```

## When to merge `develop` → `main`

**Canonical rule: `main` = the latest tagged release.** `main` is what
casual visitors see on GitHub; `develop` is where active work
integrates. We keep these in sync via a single trigger:

> **Tag push on `develop` automatically fast-forwards `main` to the tag.**

The mechanism is a small GitHub Action workflow at
`.github/workflows/sync-main.yml` that listens on `push: tags: ['v*']`
and runs `git merge --ff-only <tag>` on `main` (with a `--no-ff` merge
commit as fallback for non-linear histories). The bot pushes `main`
directly using `GITHUB_TOKEN` — no manual `checkout main` step needed.

### What this means in practice

| Change kind                           | Action to land it on `main`              |
|---------------------------------------|------------------------------------------|
| **Code/API/CLI/MCP change**           | Bump version, tag `vX.Y.Z`, push tag — workflow syncs `main` |
| **Skills / audit-rule rollout**       | Same: bump patch, tag `vX.Y.Z`, push tag |
| **README / docs polish (visible-on-GitHub change)** | Same — patch bump with `docs:` commit prefix is honest signaling |
| **In-flight refactor / WIP**          | Stay on `develop` — no tag yet           |

The patch-bump-for-docs idiom is intentional: any change that should be
visible on the GitHub landing page is a "release" of sorts (the README
is part of what users see when deciding whether to install). Tag it.

### Reference workflow

```yaml
# .github/workflows/sync-main.yml
name: Sync main with release tag
on:
  push:
    tags: ['v*']
jobs:
  ff-main:
    runs-on: ubuntu-latest
    permissions: { contents: write }
    steps:
      - uses: actions/checkout@v4
        with: { ref: main, fetch-depth: 0, token: '${{ secrets.GITHUB_TOKEN }}' }
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          TAG="${{ github.ref_name }}"
          git fetch origin --tags
          git merge --ff-only "$TAG" || git merge --no-ff "$TAG" -m "merge: sync main with $TAG"
          git push origin main
```

Reference exemplars: `scitex-ssh`, `scitex-dev`.

### Manual fallback (escape hatch)

If the workflow can't run (CI down, branch protection misconfigured,
etc.):

```bash
git -C ~/proj/PACKAGE checkout main
git -C ~/proj/PACKAGE pull origin main
git -C ~/proj/PACKAGE merge --ff-only vX.Y.Z       # or --no-ff if diverged
git -C ~/proj/PACKAGE push origin main
git -C ~/proj/PACKAGE checkout develop
```

If a pre-push hook blocks direct `git push origin main`, open a PR
`develop → main` instead and merge via `gh pr merge --merge`.

## RULES: Never Sync Blind

1. **NEVER push without checking remote state first** (`diff`)
2. **NEVER pull without checking local state first** (`git status`)
3. **NEVER discard uncommitted changes without reading the diff**
4. **Always classify changes**: improvement (commit), artifact (discard), obsolete (archive)

## PyPI Trusted Publisher

```
Repository: ywatanabe1989/<package>
Workflow: publish-pypi.yml
Environment name: pypi
```

If not setup correctly,
1. Manually publish using twine
2. Instruct user to open `https://pypi.org/manage/project/<pypi-package-name>/settings/publishing/`

## Troubleshooting

### Tag not reachable from current branch

```bash
git tag -d vX.Y.Z                               # Delete local
git tag -a vX.Y.Z -m "Release vX.Y.Z" HEAD      # Retag on HEAD
git push origin vX.Y.Z --force                   # Force-push tag
```

### Merge conflicts on remote hosts

**Always read diff contents before discarding:**

```bash
scitex dev versions diff --host nas -p PACKAGE   # READ FIRST
scitex dev versions commit --host nas -p PACKAGE -m "preserve: work from NAS" --confirm
ssh nas "cd ~/proj/PACKAGE && git stash && git pull && git stash pop"
```

### Stale dist-info

```bash
ls ~/.env-3.11/lib/python3.11/site-packages/PACKAGE_NAME-*.dist-info
rm -rf ~/.env-3.11/lib/python3.11/site-packages/PACKAGE_NAME-OLD_VERSION.dist-info
```
