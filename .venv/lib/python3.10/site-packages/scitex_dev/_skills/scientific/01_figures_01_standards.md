---
description: |
  [TOPIC] Scientific Figures
  [DETAILS] Universal, library-agnostic standards for publication-quality scientific figures — comparison rules (shared colour scale, aligned axes, consistent sample-size annotations), multi-panel layout grids, colour-map selection for categorical vs continuous vs divergent data, typography and legend placement, PDF-report layout (aspect, DPI, bleed), and how to justify breaking each rule. Pairs with `figrecipe/21_scientific-figure-patterns.md` for matplotlib-specific implementation code. Use when designing any figure for a manuscript, poster, or talk; when reviewing a plot for common pitfalls; or when auditing an ecosystem output for scientific rigour.
tags: [scitex-scientific-figures-standards]
---

# Scientific Figure Standards (universal principles)

Library-agnostic rules for scientific figures. For figrecipe/matplotlib code
patterns that implement these rules, see
[../../figrecipe/21_scientific-figure-patterns.md](../../figrecipe/21_scientific-figure-patterns.md).

## Comparison Figures: Mandatory Rules

When comparing conditions (treatment vs control, pre vs post, seizure vs
interictal, etc.):

1. **Same color scale.** Both panels MUST share identical `vmin`/`vmax` so
   intensities are directly comparable. Compute the global min/max across all
   compared conditions BEFORE drawing. For diverging data, use a symmetric
   range (`vabs = max(|vmin|, |vmax|)`, then `vmin=-vabs, vmax=vabs`). If the
   data is heavy-tailed, share a **percentile** range across conditions instead
   of raw min/max — see Robust Limits for Long-Tailed Data.
2. **Aligned axes.** Use shared x and y across the panels. Remove redundant
   tick labels on inner axes — only label the outer edges.
3. **Side-by-side layout.** Place conditions horizontally (or in a small grid)
   for direct visual comparison. Label each panel clearly with the condition
   name.
4. **Same axis range** on x and y, even if one condition has less data — the
   visual comparison is destroyed by mismatched ranges.
5. **One shared colorbar** for the comparison group (not one per panel) so
   the color↔value mapping is unambiguous.

## Representative Examples Must Be Genuinely Typical

A panel labelled "representative" (subject / channel / trial / window) must be
typical of the population it stands for — **not** the strongest or most
photogenic case:

- **Pick by a stated, reproducible criterion** (median effect, nearest-to-mean),
  never by eye, and state that criterion in the caption.
- **Cross-check against the population.** A representative *control* must NOT
  exhibit the *effect* you attribute to the experimental condition; if it does,
  it is not a valid control — re-select it.
- This is the presentation counterpart to the no-synthetic-data policy
  ([01_figures_03](01_figures_03_no-synthetic-data-policy.md)): the data is
  real, but a cherry-picked real example is its own integrity failure.

## State What Each Panel Shows

The reader must never have to guess what the data is:

- **Population / unit** — is it pooled across the cohort, or a single subject /
  channel / trial / window? State it.
- **Sample size** — annotate `n` (e.g. `n = 12 seizures`). A panel with no `n`
  is incomplete.

Put it in the title, a corner annotation, or the caption — consistently across
panels.

## Multi-Panel Layout for Per-Subject Reports

- One subject (patient/participant/sample) per page, with all conditions for
  that subject shown together in a grid (e.g., 2×2 or 2×3).
- NOT one figure per page — that explodes page count and breaks comparison.
- Target page count: ~1–2 pages per subject (e.g., 15–25 pages for 15 subjects).

## Temporal Plots with Shared Time Axis

Stack a heatmap above its averaged profile (or any two plots that share time):
- Use a shared x axis for both panels.
- Allocate vertical space proportionally (e.g., heatmap : line ≈ 3 : 1).
- Hide x tick labels on the upper panel; show only on the bottom panel.

## Binned / Windowed Axes

- **Consistent, explicit half-open interval notation** for bins/windows:
  `[-32, -16)`, `[-16, -1)`, `[0, 2)`, `[2, 10)` — the `[a, b)` form makes the
  bounds and which end is inclusive unambiguous.
- **Show the complete series of windows** — don't drop intermediate bins; a gap
  in the sequence misleads the reader.

## Color Maps

- **Diverging data** (positive/negative around 0): `RdBu_r` or `coolwarm`.
- **Sequential data** (0 → max): `viridis` or `plasma`.
- **Never use `jet`** — perceptually non-uniform; misrepresents data.
- **A colorbar (a.k.a. scalebar) is MANDATORY for EVERY colormap, on EVERY
  panel** that encodes a numerical quantity in colour (z-score, rate, effect
  size), with **units in the label**. No exceptions — a numeric colour axis with
  no colorbar is a defect, not a stylistic choice. A shared comparison group
  still shows one colorbar; no panel may rely on colour with no scale visible.

## Robust Limits for Long-Tailed Data

