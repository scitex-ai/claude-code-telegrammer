---
description: |
  [TOPIC] Doc Surfaces — README Presentation Conventions
  [DETAILS] Adopted 2026-05. Mirrors scitex-io as the canonical reference. Covers section ordering (Problem→Quick Start→Install→How it works→Interfaces→Lint Rules→Hook→Part of SciTeX), Quick Start as top-level H2, "one diagram is enough" rule, blockquote callouts with `>`, one-sentence Problem/Solution cells (≤200 chars), two-row badge layout, mermaid init config for compact diagrams, ⭐ ratings on every interface summary, drop deprecated `> **Interfaces:** ...` callout, drop trailing "— for AI Agents" tags. Use when refreshing or auditing a SciTeX package's README, MCP descriptions, docstrings, and skill leaves.
tags: [scitex-general-development-doc-surfaces]
---

# Doc Surfaces — Presentation Conventions

## Reference package

The canonical example is **scitex-io**:
https://github.com/ywatanabe1989/scitex-io/blob/develop/README.md

When in doubt about layout, wording density, or section choice, mirror that
README verbatim. Deviations need a concrete reason (e.g., the package has no
linter, so the Lint Rules section is omitted).

## Section order (top to bottom)

Canonical H2 sequence enforced by PS-143:

1. **Problem and Solution** — single combined H2, two-column table layout.
   Each cell is **one sentence, ≤ 200 chars**, bold ≤ 30% of cell length
   (PS-144). Names the pain, then the fix.
2. **Quick Start** — top-level H2 (NOT nested under Install). A tight ~15-line
   runnable demo with a round-trip assertion so a reader can paste-and-run.
3. **Installation** — single line `uv pip install "<pkg>[all]"`. Per-module
   extras (`[hdf5]`, `[parquet]`, ...) live inside a `<details>` block.
4. **How it works** *(or `## Architecture` — both accepted by PS-142)* — split
   into `### 1. <step>`, `### 2. <step>` subsections. **One mermaid diagram
   total** (one diagram is enough — don't repeat the same picture in Demo and
   Architecture).
5. **<N> Interfaces** — `## 5 Interfaces` etc. Each interface as a
   `<details>` block. PS-131 is relaxed: `open` is OPTIONAL on all of them.
6. **Lint Rules** *(if the package ships a linter plugin)* — top-level H2,
   full rule table inside `<details>`.
7. **Claude Code Integration as a Hook** *(if applicable)* — ship the hook
   script at `examples/<pkg>_lint.sh`. Self-contained, no dotfiles dependency,
   user can `curl` it directly.
8. **Part of SciTeX** — Four Freedoms blockquote required (PS-120).

## Auditor rules

| Rule | Enforces |
|---|---|
| PS-116 | No deprecated `> **Interfaces:** ...` callout |
| PS-118 | No trailing parenthetical tags like `— for AI Agents`, `— for AI Agent Discovery` |
| PS-120 | Standardized "Part of SciTeX" umbrella one-liner |
| PS-131 (relaxed) | `<details open>` inside `## <N> Interfaces` is OPTIONAL |
| PS-141 | At least one visual in Demo OR Architecture (visual-anywhere rule) |
| PS-142 | `## Architecture` OR `## How it works` H2 required, with a diagram inside |
| PS-143 | Canonical H2 order |
| PS-144 | Problem/Solution table cells ≤ 200 chars + bold ≤ 30% |

## Mermaid sizing

Prepend every diagram with this init line so it renders compactly on GitHub
and RTD:

```
%%{init: {'flowchart': {'nodeSpacing': 20, 'rankSpacing': 40, 'curve': 'linear'}, 'themeVariables': {'fontSize': '12px'}}}%%
```

Also:

- Keep node labels short (≤ 3 words where possible).
- Drop redundant package prefixes inside nodes (`save()` not `sio.save()` once
  the diagram title already says "scitex-io").

## Blockquote (`>`) callouts

Use blockquotes for emphasis tips. Every continuation line MUST carry `>` so
markdown renders them as one connected block (a bare blank line breaks the
quote in two on GitHub):

```markdown
> **Absolute paths bypass routing.** `sio.save(df, "/data/x.csv")`
> writes to `/data/x.csv` as-is — only relative paths get routed.
```

Pattern: bold lead-in + concrete example on the same or next quoted line.

## Badge row

Two rows. Drop the AGPL license badge — redundant with `pyproject.toml` and
the umbrella footer.

```markdown
[![PyPI](https://img.shields.io/pypi/v/<pkg>.svg)](https://pypi.org/project/<pkg>/)
[![Python](https://img.shields.io/pypi/pyversions/<pkg>.svg)](https://pypi.org/project/<pkg>/)
[![Read the Docs](https://img.shields.io/readthedocs/<pkg>)](https://<pkg>.readthedocs.io/)

[![Tests](https://github.com/ywatanabe1989/<pkg>/actions/workflows/tests.yml/badge.svg)](https://github.com/ywatanabe1989/<pkg>/actions/workflows/tests.yml)
[![Install Test](https://github.com/ywatanabe1989/<pkg>/actions/workflows/install-test.yml/badge.svg)](https://github.com/ywatanabe1989/<pkg>/actions/workflows/install-test.yml)
[![Coverage](https://codecov.io/gh/ywatanabe1989/<pkg>/branch/main/graph/badge.svg)](https://codecov.io/gh/ywatanabe1989/<pkg>)
```

Row 1 = identity (PyPI / Python / RTD). Row 2 = health (Tests / Install Test
/ Coverage).

## Interface ratings (⭐)

Every interface summary line carries a 1–3 star rating reflecting recommended
use:

- ⭐⭐⭐ — primary, what most users should reach for.
- ⭐⭐ — supported, narrower audience.
- ⭐ — niche / power-user / legacy.

Stars are **required** on every interface summary. **Drop trailing
parenthetical tags** like `— for AI Agents`, `— for AI Agent Discovery`
(PS-118).

Example:

```markdown
<details>
<summary>🐍 <strong>Python API</strong> ⭐⭐⭐ — <code>import scitex.io as sio</code></summary>
```

## What to update when refreshing a package's docs

Sweep every surface — README alone is not enough:

- [ ] `README.md` (this skill)
- [ ] `SKILL.md` — drop deprecated `> **Interfaces:** ...` callout if present
- [ ] Individual skill leaves under `src/<pkg>/_skills/<pkg>/` — sweep
      `stx.io.*` to canonical `sio.*` (and equivalents for other packages);
      refresh stale rule ranges so they match the live linter
- [ ] Python docstrings (`load_configs`, `save`, `load`, ...) — first-line
      summaries match the README's one-sentence framing
- [ ] MCP tool descriptions in `_mcp/server.py` — same one-sentence framing
- [ ] CLI `--help` epilogs — **only** if behavior changes are user-visible;
      otherwise leave alone

## Related skills

- [`04_docs/01_readme.md`](../04_docs/01_readme.md) — canonical section order
- [`04_docs/01_readme_template.md`](../04_docs/01_readme_template.md) — full template
- [`04_docs/03_env-vars-and-state.md`](../04_docs/03_env-vars-and-state.md) — env/state surface
- [`03_interface/04_skills/SKILL.md`](../03_interface/04_skills/SKILL.md) — skill leaves spec
