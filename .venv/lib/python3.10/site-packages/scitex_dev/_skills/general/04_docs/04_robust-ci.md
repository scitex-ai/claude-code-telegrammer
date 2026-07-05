---
description: |
  [TOPIC] Robust Sphinx docs-CI
  [DETAILS] How to keep `sphinx-build -W` (warnings-as-errors) strict while
  defending against the four benign failure modes that recur across the
  ~60-package ecosystem: (1) autodoc docstring reST noise → `suppress_warnings
  = ["docutils"]` (precise category filter, real breakage still fails -W);
  (2) `_sphinx_html` commit-back to protected develop → GH006 → `continue-on-error`;
  (3) missing-peer autodoc import failure → `autodoc_mock_imports`; (4) math
  directives → `sphinx.ext.mathjax` (HTML, zero system deps — never imgmath/dvipng).
  Plus the uv install step and the canonical conf.py/workflow snippets. Use when a
  package's docs-CI fails on -W or when rolling the robust docs-CI template across
  the ecosystem. Reference implementation: scitex-seizure-metrics.
tags: [scitex-general-docs-robust-ci]
---

# Robust Sphinx docs-CI

`sphinx-build -W` (warnings-as-errors) is the correct default — it stops
broken docs from shipping. But across ~60 packages it bites on a recurring
set of *benign* failure modes that have nothing to do with broken docs.
The canonical `conf.py` + workflow defend against each WITHOUT weakening
`-W` for real breakage.

Reference implementation that survives all four modes:
`scitex-seizure-metrics/docs/sphinx/conf.py` +
`.github/workflows/rtd-sphinx-build-on-ubuntu-latest.yml` (PR #6, 2026-05).

## Mode 1 — benign docstring reST warnings (most common)

autodoc feeds free-form module/function docstrings through docutils.
A wrapped bullet whose continuation indents past the `- ` marker reads
as a nested block quote → `ERROR: Unexpected indentation` +
`WARNING: Block quote ends without a blank line`. The build *succeeds*
(`build finished with problems, N warnings`) but `-W` turns the N
warnings into a nonzero exit.

Demanding perfect reST in every docstring across the ecosystem is
unsustainable (every new docstring can reintroduce it). The defense
belongs in `conf.py`:

```python
# Suppress ONLY the docutils reST-parser rendering noise from autodoc'd
# docstrings. Scoped to the "docutils" category — real breakage
# (missing toctree pages [toc.not_readable], broken cross-refs [ref.*],
# missing math renderer, undefined directives) is emitted under OTHER
# categories and still trips `sphinx-build -W`.
suppress_warnings = ["docutils"]
```

Verified: with this set + `-W`, a deliberate broken toctree entry
(`toc.not_readable`) and a broken `:py:func:` ref STILL fail the build.
It is **NOT** "disable `-W`" — it is a precise category filter.

Authors *may* additionally clean individual docstrings so the rendered
HTML is also correct (blank line before a bullet list; flatten or
parenthesize hanging-indent continuations — do not indent a bullet's
continuation line past the `- ` marker). But the `conf.py` line is the
ecosystem-wide guarantee that a benign docstring wrap never reds a PR.

## Mode 2 — `_sphinx_html` commit-back to protected `develop` → GH006

The auto-commit step that refreshes `src/<pkg>/_sphinx_html/` on a
`develop` push can hit GH006 (protected-branch / GitHub-App push
rejection). Make that step non-fatal so a push-back failure never reds
the build:

```yaml
- name: Commit refreshed HTML if it changed (develop push only)
  continue-on-error: true        # GH006 / protected-branch → don't fail CI
  if: github.event_name == 'push' && github.ref == 'refs/heads/develop'
  run: |
    if [ -n "$(git status --porcelain src/<pkg>/_sphinx_html)" ]; then
      git config user.name "github-actions[bot]"
      git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
      git add src/<pkg>/_sphinx_html
      git commit -m "docs(sphinx_html): refresh from CI build"
      git push
    fi
```

## Mode 3 — autodoc import failure from missing peer deps

If a peer scitex-* package (or heavy optional dep) isn't installed in
the docs build, autodoc's `import` of the module fails the build. Mock
the unavailable imports rather than installing the whole world:

```python
autodoc_mock_imports = ["torch", "scipy", "scitex_decorators", "scitex_gen"]
```

Only needed while peers are unpublished; remove once `pip install .`
resolves them. See [`04_docs/03_rtd.md`](03_rtd.md) for the
RTD-side variant.

## Mode 4 — math directives need a renderer (use MathJax, no system dep)

Math (`.. math::`, myst `dollarmath`/`amsmath`, `$...$`) needs a
renderer. **Use `sphinx.ext.mathjax`** — it renders in-browser via the
MathJax CDN and requires NO system packages. Avoid `sphinx.ext.imgmath`
/ `pngmath`, which shell out to `latex` + `dvipng` (a system dep the CI
runner won't have):

```python
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.mathjax",        # math, HTML, zero system deps
    "myst_parser",
]
myst_enable_extensions = ["dollarmath", "amsmath"]   # if math lives in .md
```

Verify the math page ships MathJax markup (`tex-mml-chtml`, `class="math`)
and contains NO `imgmath`/`dvipng` references.

## Install docs deps via uv

The workflow installs docs deps with `uv`, not pip:

```yaml
- name: Install uv
  uses: astral-sh/setup-uv@v5
- name: Install package + docs deps
  run: uv pip install --system -e ".[docs]"
```

## Canonical PR-vs-push build step

`-W` strict on every event (PRs and develop/main pushes); the bundle
refresh + commit-back stays develop-push-only:

```yaml
- name: Build Sphinx HTML (warnings fail the build)
  run: sphinx-build -W -b html docs/sphinx docs/sphinx/_build/html
```

(Some packages relax `-W` to PR-only and run a bare build on push so a
late docstring slip can't block a release tag; with `suppress_warnings`
in place the benign modes are already neutralized, so keeping `-W` on
all events is preferred.)

## Per-package tailoring (for ecosystem rollout)

`suppress_warnings = ["docutils"]` + `sphinx.ext.mathjax` + the
`continue-on-error` commit-back step + the uv install are
**package-agnostic** — drop them in as-is.

The only per-package knob is `autodoc_mock_imports`: list that package's
unavailable heavy/peer imports, or omit it entirely when `pip install .`
resolves every dependency. A package with no math directives doesn't
strictly need `mathjax` either, but including it is harmless (no system
dep) and future-proofs the first math docstring.

## See also

- [`04_docs/02_sphinx.md`](02_sphinx.md) — Sphinx layout, the
  `_sphinx_html` wheel bundle, `audit-project` PS-12x rules.
- [`04_docs/03_rtd.md`](03_rtd.md) — Read the Docs onboarding +
  the `autodoc_mock_imports` RTD variant.
