---
description: |
  [TOPIC] Scitexification Stage 2 — Session + config
  [DETAILS] Stage 2 of the 5-stage scitexification arc: the script
  entry-point becomes `@stx.session.start(...)`; magic numbers and
  hard-coded paths become `CONFIG.<KEY>` lookups against `config/*.yaml`
  (deep-merged); ad-hoc `print` becomes the session logger. Once stage 2
  lands, every later session run gets a dated output dir, a per-run
  logger, and a single config knob to flip — which is the precondition
  for stage 3 (figure DAG hooks) and stage 4 (claim registration). Stage
  1's I/O calls keep working unchanged; they just gain a session-owned
  output root.
tags: [scitexification, scitexification-session-config]
---

# Stage 2 — Session + config

The structural step. The script's `if __name__ == "__main__": main()`
becomes an `@stx.session.start(...)`-decorated `main`; magic numbers move
to `config/*.yaml` and are read as `CONFIG.<KEY>`; bare `print` calls
become the injected `logger`. The program's *shape* does not change — its
entry-point and its parameter surface do.

> **What changes**: the entry-point, the parameter-reading layer, the
> logging layer.
> **What stays the same**: function-call structure, module organization,
> test cases.

## The decorated entry-point

```python
import scitex as stx

@stx.session.start
def main(CONFIG=stx.session.INJECTED, logger=stx.session.INJECTED,
         plt=stx.session.INJECTED, COLORS=stx.session.INJECTED,
         rngg=stx.session.INJECTED):
    """Docstring becomes the --help description."""
    df = stx.io.load(eval(CONFIG.PATH.RAW_CSV))
    logger.info(f"loaded {len(df)} rows")
    ...
    return 0
```

- **Minimum** injection is `CONFIG` + `logger`; the full five-tuple
  (`CONFIG, logger, plt, COLORS, rngg`) is supported and recommended —
  `plt` is the session-bound `stx.plt` (Stage 3), `rngg` the seeded RNG
  gateway (deterministic runs), `COLORS` the palette.
- The decorator gives each run a **dated output dir** (`SDIR_OUT`) and a
  **per-run logger**, so Stage-1 `stx.io.save(...)` lands under a
  session-owned root automatically — no `os.makedirs`.

## Config: `config/*.yaml` → `CONFIG.<KEY>`

Magic numbers and paths become YAML, deep-merged across files and read by
dotted access:

```yaml
# config/PARAMS.yaml
THRESHOLD: 0.5
N_FOLDS: 5
```
```yaml
# config/PATH.yaml   — values are Python f-strings, evaluated at load
RAW_CSV:     f"./data/raw.csv"
METRICS_CSV: f"./data/metrics.csv"
```
```python
CONFIG.THRESHOLD                 # 0.5
stx.io.load(eval(CONFIG.PATH.RAW_CSV))   # PATH values are f-strings → eval
```

### CONFIG access conventions

`CONFIG` is a constant — treat it like one:

- **Full path from the root, inline at every use site**
  (`CONFIG.PAPER_FIGURES.FIG02.PANEL_D.AXES_WIDTH_MM`). Never split it into an
  intermediate variable — neither a section handle
  (`fig2 = CONFIG.PAPER_FIGURES.FIG02`) nor a scalar alias. Inline access keeps
  every read greppable and traceable to one source.
- **UPPERCASE keys**, and functions that receive config take an uppercase
  `CONFIG` parameter.
- **Move module-scope domain literals into config** — event orders, key maps,
  layout toggles belong in `config/*.yaml`, not as top-of-file constants.

### Pre-flight rules (config corner cases that crash silently)

```
□ config/PATH.yaml has NO outer `PATH:` wrapper. Top-level keys are
  exposed directly under CONFIG.PATH.<KEY>; an outer wrapper yields
  CONFIG.PATH.PATH.<KEY> and every access site raises AttributeError.
□ PATH values are f-strings and are cwd-relative: use f"./data/x", NOT
  f"{ROOT}/data/x" — ROOT is not in scope at eval time.
□ Makefile must NOT set `SHELL := /bin/bash` — it breaks @stx.session
  under make. And `cd $(ROOT) && python3 ...` so cwd-relative f-strings
  resolve when make runs from elsewhere.
□ Declare all five INJECTED params explicitly; a missing one breaks the
  DI assumptions downstream stx modules make.
□ @stx.session CONFIG (`_DotDict`) access is CASE-SENSITIVE: unlike
  `load_configs`, the session path does NOT auto-uppercase, so a YAML key
  must be written in the SAME case it is accessed. Convention: UPPERCASE
  both. (A panel reading `CONFIG.PAPER_FIGURES.REP_SUBJECT_ID` fails against
  a lowercase `rep_subject_id` YAML key.)
```

## Migrating an existing config layer

| Original | SciTeX |
|---|---|
| `argparse` / `sys.argv` flags | move defaults to `config/PARAMS.yaml`; keep only true *invocation* flags |
| module-scope `MAGIC = 0.5` | `CONFIG.MAGIC` (one YAML line) |
| `hydra` / `gin` config | port the resolved values into `config/*.yaml`; drop the framework |
| `click` CLI | the `@stx.session.start` docstring + CONFIG replaces most of it |
| `logging.getLogger(...)` / `print` | the injected `logger` (`.info/.warning/.error`) |

Don't run two config systems at once: either fully on `CONFIG` or, for a
call site you're not migrating yet, fully on the original — mixing
`os.path.join(...)` and `CONFIG.PATH.<KEY>` in the same script is the
loudest tell that Stage 2 was rushed.

## Worked example

```python
# BEFORE                                    # AFTER (stage 2)
THRESH = 0.5                                 # config/PARAMS.yaml: THRESHOLD: 0.5
def main():                                  @stx.session.start
    df = pd.read_csv("data/raw.csv")         def main(CONFIG=stx.session.INJECTED,
    print("loaded", len(df))                          logger=stx.session.INJECTED):
    ...                                          df = stx.io.load(eval(CONFIG.PATH.RAW_CSV))
if __name__ == "__main__":                       logger.info(f"loaded {len(df)}")
    main()                                       ...
                                                 return 0
```

Function bodies and tests are untouched; the entry-point and the
parameter/logging layers moved.

## Follow-up

- Full `scitex_session` surface (the `@stx.session.start` signature,
  INJECTED params, `SDIR_OUT`/`SDIR_RUN`, YAML deep-merge + CLI/env
  overrides, lifecycle hooks) → **`scitex-session`'s own SKILL.md**.
- Stage 1 ([`01_io-patterns.md`](01_io-patterns.md)) is the precondition —
  every I/O call must already be on `stx.io.{load,save}`.
- Stage 3 ([`03_plt-patterns.md`](03_plt-patterns.md)) hooks the figure
  DAG into the session-managed output dir established here.

See also: [`00_playbook.md`](00_playbook.md) (universal pre-flight +
done-condition), [`SKILL.md`](SKILL.md) (the 5-stage table),
[`../02_research-project_07_config-and-parameters.md`](../02_research-project_07_config-and-parameters.md)
(the `@stx.session` config reference).
