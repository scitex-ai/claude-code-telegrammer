---
description: |
  [TOPIC] Scitexification Stage 1 — I/O patterns
  [DETAILS] Stage 1 of the 5-stage scitexification arc: every `open()` /
  `np.load` / `pd.read_csv` / `pickle.load` becomes `stx.io.load(...)`;
  every `np.save` / `pickle.dump` / `df.to_csv` becomes `stx.io.save(...,
  symlink_to=...)`. Once both halves are mechanically swapped, DAG
  composition (output of step N is the input of step N+1) becomes
  visible at the filesystem level — which is the precondition every
  later stage builds on (config wins at stage 2, the figure DAG hooks
  at stage 3, evidence-binding at stage 4, naming/numbering at stage 5).
tags: [scitexification, scitexification-io]
---

# Stage 1 — I/O patterns

The mechanical translation step. Every read becomes `stx.io.load(...)`,
every write becomes `stx.io.save(..., symlink_to=...)`. The DAG that was
implicit in the original script (`step_2.py` reads what `step_1.py`
wrote) becomes explicit on disk: each output's real bytes land beside the
script that produced it, and a symlink at the consumed path points back,
so a `find`, a `make repro`, or a clew lineage walk can reconstruct the
pipeline from the filesystem alone.

> **What changes**: every I/O call site.
> **What stays the same**: your algorithm, your data shapes, your
> business logic. Stage 1 is a mechanical rewrite, not a redesign.

## Translation inventory

### Reads → `stx.io.load`

`stx.io.load(path)` auto-detects the format from the extension, so the
loader collapses every reader into one call:

| Original | SciTeX |
|---|---|
| `open(path).read()` / `open(path, "rb").read()` | `stx.io.load(path)` |
| `json.load(open(path))` | `stx.io.load(path)`  (`.json`) |
| `yaml.safe_load(open(path))` | `stx.io.load(path)`  (`.yaml`) |
| `np.load(path)` / `np.loadtxt(path)` | `stx.io.load(path)`  (`.npy`/`.npz`/`.txt`) |
| `pd.read_csv(path)` / `read_parquet` / `read_excel` | `stx.io.load(path)` |
| `pickle.load(open(path, "rb"))` | `stx.io.load(path)`  (`.pkl`) |
| `torch.load(path)` | `stx.io.load(path)`  (`.pth`/`.pt`) |
| `cv2.imread(path)` / `Image.open(path)` | `stx.io.load(path)`  (`.png`/`.jpg`) |
| `h5py.File(path)["k"][:]` | `stx.io.load(path, key="k")`  (`.h5`) |

### Writes → `stx.io.save(..., symlink_to=...)`

Always pass the **object first, path second**, and bind cross-stage
consumers with `symlink_to=` (see "The `symlink_to=` idiom" below):

| Original | SciTeX |
|---|---|
| `json.dump(obj, open(path,"w"))` | `stx.io.save(obj, path)` |
| `np.save(path, arr)` / `np.savetxt(path, arr)` | `stx.io.save(arr, path)` |
| `pickle.dump(obj, open(path,"wb"))` | `stx.io.save(obj, path)` |
| `df.to_csv(path)` / `to_parquet` / `to_excel` | `stx.io.save(df, path)` |
| `torch.save(model, path)` | `stx.io.save(model, path)` |
| `plt.savefig(path)` | `stx.io.save(fig, path)`  → **see Stage 3** |

`stx.io.save` also **auto-exports the source CSV** for figures/tables, so
a saved `stx.plt` figure emits `plot.png` + `plot.csv` in one call — the
data half of every figure's provenance. Detail lives in Stage 3 and in
`scitex-plt` / `figrecipe`.

## The `symlink_to=` idiom (what makes the DAG visible)

This is the load-bearing pattern of Stage 1. `stx.io.save` writes the
**real bytes** next to the producing script's output dir, and
`symlink_to=` drops a **symlink** at the path the next stage reads:

