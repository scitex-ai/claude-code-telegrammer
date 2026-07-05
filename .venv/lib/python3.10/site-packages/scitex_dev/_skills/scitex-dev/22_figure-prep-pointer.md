---
description: |
  [TOPIC] Figure Prep — see figrecipe playbook
  [DETAILS] Pointer leaf. Figure preparation across the SciTeX ecosystem is owned by figrecipe; this scitex-dev leaf exists only so an agent loading the scitex-dev skill set discovers the figrecipe playbook. The canonical content lives in `figrecipe/_skills/figrecipe/21_figure-prep-playbook.md` (figure-prep playbook), `22_nan-sentinel-on-read.md` (NaN-sentinel handling), `24_l-shaped-scale-bar.md` (L-shaped scale bar on signal traces), and `scientific/01_figures_03_no-synthetic-data-policy.md` (ecosystem-policy authority for the real-data-only rule).
tags: [scitex-dev-figure-prep-pointer]
---

# Figure Prep — see figrecipe

This leaf is a discoverability shim. Figure-preparation conventions
for the SciTeX ecosystem are owned by **figrecipe**, with the
ecosystem-wide policy authority living under the scitex-dev
**scientific** skill umbrella.

## Where the content actually lives

| Topic | Canonical leaf |
|---|---|
| Seven-rule figure-prep playbook (real data, NaN, common scale, representative-example criteria, config-as-SSoT, figrecipe dogfood, L-shaped scale bar on signal traces) | `figrecipe/_skills/figrecipe/21_figure-prep-playbook.md` |
| Convert storage-layer sentinel (e.g. `-32768`) → `np.nan` at the figure layer | `figrecipe/_skills/figrecipe/22_nan-sentinel-on-read.md` |
| No-synthetic-data-in-publication-figures (ecosystem policy authority) | `scitex_dev/_skills/scientific/01_figures_03_no-synthetic-data-policy.md` |
| No-synthetic-data (figrecipe rendering-side guard) | `figrecipe/_skills/figrecipe/23_no-synthetic-data-policy.md` |
| L-shaped scale bar for representative signal-trace panels (hide axes; lower-left time + amplitude bars sharing a corner) | `figrecipe/_skills/figrecipe/24_l-shaped-scale-bar.md` |
| Universal scientific-figure standards (color, axes, layout) | `scitex_dev/_skills/scientific/01_figures_01_standards.md` |
| Figure provenance / Source→Figure DAG | `scitex_dev/_skills/scientific/01_figures_02_provenance-and-verification.md` |

## When to load this leaf vs the canonical leaves

- Load this leaf if you discovered it via the scitex-dev skill index
  and need to know which figrecipe / scientific leaves to read next.
- Load the figrecipe playbook (`figrecipe/_skills/figrecipe/21_*`)
  directly when you are actually preparing a figure.
- Load the scientific policy leaf
  (`scientific/01_figures_03_no-synthetic-data-policy.md`) when you
  are arbitrating "is this an OK source of data?" — the authoritative
  rule lives there.

This leaf intentionally carries no rules of its own — adding rules
here would create a second source of truth and the two would drift.
