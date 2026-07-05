---
description: |
  [TOPIC] Scitex Readthedocs
  [DETAILS] How to onboard, configure and verify Read the Docs projects for SciTeX ecosystem packages — covers token loading, project import, default-branch handling, build triggering and bulk operations.
tags: [scitex-general-docs-rtd]
---

# Read the Docs — SciTeX ecosystem playbook

API-first: every meaningful RTD action has a v3 endpoint. **Avoid the web UI**
for anything that loops over projects — it does not scale and the form
sometimes rotates state. Browser automation is brittle for the same reason.

API base: `https://app.readthedocs.org/api/v3/` (the historical
`readthedocs.org/api/v3/` host still answers but `app.` is canonical).

## Token

```bash
source /home/ywatanabe/.bash.d/secrets/000_ENV_READ_THE_DOCS.src
# Exports READ_THE_DOCS_TOKEN and the alias RTD_TOKEN.
```

Generate / rotate at <https://app.readthedocs.org/accounts/tokens/>.
Never hard-code the token in scripts; always source the env file.

Smoke test:

```bash
curl -sS https://app.readthedocs.org/api/v3/projects/?limit=1 \
  -H "Authorization: Token $RTD_TOKEN" | jq '.count'
```

## Import a single project

```bash
curl -sS -X POST https://app.readthedocs.org/api/v3/projects/ \
  -H "Authorization: Token $RTD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "scitex-FOO",
    "repository": {
      "url": "https://github.com/ywatanabe1989/scitex-FOO",
      "type": "git"
    },
    "homepage": "https://github.com/ywatanabe1989/scitex-FOO",
    "programming_language": "py",
    "language": "en",
    "default_branch": "develop"
  }' | jq -r '.urls.documentation'
```

**`default_branch` matters.** SciTeX peer packages are `develop`-first; if
you omit the field RTD assumes `main` and the first build fails because
there is no `main` branch yet.

Successful response includes `slug`, `urls.documentation`, `urls.builds`.
The doc URL is `https://<slug>.readthedocs.io/en/latest/` once the first
build succeeds.

## Bulk import (the loop used for the 24-package onboarding)

```bash
RTD_TOKEN=${RTD_TOKEN:?source the env file first}
PACKAGES="scitex-A scitex-B scitex-C"          # space-separated
echo "name,status,doc_url"
for pkg in $PACKAGES; do
  resp=$(curl -sS -X POST https://app.readthedocs.org/api/v3/projects/ \
    -H "Authorization: Token $RTD_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"$pkg\",
      \"repository\": {\"url\": \"https://github.com/ywatanabe1989/$pkg\", \"type\": \"git\"},
      \"homepage\": \"https://github.com/ywatanabe1989/$pkg\",
      \"programming_language\": \"py\",
      \"language\": \"en\",
      \"default_branch\": \"develop\"
    }")
  status=$(echo "$resp" | python3 -c "import sys,json; d=json.loads(sys.stdin.read() or '{}'); print('OK' if 'slug' in d else d.get('detail','err'))")
  url=$(echo "$resp"    | python3 -c "import sys,json; d=json.loads(sys.stdin.read() or '{}'); print(d.get('urls',{}).get('documentation',''))")
  echo "$pkg,$status,$url"
done
```

CSV output is intentional — easy to pipe to `column -ts,` for review or
`tee /tmp/rtd-import.log` for an audit trail.

## Listing existing projects (always run before bulk import)

```bash
curl -sS "https://app.readthedocs.org/api/v3/projects/?limit=100" \
  -H "Authorization: Token $RTD_TOKEN" | \
  jq -r '.results[].slug' | sort
```

The API returns `409` for an existing slug. Slugs are lowercase + hyphens.

## Triggering a build

```bash
curl -sS -X POST \
  "https://app.readthedocs.org/api/v3/projects/<slug>/versions/latest/builds/" \
  -H "Authorization: Token $RTD_TOKEN"
```

The first build fires automatically once the project is imported and the
GitHub webhook is wired (RTD does this during import). Manual trigger is
only needed when you push docs config changes and want to rebuild without
making a new commit.

## Build configuration: `.readthedocs.yaml` in the repo

The API only handles project metadata. Build config lives in the repo as
`.readthedocs.yaml`. Minimum config that works for SciTeX peer packages:

```yaml
# .readthedocs.yaml
version: 2
build:
  os: ubuntu-22.04
  tools:
    python: "3.11"
sphinx:
  configuration: docs/sphinx/conf.py
python:
  install:
    - method: pip
      path: .
      extra_requirements: [docs]
```

This expects:
- `docs/sphinx/conf.py` (sphinx-rtd-theme works fine; pin in `[docs]` extra).
- `pyproject.toml` declaring a `docs` optional-dependency group.

The `develop` branch must contain this file or the first build aborts.

## Peer-dep packages (when peer deps aren't on PyPI yet)

If `pyproject.toml` lists peer packages that aren't published yet (e.g. a
sibling `scitex-decorators>=0.1.0` during a multi-package extraction),
RTD's default `pip install .` will fail at dep resolution. **Don't install
the package** — autodoc only needs to read source files.

`.readthedocs.yaml`:
```yaml
python:
  install:
    - requirements: docs/requirements.txt
```

`docs/requirements.txt` (sphinx + extensions only):
```
sphinx>=7.0
sphinx-rtd-theme>=2.0
myst-parser>=2.0
sphinx-copybutton>=0.5
sphinx-autodoc-typehints>=1.25
```

`docs/sphinx/conf.py` exposes the source path and mocks the missing peers:
```python
sys.path.insert(0, os.path.abspath("../../src"))

autodoc_mock_imports = [
    "torch", "scipy", "matplotlib",       # heavy externals (optional)
    "scitex_decorators", "scitex_gen",    # unpublished peer packages
]
```

This pattern was used to unblock `scitex-{gen,nn,dsp}` RTD builds during the
24-package onboarding (the peer deps were not yet on PyPI). After PyPI
publishing lands you can switch back to `path: .` and remove the mock list.

## Common pitfalls

- **`default_branch` mismatch.** Default RTD assumption is `main`. Override
  to `develop` on import OR change later via
  `PATCH /api/v3/projects/<slug>/` with `{"default_branch":"develop"}`.
- **404 on first build** usually means `.readthedocs.yaml` isn't on the
  branch RTD is reading. Push it first, then import.
- **The web UI's "Import a Project" wizard** is **not** equivalent to the
  API import. The wizard creates a project bound to your GitHub account's
  RTD integration, the API import creates a token-owned project. Mixing
  the two is fine but track which one made each project (the API path
  is preferred for ecosystem-wide automation).
- **Slug != name.** RTD lowercases names. `scitex-FOO` becomes the slug
  `scitex-foo`. The doc URL uses the slug.

## Verifying recent builds

```bash
curl -sS "https://app.readthedocs.org/api/v3/projects/<slug>/builds/?limit=1" \
  -H "Authorization: Token $RTD_TOKEN" | \
  jq -r '.results[0] | "\(.state) \(.success) \(.urls.build)"'
```

`state=finished success=true` means the build succeeded. `success=false`
with the build URL points to the log for investigation.