```python
# stage 1 — extract
stx.io.save(metrics_df, "metrics.csv",
            symlink_to=eval(CONFIG.PATH.METRICS_CSV))
#   real bytes : ./scripts/01_extract_out/metrics.csv
#   symlink at : ./data/metrics.csv  →  ../scripts/01_extract_out/metrics.csv

# stage 2 — consume
df = stx.io.load(eval(CONFIG.PATH.METRICS_CSV))   # follows the symlink
```

The result: one **Output** node (the real file) and one **Input** node
(the symlink the consumer reads) per cross-stage hand-off — which is
exactly the edge a clew lineage walk (Stage 4) needs. `eval(CONFIG.PATH.X)`
resolves the path through the config established in Stage 2; until Stage 2
lands you may pass a literal `"./data/metrics.csv"`.

## Corner cases (the ones that bite)

- **`.txt` loads as `list[str]`** — `stx.io.load("x.txt")` returns lines,
  not a flat string. Iterate as-is, or `"\n".join(lines)`.
- **Non-registered extensions** (`.mmd`, `.tex` source, `.bib`) — `stx.io`
  only handles the ecosystem-registered savers. Fall back to
  `Path(p).write_text(...)` / `read_text()` for those.
- **Append mode** (`open(p, "ab"/"a")`) — `stx.io.save` is whole-object
  write-replace; there is no append. Accumulate in memory and save once,
  or keep the explicit `open(..., "a")` for genuine streaming logs.
- **`dtype=object` pickles / custom classes** — round-trip via the `.pkl`
  saver works, but the class must be importable at load time; prefer a
  plain dict/array payload where you can.
- **Non-descriptive source names** (a project's literal `output`,
  `stdout`) — **copy** (don't symlink) into a descriptive `data/<name>`
  before Stage 1. `stx.io`/clew resolve a symlink to its *target*
  basename, so `result_output.txt → output` would show up as `output` in
  the DAG; a real copy shows `result_output.txt`.

## Two I/O modes (environment caveat)

`stx.io.save` needs `libgthread-2.0.so.0` (Debian/Ubuntu `libglib2.0-0`).
On a stripped container where it is missing, older `scitex-io` **silently
no-ops the save** (newer versions raise). A 30-second pre-flight catches
it before you scaffold for the wrong mode:

```python
import tempfile, os, scitex as stx
probe = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
os.unlink(probe)
stx.io.save({"ok": True}, probe)
assert os.path.exists(probe), "stx.io.save no-oped → use stdlib I/O in this env"
```

If unavailable, do Stage-1 I/O with `Path.write_text`/`read_text` +
`json`, and let Stage 4 record provenance explicitly via
`scitex_clew.add_claim(source_file=...)` (source-verified, chain-unverified).

## Worked example

```python
# BEFORE                                   # AFTER (stage 1 only)
import pandas as pd, pickle                import scitex as stx
df = pd.read_csv("raw.csv")                df = stx.io.load("raw.csv")
acc = train(df)                            acc = train(df)            # unchanged
pickle.dump(acc, open("acc.pkl", "wb"))    stx.io.save(acc, "acc.pkl",
                                              symlink_to="./data/acc.pkl")
```

The algorithm (`train`) is untouched; only the I/O call sites moved.

## Follow-up

- Full `stx.io.{load,save}` surface (registered formats, `symlink_to=`
  semantics, `verbose=`, error handling) → **`scitex-io`'s own SKILL.md**
  (this chapter teaches *which* call to reach for, not the full API).
- Stage 2 ([`02_session-config.md`](02_session-config.md)) wraps the
  entry-point in `@stx.session.start(...)` so these I/O calls land under
  a session-managed, dated output root automatically.

See also: [`00_playbook.md`](00_playbook.md) (universal pre-flight +
done-condition), [`SKILL.md`](SKILL.md) (the 5-stage table).
