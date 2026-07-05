---
description: |
  [TOPIC] Full Update Deploy
  [DETAILS] Phases 3–5 of the full ecosystem update — local sync, NAS deploy (scitex-cloud special handling), verification, parallel execution strategy, and common failure modes. See 18_full-update.md for phases 1–2 (pre-flight + release).
tags: [scitex-dev-release-deploy]
---

# Full Ecosystem Update — Phases 3–5 (Deploy + Verify)

Continuation of [18_full-update.md](18_full-update.md). Phases 1–2 cover pre-flight
and release; this file covers local sync, NAS deploy, verification, parallel
execution, and failure modes.

**Goal:** Update the local dev environment to match published versions.

### 13. fix_local — Reinstall bumped packages locally

- **Python**: `from scitex_dev.fix import fix_local`
  - `fix_local(packages=["figrecipe", "scitex-dev"], confirm=True)` → `{pkg: {status, output}}`
- **CLI**: `pip install -e ~/proj/PACKAGE`
- **MCP**: `mcp__scitex__dev_ecosystem_sync_local(packages=["..."], confirm=True)`

### 14. verify_versions — Confirm local versions aligned

- **Python**: `from scitex_dev.fix import verify_versions`
  - `verify_versions(packages=None)` → `{pkg: "ok" | "mismatch: ..."}`
- **CLI**: `scitex-dev ecosystem fix-mismatches --dry-run` (should show no mismatches)
- **MCP**: `mcp__scitex__dev_ecosystem_list` (all statuses should be "ok")

All packages must show "ok" before proceeding.

---

## Phase 4: Host Sync (NAS)

**Goal:** Deploy updated packages to remote hosts.

### 15. fix_remote — [Custom] Sync packages to NAS

- **Python**: `from scitex_dev.fix import fix_remote`
  - `fix_remote(hosts=["nas"], packages=None, install=True, confirm=True)` → `{host: {pkg: {status}}}`
  - Timeout fallback: `fix_remote(hosts=["nas"], install=False, confirm=True)`
- **CLI**: `scitex-dev ecosystem sync --host nas --confirm`
- **MCP**: `mcp__scitex__dev_ecosystem_sync(hosts=["nas"], confirm=True)`

### 16. deploy_scitex_hub — [Custom] scitex-hub NAS deploy

- **Python**: `from scitex_dev.deploy import deploy_scitex_hub`
  - `deploy_scitex_hub(host="nas", branch="develop", confirm=False)` → `{host, commands, outputs, status}`
- **CLI**:
  ```bash
  ssh nas "cd ~/proj/scitex-cloud && git pull origin develop"
  ssh nas "cd ~/proj/scitex-cloud && docker compose stop"
  ssh nas "cd ~/proj/scitex-cloud && npm install && npx vite build"
  ssh nas "cd ~/proj/scitex-cloud && docker compose up -d"
  ```
- **MCP**: via `deploy_scitex_hub` Python API (planned as MCP tool)

**Important:** Stop Docker before Vite build to avoid OOM on NAS.

### 17. verify_production — [Custom] Check scitex.ai is live

- **Python**: `from scitex_dev.deploy import verify_production`
  - `verify_production(url="https://scitex.ai", timeout=10)` → `{url, status_code, status}`
- **CLI**: `curl -s -o /dev/null -w "%{http_code}" https://scitex.ai`
- **MCP**: `mcp__scitex__capture_screenshot(url="https://scitex.ai")`

---

## Phase 5: Verification

**Goal:** Confirm everything is consistent and working. Every check must PASS.

### 18. verify_versions — Final ecosystem status check

- **Python**: `from scitex_dev.fix import verify_versions`
  - `verify_versions()` → all must be `"ok"`
- **CLI**: `scitex-dev ecosystem fix-mismatches --dry-run`
- **MCP**: `mcp__scitex__dev_ecosystem_list`

### 19. check_readme — Verify READMEs reflect current codebase

For each released package, confirm README.md contains:
- Correct version number (matches pyproject.toml)
- Four Interfaces section (Python API, CLI, MCP Server, Skills)
- Installation instructions with current package name
- No stale API examples referencing removed functions

```bash
# Quick check: version in README
for repo in scitex-python figrecipe crossref-local scitex-writer scitex-dataset scitex-dev; do
  dir=~/proj/$repo
  ver=$(grep '^version' "$dir/pyproject.toml" | head -1 | sed 's/.*"\(.*\)"/\1/')
  in_readme=$(grep -c "$ver" "$dir/README.md" 2>/dev/null || echo 0)
  printf "%-20s ver=%s in_readme=%s\n" "$repo" "$ver" "$in_readme"
done
```

### 20. check_rtd — Verify Read the Docs builds

- **Python**: `from scitex_dev.rtd import check_all_rtd`
  - `check_all_rtd()` → `{pkg: {status, url, build_status}}`
- **CLI**: `scitex-dev rtd check`
- **MCP**: `mcp__scitex__docs_list`

All RTD builds must show "passing". If failing, check build logs and fix.

### 21. check_dashboard — Verify version dashboard loads

- **CLI**: `curl -s http://127.0.0.1:5000/api/versions | python3 -m json.tool | head -5`
- **MCP**: `mcp__scitex__capture_screenshot(url="http://127.0.0.1:5000/")`

Dashboard must show all packages with correct versions, no "Loading..." stuck state.

### 22. verify_production — [Custom] Visual verification

- **CLI**: `playwright-cli screenshot https://scitex.ai --viewport 1920x1080`
- **MCP**: `mcp__scitex__capture_screenshot(url="https://scitex.ai")`

Desktop + mobile viewport. Screenshot as proof.

### 23. report_summary — Generate summary table

```
Package             Old     New     PyPI    NAS     README  RTD     Status
scitex-python       2.27.0  2.27.1  ok      ok      ok      ok      PASS
figrecipe           0.28.0  0.28.1  ok      ok      ok      ok      PASS
...
```

---

## Parallel Execution Strategy

Launch one subagent per package (or batch of 2-3 small packages).
Use `GitHandlerAgent-SONNET` subagent type.
All agents must use `git -C /full/path` for git commands (hook requirement).

## Choice Presentation

When invoked via `/update-scitex-full`, present:

```
Current ecosystem state:
  Package           toml        tag         PyPI        diff   bump
  scitex-python     2.27.0      v2.27.0     2.27.0      0      skip
  figrecipe         0.28.0      v0.28.0     0.28.0      3      patch
  ...

Recommendation: Level 4 for all, Level 5 for scitex-dev

  1. Audit only (dry run)
  2. Local + GitHub Release
  3. + PyPI
  4. + Host sync          <-- recommended
  5. + Skills export
```

## Common Failure Modes

| Failure | Cause | Fix |
|---------|-------|-----|
| PyPI 403 | Trusted publisher not configured | Configure OIDC on pypi.org or `twine upload` for first publish |
| Duplicate wheel | Version already on PyPI | Bump to next patch, re-release |
| NAS OOM on Vite | Docker consuming memory | `docker compose stop` before build |
| `__init__.py` mismatch | Version not synced | `fix_init_version(path, confirm=True)` |
| Tag wrong commit | Tagged before fixing | `git tag -d vX.Y.Z && git tag -a vX.Y.Z HEAD && git push origin vX.Y.Z --force` |
| NAS conflicts | Uncommitted changes | `mcp__scitex__dev_ecosystem_diff` then commit or stash |
| NAS timeout | pip install >120s | `fix_remote(install=False)` then SSH pip manually |
