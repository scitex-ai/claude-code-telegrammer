---
description: |
  [TOPIC] No-Synthetic-Data-In-Publication-Figures Policy
  [DETAILS] Ecosystem-wide rule for the SciTeX scientific stack: paper, representative, and publication figures MUST NOT contain synthetic or placeholder data. If the real data is absent at render time, the figure-generation script must FAIL LOUD (raise / abort / non-zero exit) rather than silently substitute a fake. Applies to every package that emits publication artefacts (figrecipe, scitex-clew, scitex-stats, downstream paper repos). Synthetic data is only acceptable in clearly-marked test fixtures (`tests/fixtures/`, `examples/synthetic_*.py`) where the intent is "exercise the API", never "stand in for a result".
tags: [scitex-scientific-no-synthetic-data]
---

# No-Synthetic-Data Policy (publication figures)

Canonical ecosystem-policy home for the rule that publication-bound
figures must be backed by real data or fail loud. Per-package rendering
implementations (figrecipe rendering rule, scitex-clew claim binding)
cross-link to this leaf instead of restating.

## The rule

A figure destined for a paper, poster, slide deck, or any
representative-of-a-result asset MUST be generated from real
experimental/observational data. If the real data is unavailable at
render time the figure-generation script MUST fail loud — raise an
exception, exit with a non-zero status, or refuse to write the output
file — rather than silently substitute synthetic, random, or
placeholder values.

Synthetic data is only acceptable when:

- the artefact is clearly a test fixture (`tests/fixtures/*`,
  `tests/test_*.py`, `examples/synthetic_*.py`), and
- the file path or filename signals "synthetic" to any reader, and
- the artefact is not consumed by a paper / report / submission
  pipeline.

## Why this is policy, not preference

A placeholder figure that "looks right" travels. It gets pasted into
slides, screenshotted into Slack, referenced in a draft, and forgotten
about. By the time someone notices the axis labels were always lying,
it is in a PDF on arXiv. A loud failure at render time costs minutes;
a quiet synthetic figure costs a retraction.

## DO

- **Fail loud** when real data is missing. Raise
  `FileNotFoundError`, `ValueError`, or a domain-specific error; exit
  non-zero from CLI; refuse to write the output file.
- **Name test fixtures explicitly**: `tests/fixtures/synthetic_*.npz`,
  `examples/01_synthetic_demo.py`. The substring `synthetic` /
  `fixture` / `demo` should appear in the path.
- **Mark placeholder panels visibly** if a figure intentionally
  carries a "TODO: real data" panel during drafting — overlay a
  diagonal "PLACEHOLDER" watermark, use a red border, or write the
  word "PLACEHOLDER" in 24pt across the panel. The figure must
  refuse to render as final-quality.
- **Cross-link** from each package's rendering layer to this leaf
  (figrecipe `23_no-synthetic-data-policy.md`, scitex-clew claim
  binding docs) so the rule has one source of truth.

## DON'T

- **Don't `np.random.*` into a representative figure** to "show the
  shape" — that shape becomes the figure that ships.
- **Don't fill missing data with the column mean** for a publication
  panel. (Imputation may be a valid scientific choice, but it must be
  a *documented* method, not a silent rendering shortcut.)
- **Don't write a `make_example_figure()` helper that swallows
  `FileNotFoundError`** and renders a stub. The helper should
  propagate.
- **Don't ship `examples/representative_figure.py` that secretly uses
  `np.random.randn`** — rename it to
  `examples/synthetic_demo_figure.py` and gate any publication
  pipeline against importing from `synthetic_*` paths.

## Recommended enforcement

For projects with a paper pipeline, add a pre-PDF-build check that
rejects any figure whose generating script imports `numpy.random`,
`random`, or reads from a `synthetic_*` path:

```bash
# in scripts/makefile/check-no-synthetic.sh
grep -lE '(np\.random|from random|synthetic_)' "$SDIR_OUT"/*.py \
    && { echo "ABORT: synthetic data referenced in publication path"; exit 2; }
```

Stricter: have the figure-generation entry-point assert on data
provenance (`assert data_path.exists() and not "synthetic" in
str(data_path)`).

## Scope and exceptions

- **In scope**: figures used in papers, posters, talks, grant
  applications, internal reviews, PDF reports under
  `scientific/03_reporting_*`, and any artefact referenced as a
  "result".
- **Out of scope**: API exercise tests, package-level
  `examples/quickstart.py` that demonstrates the library's
  *call shape*, hand-drawn schematic diagrams (`figrecipe`
  diagram primitives) that carry no quantitative claim.
- **Exception**: a figure may use a real-data subset clearly
  marked as "schematic" (`schematic=True` kwarg, "(schematic)" in
  the title) where the goal is to teach the reader what the axes
  mean before the real result is shown. This is not synthetic data;
  it is a downsampled / curated real example.

## Cross-references

- `figrecipe/_skills/figrecipe/23_no-synthetic-data-policy.md` — the
  same rule, applied as a rendering-layer guard inside figrecipe
  (refuse-to-render on missing data, name test fixtures clearly).
- `01_figures_01_standards.md` — universal figure standards (color
  scale, axes, layout). This policy is the *content* counterpart to
  those *presentation* rules.
- `01_figures_02_provenance-and-verification.md` — provenance binding
  (Source→Figure DAG, Clew claims). Hash-verifying a synthetic-data
  figure is worse than not verifying it at all: it certifies the
  fake.
- `99_lessons-learned.md` — the failure mode that motivated this
  leaf.