A few extreme values must not dictate the axis / colour range. A long tail
stretches the scale until the bulk of the data is squashed into a sliver and the
real differences — the point of the figure — become invisible.

- **Set limits by percentiles, not raw min/max**, when the data is heavy-tailed:
  e.g. `vmin, vmax = np.percentile(data, [1, 99])`. The informative mass of the
  distribution then fills the range and differences become legible.
- **Disclose the clipping.** Clipping the tail *for visibility* is legitimate;
  hiding that you did it is not. Saturate out-of-range values to a distinct
  colour (`cmap.set_over` / `set_under`) and/or state the window in the caption
  ("colour clipped at 1st–99th pct").
- **Keep limits shared for comparisons.** Compute the percentile limits ONCE
  across ALL compared conditions (not per panel) so the panels stay directly
  comparable (see Comparison Figures).

## Axis Labels & Typography

- **Capital first letter + clear words**: "Phase Frequency (Hz)", not "phase freq".
  This applies to **all** text — legends, categorical tick labels, annotations,
  and panel titles — not only axis labels ("Density", "Preictal", not "density").
- **Italicize mathematical & statistical symbols** — variables, *R²*, *p*, *n*,
  *β* are math, not prose; set them in italic.
- **Titles: the minimal sufficient identifier**, short and clear (e.g. "Patient
  #10", not a sentence). An overlong title that is hard to parse is a defect.
- **Abbreviate consistently or not at all.** If space forces abbreviation,
  abbreviate *both* paired axes the same way — "Amp. Freq. (Hz)" must pair with
  "Phase Freq. (Hz)"; never abbreviate one axis and spell out the other.
- **Use an en-dash (–) for numeric ranges**, not a hyphen or double-hyphen:
  "10–20 Hz", not "10--20 Hz".
- A per-tile / per-window **title shows the actual range it covers**, not just a
  single offset.

## Regression & Scatter Plots

- **Fit line in a neutral colour (black)** so it stands out from the (often
  coloured) data points.
- **Show the fitted equation** — e.g. `y = ax + b` with the actual coefficients.
- **Put the fit statistics (*R²*, *p*, *n*) next to the regression line**, not
  floating in a corner, with the symbols *italicized*.

## Encoded Channels Need a Legend

Any visual channel that carries a quantity must be decodable:

- **Colour → colorbar** (with units; see Color Maps above).
- **Marker size → a size legend.** If bubble size/area encodes a value, show a
  size legend and say in the caption what size means. A bubble chart whose size
  is unexplained is unreadable.

## Effect Sizes Need Implication Thresholds

A magnitude only means something against a reference. Whenever a figure shows an
effect size, a delta, or a difference, draw the threshold(s) that make it
interpretable:

- **Significance / clinical cutoff** — a horizontal line or shaded band at the
  decision boundary, so the reader sees which points cross it.
- **Effect-size reference lines** — small / medium / large markers where
  applicable (e.g. Cohen's *d* = 0.2 / 0.5 / 0.8).
- **A "meaningful difference" line on delta plots** — a Δ is only actionable
  beside the Δ that matters.

A bare effect-size or delta with no threshold leaves the "so what" unstated.

## Reduce Chartjunk

- **Hide spines / ticks that don't aid reading.** On a heatmap / image /
  comodulogram panel the box spines and redundant ticks add nothing — hide them
  and let the colorbar + axis labels carry the information.

## PDF Report Layout

When generating multi-figure scientific reports as a PDF:

- **Bookmarks**: every section navigable via PDF outline (use `fpdf2`'s
  `start_section()` or post-hoc `pikepdf` outline editing).
- **Size**: target under 10MB for email; reduce DPI to 100–150 or compress
  with `ghostscript` if needed.
- **Aspect ratios**: preserve the original aspect ratio of every embedded
  figure — read image dimensions before laying out.
- **Captions**: every figure has a numbered caption (Figure N: …) with a
  one-sentence description.
- **Page numbers** included.

## Anti-patterns

- Two heatmaps with different `vmin`/`vmax` "for clarity" — defeats the
  comparison.
- A diverging colormap centered at the data mean instead of zero — implies
  asymmetry where there isn't any.
- One figure per PDF page for a 50-figure report — unreadable, unprintable.
- Using `jet` "because it's colorful".
- A regression panel with the fit line in a data colour, no equation, and the
  stats floating in a corner instead of beside the line.
- A bubble chart with no size legend — the reader can't decode what size means.
- A panel that doesn't say whether it's pooled or a single subject, or omits `n`.
- Lowercase axis / legend / category labels ("density", "preictal") — capitalize
  the first letter.
- Box spines + redundant ticks left on a heatmap, adding visual noise.
- A long-tailed heatmap / histogram scaled to raw min–max so the bulk is
  squashed into a sliver — use percentile (1st–99th) limits and mark the
  clipped tail.
- An effect-size / Δ panel with no implication threshold — the reader can't
  tell which values are meaningful.
- A colormap panel with no colorbar / scalebar — colour with no visible scale
  is undecodable.
