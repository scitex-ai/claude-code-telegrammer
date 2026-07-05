---
description: |
  [TOPIC] License And Cla
  [DETAILS] Ecosystem-wide policy for licensing (SPDX `AGPL-3.0-only`) and the Contributor License Agreement gate. Covers the AGPL-only rationale, the `cla.yml` workflow template, the strict `signatures/cla.json` shape that the CLA action requires (object with `signedContributors`, NOT a bare array), recovery from the size-3 crash, the `pull_request_target` base-branch trap, and the bootstrap + audit recipes.
tags: [scitex-general-ecosystem-license-and-cla]
---

# License and CLA (ecosystem policy)

## License: `AGPL-3.0-only`

### Why AGPL v3.0
SciTeX ships under AGPL v3.0 to enforce the [Four Freedoms](https://www.gnu.org/philosophy/free-sw.en.html) across networked deployments — closing the SaaS loophole left open by GPL.

### Why `-only`, not `-or-later`
- `-or-later` lets users redistribute under any future AGPL version (v4, v5…) — losing maintainer control over license drift.
- `-only` pins to v3.0 explicitly. Re-licensing requires a deliberate decision and contributor agreement.

### Required `pyproject.toml`

```toml
[project]
license = "AGPL-3.0-only"
```

- This is the [PEP 639](https://peps.python.org/pep-0639/) SPDX expression. Any other value triggers `REL-11_invalid_pep639_license`.
- Do **NOT** add a `License :: …` trove classifier — PEP 639 deprecated those alongside SPDX adoption. setuptools ≥80 rejects builds containing one (`E5C13_orphan_license_classifier`).

### Required `LICENSE` file
Standard AGPL-3.0 text at repo root.

## CLA (Contributor License Agreement)

All commits to `scitex-*` repos must come from **signed contributors** OR **allowlisted accounts**. The maintainer (`ywatanabe1989`) and bot accounts (`bot*`) are allowlisted; external contributors sign once via PR comment.

> **No `PERSONAL_ACCESS_TOKEN` secret is required for the allowlist path.** The action's `env: PERSONAL_ACCESS_TOKEN` line in the workflow template is allowed to resolve to an empty string. Confirmed across `scitex-core`, `scitex-io`, `scitex-app`, etc.: with the maintainer in `allowlist:`, the action sees zero unsigned committers and exits green without touching the signatures branch. PAT only becomes relevant if/when an external contributor signs via comment — that code path may need a PAT to push the signature back to `cla-signatures` and re-fire the PR check; this has not yet been exercised in this ecosystem.

### Files required in every repo

1. `CLA.md` at repo root — agreement text.
2. `CONTRIBUTING.md` at repo root — references the CLA.
3. `.github/workflows/cla.yml` — gate workflow (template below).
4. `cla-signatures` branch with `signatures/cla.json` initialized as `{"signedContributors": []}`.

### Workflow template (`.github/workflows/cla.yml`)

```yaml
name: CLA Assistant
on:
  issue_comment:
    types: [created]
  pull_request_target:
    types: [opened, closed, synchronize]
permissions:
  actions: write
  contents: write
  pull-requests: write
  statuses: write
jobs:
  CLAssistant:
    runs-on: ubuntu-latest
    steps:
      - name: CLA Assistant
        uses: contributor-assistant/github-action@v2.6.1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PERSONAL_ACCESS_TOKEN: ${{ secrets.PERSONAL_ACCESS_TOKEN }}
        with:
          path-to-signatures: "signatures/cla.json"
          path-to-document: "https://github.com/<owner>/<repo>/blob/main/CLA.md"
          branch: "cla-signatures"
          allowlist: bot*,ywatanabe1989
          custom-allsigned-prcomment: |
            Thank you for signing the SciTeX CLA. Your contribution can now be reviewed.
          custom-notsigned-prcomment: |
            Please sign the [SciTeX CLA](https://github.com/<owner>/<repo>/blob/main/CLA.md) before your contribution can be merged.
            Comment `I have read and agree to the SciTeX CLA.` to sign.
```

### `signatures/cla.json` shape — **CRITICAL**

The file MUST be a JSON **object** with a `signedContributors` array, NOT a bare array.

```json
{"signedContributors": []}
```

A bare-array file (`[]`) makes `contributor-assistant/github-action@v2.6.1` crash on startup with:

```
##[error]Cannot read properties of undefined (reading 'some')
```

The action runs `signatures.signedContributors.some(...)` at startup; with `[]` the `.signedContributors` key is `undefined`. Hit on **scitex-dev** and **scitex-audio** in 2026-04 — both had `[]` (size 3 bytes) instead of the object shape.

#### Repair recipe

```bash
SHA=$(gh api 'repos/<owner>/<repo>/contents/signatures/cla.json?ref=cla-signatures' --jq '.sha')
B64=$(printf '{"signedContributors": []}\n' | base64 -w0)
gh api -X PUT 'repos/<owner>/<repo>/contents/signatures/cla.json' \
  --field branch=cla-signatures \
  --field message="fix(cla): initialize signatures file as object" \
  --field content="$B64" \
  --field sha="$SHA"
```

### Gotcha: `pull_request_target` reads the workflow from the BASE branch

The CLA workflow runs on `pull_request_target`, which checks out and runs `cla.yml` **from the PR's base branch**, not the head. So if you update `cla.yml` (e.g. add yourself to `allowlist:`) in a feature branch, the change does **NOT** take effect for that PR — the *old* workflow gates it. The update applies only after the PR merges to main.

**Recovery for a self-PR caught by an old gate** — *do NOT rely on the signing-comment path here* (it may silently no-op without a PAT, as observed on scitex-dev PR #16 in 2026-04). Instead, **patch the allowlist on the base branch directly**:

```bash
SHA=$(gh api 'repos/<owner>/<repo>/contents/.github/workflows/cla.yml?ref=main' --jq '.sha')
CURRENT=$(gh api 'repos/<owner>/<repo>/contents/.github/workflows/cla.yml?ref=main' --jq '.content' | base64 -d)
NEW=$(echo "$CURRENT" | sed 's/allowlist: bot\*$/allowlist: bot*,ywatanabe1989/')
B64=$(printf "%s" "$NEW" | base64 -w0)
gh api -X PUT 'repos/<owner>/<repo>/contents/.github/workflows/cla.yml' \
  --field branch=main \
  --field message="ci(cla): allowlist maintainer" \
  --field content="$B64" \
  --field sha="$SHA"
```

Then trigger a fresh evaluation by pushing any commit to the PR's head branch (the `synchronize` event re-runs `pull_request_target` with the freshly updated workflow from main).

### Bootstrapping a new `scitex-*` repo

```bash
REPO=<new-repo>
# 1. Copy CLA.md, CONTRIBUTING.md, .github/workflows/cla.yml from a sibling repo (e.g. scitex-core).
#    Confirm the workflow's `allowlist:` line includes the maintainer login (e.g. `bot*,ywatanabe1989`).
#    Without the maintainer in the allowlist, every self-PR will be CLA-gated and you'll need
#    the recovery recipe above on each PR.
# 2. Create the cla-signatures branch with the correct shape:
git -C $REPO checkout --orphan cla-signatures
git -C $REPO rm -rf .
mkdir -p $REPO/signatures
printf '{"signedContributors": []}\n' > $REPO/signatures/cla.json
git -C $REPO add signatures/cla.json
git -C $REPO commit -m "init: cla-signatures branch"
git -C $REPO push origin cla-signatures
git -C $REPO checkout develop
# 3. Open a test PR — confirm the action runs without the startup crash.
```

### Auditing ecosystem CLA health

Quick scan for repos with the broken `[]` shape:

```bash
PKGS=$(scitex-dev ecosystem list --json | python3 -c "import sys,json; print(' '.join(json.load(sys.stdin)['packages']))")
for r in $PKGS; do
  size=$(gh api "repos/ywatanabe1989/$r/contents/signatures/cla.json?ref=cla-signatures" --jq '.size' 2>/dev/null)
  if [[ "$size" =~ ^[0-9]+$ ]] && (( size < 10 )); then
    echo "BROKEN size=$size  $r"
  fi
done
```

- `size=3` → literal `[]` (broken).
- `size=25` or `26` → properly initialized empty (`{"signedContributors":[]}` ± trailing newline).
- API 404 → no `cla-signatures` branch yet (action will bootstrap on first PR; no action needed).

## Rule codes

### Existing (in `scitex_dev._pyproject_lint`)
- `REL-11_invalid_pep639_license` — pyproject `license` is not the SPDX expression `"AGPL-3.0-only"`.
- `E5C13_orphan_license_classifier` — `License :: …` trove classifier present (rejected by setuptools ≥80).

### Future (TODO, 0.9.x)
- `REL-12_missing_cla_workflow` — repo has no `.github/workflows/cla.yml`.
- `E5C14_malformed_cla_signatures` — `signatures/cla.json` on `cla-signatures` branch is not a JSON object with key `signedContributors`.
