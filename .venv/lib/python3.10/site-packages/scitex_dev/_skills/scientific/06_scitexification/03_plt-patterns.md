---
description: |
  [TOPIC] Scitexification Stage 3 — Figure (plt) patterns
  [DETAILS] Stage 3 of the 5-stage scitexification arc: every
  `plt.savefig(...)` becomes `stx.io.save(fig, ..., symlink_to=...)` so
  the figure is bound to a session output (and joins the DAG built in
  stages 1 + 2); every visual style choice ladders up to figrecipe's
  publication-quality primitives (axis labels, font sizes, colour
  palettes, multi-panel layout). Once stage 3 lands, figures are
  first-class session outputs (not loose `.png`s in the cwd) and can be
  referenced from clew claims at stage 4.
tags: [scitexification, scitexification-plt]
---

# Stage 3 — Figure (plt) patterns

The publication-quality step, and the one with the strongest provenance
payoff. A figure is **not an image**: it is `code → recipe (YAML) →
media`, with **DATA (csv = what is shown)** kept separate from **STYLE
(presets = how it looks)**. `plt.savefig(...)` becomes
`stx.io.save(fig, ...)` so the figure lands DAG-bound under the
session-managed root *and auto-emits its source CSV* — the data half of
every figure's evidence chain.

> **What changes**: every `plt.savefig`; every place visual style is
> hand-encoded.
> **What stays the same**: figure intent (what comparison, which axes),
> what information the figure carries.

## The core swap

```python
fig, ax = stx.plt.subplots()          # session-bound plt (Stage 2 injects it)
ax.plot_line(x, y)                     # figrecipe primitive
ax.set_xyt("Time (s)", "Amplitude", "Ripple")   # x-label, y-label, title in one call
stx.io.save(fig, "ripple.png", symlink_to=eval(CONFIG.PATH.FIG_RIPPLE))
#   → ripple.png  +  ripple.csv   (the plotted data, auto-exported)
```

`stx.io.save(fig, ...)` is the single rule that replaces every
`plt.savefig`. The emitted `ripple.csv` is what makes the figure a
**verifiable artefact** — a reviewer (or a clew claim) can trace the
rendered pixels back to the numbers, and `make repro` can re-derive both.

## Session figures: use the injected `plt`, not top-level `figrecipe`

Inside an `@stx.session` script the figure API must be the **session-injected
`plt`** (`plt.subplots`, Stage 2) — NOT top-level `import figrecipe as fr` /
`fr.subplots`. The injected `plt` loads `SCITEX_STYLE`; raw `fr` does not, so the
two render **differently**, and that difference silently breaks reproduction and
cross-figure consistency.

- **No per-call `fontsize=` / `lw=`.** Font sizes and line widths come from the
  loaded style; setting them per-call overrides the style and un-reproducibly
  pins sizes. Document any genuine exception (e.g. tiny multi-tile grids).
- **No manual margins.** Let `plt.subplots` crop; hand-tuned margins are the
  usual cause of a figure that "doesn't crop" and whose reproduction depends on
  hard-coded sizes.

(A linter rule steering `fr` → injected `plt` inside `@stx.session` modules is
requested — pairs with this convention.)

## Translation inventory

| Original | SciTeX |
|---|---|
| `plt.savefig("f.png")` | `stx.io.save(fig, "f.png", symlink_to=...)` |
| `plt.figure(); plt.plot(x,y); plt.xlabel(..); plt.ylabel(..); plt.title(..)` | `fig, ax = stx.plt.subplots(); ax.plot_line(x,y); ax.set_xyt(..,..,..)` |
| hand-tuned colours (`plt.cm.viridis(i)`) | `COLORS.<NAME>` (injected, Stage 2) or figrecipe palette primitives |
| `gridspec` / `subplot2grid` multi-panel | `stx.plt.subplots(nrows, ncols)` + figrecipe layout |
| error bands by hand (`fill_between`) | `ax.plot_shaded_line(...)` / `plot_mean_ci(...)` |
| `sns.heatmap(...)` | `ax.plot_heatmap(...)` (keeps the CSV export) |

## Figures are clew claims (the Stage 4 bridge)

Because the figure carries its `.csv` and is saved under the session DAG,
a Stage-4 claim can bind to it: *"Figure 3's pathological-channel count
(N=42) comes from `fig3.csv`, derived from `pool.csv`, derived from
`raw/…`."* The recipe + DATA live with the **script output**, never in
the paper's caption dir (a stray recipe YAML there is build-invisible
cruft). The manuscript consumes only the rendered media, by **symlink**.

## Corner cases

- **Throwaway / exploratory plots** — a one-off diagnostic can stay on
  bare matplotlib, but anything that ends up in a paper, report, or claim
  must go through `stx.plt` + `stx.io.save` so it carries its CSV.
- **seaborn / MNE / domain plotters** — wrap the returned `fig`/`ax` and
  still `stx.io.save(fig, ...)`; you lose the auto-CSV unless you also
  pass the underlying data, so prefer the figrecipe primitive where one
  exists.
- **3D / animations** — save the figure object; the CSV export covers the
  plotted series, not frame state. Note the limitation in the caption.
- **Never** call `matplotlib.pyplot.savefig(...)` from a SciTeX session
  script — it writes outside the session output dir, is invisible to
  provenance tooling, and silently breaks `make repro`.

## Worked example

```python
# BEFORE                              # AFTER (stage 3)
plt.figure(figsize=(8,6))             fig, ax = stx.plt.subplots()
plt.plot(t, v, color="C0")            ax.plot_line(t, v)
plt.xlabel("t"); plt.ylabel("v")      ax.set_xyt("t", "v", "Trace")
plt.title("Trace")                    stx.io.save(fig, "trace.png",
plt.savefig("trace.png")                  symlink_to=eval(CONFIG.PATH.FIG_TRACE))
#   → trace.png only                  #   → trace.png + trace.csv (DAG-bound)
```

## Per-figure entry points

Each composed figure gets a uniform, reproducible pair:

- `plot_figNN_composed.py` — config-driven "smart compose" over the panel recipes.
- `plot_figNN.sh` — the runner.

so every figure builds the same way and re-runs identically.

## Follow-up

- Full figrecipe primitive surface (figure types, publication-quality
  defaults, palette + layout primitives, the `recipe → figure` flow) →
  **`figrecipe`'s own SKILL.md** and `scitex-plt`'s SKILL.md.
- Stage 2 ([`02_session-config.md`](02_session-config.md)) injects the
  session-bound `plt` + `COLORS` this chapter uses.
- Stage 4 ([`04_repro-clew.md`](04_repro-clew.md)) registers the figure's
  headline number as an evidence-bound claim.

See also: [`00_playbook.md`](00_playbook.md),
[`SKILL.md`](SKILL.md),
[`../01_figures_01_standards.md`](../01_figures_01_standards.md)
(figure standards: generative, verifiable artefacts).
