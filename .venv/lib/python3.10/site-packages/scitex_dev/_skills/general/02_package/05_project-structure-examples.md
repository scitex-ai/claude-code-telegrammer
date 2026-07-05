---
description: |
  [TOPIC] Package Examples
  [DETAILS] `./examples/` for a SciTeX package — runnable demos, mandatory numbered prefix (`01_<descriptive-name>.{py,sh,ipynb}`), `_out/` artefacts committed to git so users see them on GitHub, `00_run_all.sh` dispatcher, matched 1:1 by `tests/examples/test_<stem>.py`. Use SciTeX where applicable (`@stx.session`, `stx.io`, `stx.plt`); examples are free to import the umbrella `scitex`. Include agentic demos (MCP-tool prompts, Skills invocation patterns) where the package exposes those interfaces.
tags: [scitex-general-package-project-structure-examples]
---

# `./examples` — runnable demos

> Sibling leaves: [`./root`](01_project-structure-root.md) · [`./src`](02_project-structure-src.md) · [`./scripts`](03_project-structure-scripts.md) · [`./scripts/makefile`](04_project-structure-makefile.md) · [`./tests`](06_project-structure-tests.md)

## What goes here

- Runnable demos for each main feature.
- Every example must actually work (validated by `tests/examples/`).
- Examples are **free to import the umbrella `scitex`** — unlike `src/`, they sit at the consumer side of the cascade.
- Use SciTeX where applicable: `@stx.session`, `stx.io`, `stx.plt`.

## Canonical pattern: `@stx.session`-decorated `main()`

The reference is `~/proj/figrecipe/examples/01_bundle_format.py` and
`~/proj/scitex-python/examples/01_session.py`. Every `.py` example
should follow this shape:

```python
#!/usr/bin/env python3
"""Example: <one-line>.

Run:
    python NN_<name>.py
    python NN_<name>.py --some-flag value
    python NN_<name>.py --help
"""
from pathlib import Path
import scitex as stx
import <pkg>


@stx.session
def main(
    some_flag: str = "default",        # auto-becomes --some-flag
    CONFIG=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    """Demonstrate <feature>."""
    OUT = Path(CONFIG.SDIR_RUN)
    logger.info(f"Output dir: {OUT}")
    # ... do work, write to OUT, return 0


if __name__ == "__main__":
    main()
```

What `@stx.session` gives you for free:

- **Auto-CLI**: every `def main(...)` parameter becomes a `--kebab-case`
  flag with the right type — no `argparse` boilerplate.
- **Auto-organized output**: `CONFIG.SDIR_RUN` points at
  `<example-stem>_out/FINISHED_SUCCESS/<session_id>/` (or `…/RUNNING/`
  / `…/FAILED/` while in progress / on error). The state-suffix is the
  signal that the run completed cleanly.
- **Config injection**: `CONFIG` aggregates `./config/*.yaml` files at
  the package root.
- **Pre-wired matplotlib + logger**: ask for `plt=stx.session.INJECTED`
  or `logger=stx.session.INJECTED` and they arrive configured.
- **Reproducibility**: each run gets a unique `CONFIG.ID` and stdout/
  stderr are captured into `SDIR_RUN/logs/`.

When **NOT** to use `@stx.session`: shell scripts (`.sh`), or
notebooks where Jupyter is the runner (`.ipynb` — see below).

## Mandatory numbered prefix

```
./examples/01_<descriptive-name>.{py,sh,ipynb}
./examples/01_<descriptive-name>_out/        # outputs, git-tracked
./examples/02_<another-name>.py
./examples/02_<another-name>_out/
./examples/00_run_all.sh                     # dispatcher
```

- The `NN_` prefix gives a stable execution order and makes `00_run_all.sh` a simple `for f in NN_*.py; do …; done`.
- `.py` is preferred over `.ipynb` for diffability + CI; pick `.ipynb` only when GitHub-rendering is the point.

## `_out/` artefacts — git-tracked

Each example writes to `./examples/<stem>_out/` (a sibling directory, not a subdir of the example file's stem).

- These directories are **git-tracked** so users see what the demo produces on GitHub.
- A few outputs (figures, GIFs) are linked from `README.md` as assets.
- Outputs that bloat the wheel: keep them out via the `templates/` / wheel-vs-git pattern (see [`02_package/01_project-structure-root.md`](01_project-structure-root.md#templates--wheel-vs-git-payload-separation)).
- Don't commit run-specific artefacts like `SDIR_RUN/` outputs — those are session-unique and would churn on every demo run.

## `00_run_all.sh` — dispatcher

A single-command end-to-end demo + CI regress:

```bash
#!/bin/bash
# ./examples/00_run_all.sh
set -euo pipefail
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$THIS_DIR"
for f in 0[1-9]_*.py 1[0-9]_*.py; do
    [ -f "$f" ] || continue
    echo "==> $f"
    python "$f"
done
```

## `.ipynb` — when GitHub-rendering matters

Jupyter notebooks render inline on GitHub with cell outputs visible,
which makes them ideal for tutorial-style examples (see
`~/proj/scitex-python/examples/02_io.ipynb` etc.). Keep the same
numbered-prefix convention: `02_io.ipynb`, `03_clew.ipynb`, …

`.ipynb` cannot use `@stx.session` (the decorator wraps a function;
notebooks execute cell-by-cell). Author them as a sequence of cells
that import the package and demonstrate features inline. The `_out/`
sibling directory is optional for notebooks since the rendered cell
outputs ARE the demonstration.

### Testing `.ipynb` examples

`runpy` doesn't help for notebooks. Two workable approaches:

1. **`jupyter nbconvert --execute --to notebook --output /dev/null
   <file>.ipynb`** — runs every cell; non-zero exit on any failure.
   Cheapest CI integration.
2. **`pytest-nbval`** (`pytest --nbval-lax examples/`) — runs each
   notebook and tolerates output drift; flag `--nbval` (strict) if
   you also want output equality.

For `.py` examples the `tests/examples/test_<stem>.py` mirror runs
them directly (via `runpy.run_path` or `subprocess.run`). For
`.ipynb` examples the matching test invokes `nbconvert` or `nbval`.

## 1:1 match with `tests/examples/`

Every example file has a matching test under [`./tests/examples/`](06_project-structure-tests.md). The test's job is to confirm the example runs to completion and produces the expected `_out/` artefacts.

```
examples/01_load_save.py            →  tests/examples/test_01_load_save.py
examples/02_plot_summary.py         →  tests/examples/test_02_plot_summary.py
```

PS-303 of `audit-project` flags an example without a matching test.

## Agentic demos

Where the package exposes MCP tools or Skills, the examples directory should include:

- A `.py` file showing the **direct Python API** call (e.g. `stx.io.save(...)`).
- A short prompt file or markdown demo showing the **agentic invocation** (the MCP-tool name an agent would call, the Skill phrase that should trigger it).

This lets `tests/agentic/` regress the trigger surface against real prompts.

## Quick checklist

- [ ] `./examples/00_run_all.sh` dispatcher exists
- [ ] Every demo file numbered `NN_<descriptive-name>.{py,sh,ipynb}`
- [ ] Every demo has a sibling `_out/` directory committed
- [ ] Every demo has a matching `tests/examples/test_*.py`
- [ ] Outputs linked from README are produced by an example, not hand-edited
