---
description: |
  [TOPIC] Readme Organization
  [DETAILS] Canonical README.md template for every SciTeX package — required section order (one-liner → install → quickstart → interfaces → status/CI badges → links → licence → Four-Freedoms footer), badge set (PyPI version, CI, coverage, RTD, licence), collapsible blocks for long examples, `import scitex` (never `as stx`) in all snippets, absence of the ywatanabe@ signature, and the intra-README link contract that external RTD/Sphinx builds depend on. Use when scaffolding a new repo's README or auditing one for ecosystem drift.
tags: [scitex-general-docs-readme]
---

# README Organization (SciTeX)

## Reference package

When in doubt about any rule on this page, mirror
[**scitex-io**](https://github.com/ywatanabe1989/scitex-io/blob/develop/README.md).
It is the canonical example of every convention here — badge layout,
section ordering, blockquote callouts, mermaid sizing, `<details>`
collapsing, Problem/Solution cell length, hook integration recipe.

## Standard Section Order

Every SciTeX package README follows this structure:

```markdown
# package-name

[Centered SciTeX logo]

**One-line tagline**

[Quick links: Documentation · pip install — centered]

[Badges: PyPI, Docs, Tests, License] ← placed JUST ABOVE the `---`
separator (not under the H1). The header reads top-to-bottom as
identity (logo + tagline + install link) → CI status (badges) → content.

---

## Problem and Solution                ← one combined H2; table layout
<details><summary>Supported Formats / Feature Table</summary></details>
## Quick Start                          ← top-level, tight runnable demo
## Installation                         ← one `uv pip install pkg[all]` line
## How it works (or `## Architecture`)  ← subsections explaining design;
                                          one diagram total is enough
                                          (see PS-141 / PS-142 below)
## <N> Interfaces (Python · CLI · MCP · Skills · HTTP optional)
  ← All four interface blocks MAY be collapsed `<details>` — no longer
    required to have at least one `<details open>` (PS-131 relaxed).
    NO standalone `## Modules` H2 either (PS-132; duplicates autoapi
    and drifts).
## Lint Rules (if applicable)
## Claude Code Integration as a Hook (if applicable)
## Part of SciTeX

**Required first paragraph** (one standardized line):

> `<package>` is part of [**SciTeX**](https://scitex.ai). Install via
> the umbrella with `pip install scitex[<extra>]` to use as
> `scitex.<module>` (Python) or `scitex <subcommand> ...` (CLI).

Replace `<package>`, `<extra>`, `<module>`, `<subcommand>` per package.
Do NOT use the older `> **SciTeX users**: ...` blockquote form (drifts;
inconsistent across the ecosystem).

[Optional `import scitex` snippet — ONLY include if it demonstrates
 **synergy via the umbrella**: an advantage you only get when combined
 with OTHER scitex packages through `import scitex`. Concretely, the
 snippet must touch at least TWO scitex modules and the combination must
 produce a meaningful result the standalone package cannot.

 Examples of valid synergy:
   import scitex as stx
   data = stx.io.load("session.npy")          # scitex-io
   fig, ax = stx.plt.subplots()               # scitex-plt
   ax.plot(data)
   stx.io.save(fig, "out.png")                # plt → io round-trip

 NOT synergy (skip the snippet entirely):
   import scitex
   scitex.ssh.setup(2222, ...)                # same call as scitex_ssh.setup
                                              # — different alias, no benefit

 If your package has no umbrella synergy yet, omit the snippet and ship
 only the Four Freedoms blockquote. Don't fabricate a single-module
 example just to fill the section.]
[Four Freedoms blockquote — always present]

---

[Centered SciTeX icon footer]

```

## Presentation conventions (adopted 2026-05)

### Quick Start (top-level H2)

A `## Quick Start` H2 sits between **Problem and Solution** and
**Installation**. It contains one tight runnable code block (≈10–25
lines) demonstrating the package's primary value, with a round-trip
assertion if applicable. This replaces the old role of the primary
`<details open>` interface block. With Quick Start present, every
interface inside `## <N> Interfaces` can be collapsed (PS-131 relaxed).

### Installation (one-liner)

```markdown
## Installation

```bash
uv pip install "<pkg>[all]"
```
```

No prose. The per-module extras matrix goes inside a `<details>`
collapsible directly below. Drop redundant explanations of why `uv` is
faster than `pip`; users either know or follow the link.

### How it works (numbered subsections)

`## How it works` (or the older `## Architecture` — both are accepted
by the auditor, PS-142) breaks into `### 1.`, `### 2.`, `### 3.`
subsections, each focused on one design choice. Use one mermaid
diagram between Demo and Architecture/How-it-works — the "one diagram
is enough" rule (PS-141 visual-anywhere). Mermaid init config keeps
the diagram compact:

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 20, 'rankSpacing': 40, 'curve': 'linear'}, 'themeVariables': {'fontSize': '12px'}}}%%
```

### Blockquote (`>`) callouts for high-signal asides

Use `>` to set apart rules, edge cases, opt-in extras, and "watch out"
notes. Every continuation line must carry the `>` prefix so markdown
renders one connected callout (not a broken-multi-line quote):

```markdown
> **Absolute paths bypass routing.** `sio.save(df, "/data/x.csv")`
> writes to `/data/x.csv` as-is — caller-anchored routing (§2) only
> applies when the path is relative.
```

### Problem and Solution: one sentence per cell

The `## Problem and Solution` table cells must each be a single
sentence (≤ 200 chars per cell, PS-144). Drop trailing examples and
"impossible to track" amplifications — the table is a scannable
summary, not an essay.

| # | Problem | Solution |
|---|---|---|
| 1 | **Format zoo** — every format has its own API. | **One call** dispatches across 30+ formats. |

<!-- hook-bypass: line-limit (file pre-existing over MD cap; see GITIGNORED/REFACTORING.md) -->

### Badge row — canonical SAC layout (PS-167)

Mirrors `scitex-agent-container/README.md`. Header order: H1 (with
`<code>pkg-name</code>`) → centered logo → centered **tagline**
(`<p align="center"><b>...</b></p>`) → centered Full-Doc + install
line → badge block. PS-167 enforces four rules on the badge block:

1. Wrapped in `<!-- scitex-badges:start -->` … `<!-- scitex-badges:end -->`
   markers (markers OUTSIDE the `<p>` tags — never nested inside).
2. Exactly **two** `<p align="center">` rows: row 1 = metadata
   (`pypi`, `python`, `docs`); row 2 = CI/health (`tests`,
   `install-check`, `quality`, `cov`).
3. Every image served from `img.shields.io/...` (raw
   `actions/.../badge.svg`, `readthedocs.org/.../badge`,
   `badge.fury.io` are rejected — shields.io is required so each
   badge can carry `?label=<short>`).
4. Short labels from PS-166's vocabulary; metadata row uses at least
   one of `pypi`/`python`/`docs`, CI row uses at least one of
   `tests`/`install-check`/`quality`/`cov`.

```html
<!-- scitex-badges:start -->
<p align="center">
<a href="https://pypi.org/project/<pkg>/"><img src="https://img.shields.io/pypi/v/<pkg>?label=pypi" alt="pypi"></a>
<a href="https://pypi.org/project/<pkg>/"><img src="https://img.shields.io/pypi/pyversions/<pkg>?label=python" alt="python"></a>
<a href="https://github.com/<owner>/<pkg>/actions/workflows/rtd-sphinx-build-on-ubuntu-latest.yml"><img src="https://img.shields.io/github/actions/workflow/status/<owner>/<pkg>/rtd-sphinx-build-on-ubuntu-latest.yml?branch=develop&label=docs" alt="docs"></a>
</p>
<p align="center">
<a href="https://github.com/<owner>/<pkg>/actions/workflows/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml"><img src="https://img.shields.io/github/actions/workflow/status/<owner>/<pkg>/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml?branch=develop&label=tests" alt="tests"></a>
<a href="https://github.com/<owner>/<pkg>/actions/workflows/import-smoke-on-ubuntu-py3-12.yml"><img src="https://img.shields.io/github/actions/workflow/status/<owner>/<pkg>/import-smoke-on-ubuntu-py3-12.yml?branch=develop&label=install-check" alt="install-check"></a>
<a href="https://github.com/<owner>/<pkg>/actions/workflows/scitex-dev-quality-audit-on-ubuntu-latest.yml"><img src="https://img.shields.io/github/actions/workflow/status/<owner>/<pkg>/scitex-dev-quality-audit-on-ubuntu-latest.yml?branch=develop&label=quality" alt="quality"></a>
<a href="https://codecov.io/gh/<owner>/<pkg>"><img src="https://img.shields.io/codecov/c/github/<owner>/<pkg>/develop?label=cov" alt="cov"></a>
</p>
<!-- scitex-badges:end -->
```

Drop the AGPL license badge — already in `pyproject.toml` metadata
and visible on PyPI.

#### Badge label convention: shields.io with explicit `?label=...`

Workflow filenames are deliberately descriptive
(`pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml`), which makes the
default GitHub Actions badge text unreadable. Use **shields.io's
`github/actions/workflow/status` endpoint with an explicit `?label=`
short label**. The badge URL keys on the filename (long, descriptive);
the short label keys on shields.io (so the rendered badge stays
scannable). Example:

```html
<a href="https://github.com/<owner>/<repo>/actions/workflows/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml">
  <img src="https://img.shields.io/github/actions/workflow/status/<owner>/<repo>/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml?branch=develop&label=tests"
       alt="tests">
</a>
```

Apply the same pattern to every workflow badge (`label=install`,
`label=docs`, `label=audit`, …). Do NOT rename the workflow file to
match the short label — the descriptive filename is required by PS-164
for the GitHub Actions UI; the README badge label is purely cosmetic.

### Claude Code Integration as a Hook (optional)

If the package ships lint rules, add a `## Claude Code Integration as
a Hook` section after `## Lint Rules`. Ship the hook script at
`examples/<pkg>_lint.sh` (self-contained — no dependency on the
maintainer's dotfiles). Include `settings.json` snippet that wires it
to `PostToolUse` with matcher `Edit|Write|MultiEdit`. See
[scitex-io's hook](https://github.com/ywatanabe1989/scitex-io/blob/develop/examples/scitex_io_lint.sh)
for the template.

### Interface ratings (`⭐`)

Star ratings are **required** on every interface summary (drop only
the trailing parenthetical tags like `— for AI Agents` /
`— for AI Agent Discovery`, PS-118). Use 1–3 stars per interface
reflecting its primacy:

```markdown
<details>
<summary><strong>Python API ⭐⭐⭐</strong></summary>
```

The deprecated `> **Interfaces:** ...` callout at the top of SKILL.md
files is forbidden (PS-116) — stars belong on summaries only.

## Badge Row (SciTeX Style)

```markdown
<p align="center">
  <a href="https://badge.fury.io/py/PACKAGE"><img src="https://badge.fury.io/py/PACKAGE.svg" alt="PyPI version"></a>
  <a href="https://PACKAGE.readthedocs.io/"><img src="https://readthedocs.org/projects/PACKAGE/badge/?version=latest" alt="Documentation"></a>
  <a href="https://github.com/ywatanabe1989/PACKAGE/actions/workflows/ci.yml"><img src="https://github.com/ywatanabe1989/PACKAGE/actions/workflows/ci.yml/badge.svg" alt="Tests"></a>
  <a href="https://www.gnu.org/licenses/agpl-3.0"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License: AGPL-3.0"></a>
</p>
```

## Interface sections (collapsible)

The README's `## <N> Interfaces` section contains one `<details>` block
per interface. Star ratings live on the `<summary>` (not in a separate
callout); strip parenthetical expansions and `-- for AI Agents` /
`— for AI Agent Discovery` tails (audit rule **PS-118**).

**All blocks may be collapsed** (`<details>` without `open`). The
historical requirement to mark at least one as `<details open>` is no
longer enforced (audit rule **PS-131** relaxed). Optionally still mark
the primary as `<details open>` when its example doubles as a
quick-start and the package omits a top-level `## Quick Start`
section — but most packages now ship a top-level `## Quick Start`
that carries that role, so every interface block stays collapsed.

```markdown
<details>
<summary><strong>Python API ⭐⭐⭐</strong></summary>
[Minimal `import <pkg>` example, 3-10 lines]
> **[Full API reference](<deeplink>)**
</details>

<details>
<summary><strong>CLI Commands ⭐⭐</strong></summary>
[Minimal command examples]
> **[Full CLI reference](<deeplink>)** · run `<pkg> --help-recursive` for the live tree.
</details>

<details>
<summary><strong>MCP Server ⭐⭐</strong></summary>
[Tool table + `<pkg> mcp start`]
> **[Full MCP specification](<deeplink>)** · run `<pkg> mcp list-tools` for the live registry.
</details>

<details>
<summary><strong>Skills ⭐</strong></summary>
[Skill table + `<pkg> skills list`]
> **[Full skills directory](https://github.com/ywatanabe1989/<pkg>/tree/develop/src/<import>/_skills/<pkg>)**
</details>
```

Star ratings are **required** on every interface summary (PS-120) —
they signal which interface is the package's primary user surface.
Drop only the trailing parenthetical tags like
`— for AI Agents` / `— for AI Agent Discovery` (PS-118); keep the
stars.

> **Reference package: `scitex-io`** — the canonical example of every
> rule on this page. When in doubt, mirror its README structure, badge
> layout, section ordering, blockquote-callout style, mermaid sizing,
> `<details>` collapsing, and Problem/Solution cell length.

### Canonical "Full X reference" deep-link patterns

Each `Full X` link **must** be a deep-link, not a bare RTD root URL
(audit rule **PS-123**). The deep-link points into the bundled
`_sphinx_html/` (also surfaced via Read the Docs):

| Interface  | Canonical deep-link                                                          |
|------------|------------------------------------------------------------------------------|
| Python API | `https://<pkg>.readthedocs.io/en/latest/api/<import_name>.html`              |
| CLI        | `https://<pkg>.readthedocs.io/en/latest/quickstart.html` (or dedicated page) |
| MCP        | `https://<pkg>.readthedocs.io/en/latest/api/<import_name>._mcp.html`         |
| Skills     | `https://github.com/ywatanabe1989/<pkg>/tree/develop/src/<import>/_skills/<pkg>` |

Skills point at the source tree on GitHub (not RTD) because skill
markdown is consumed by AI agents that follow the directory structure
directly.

### Future: `scitex-dev readme refresh` (planned)

The interface block bodies (code examples + tool tables + skill tables)
should eventually be auto-generated between markers like
`<!-- scitex-api:start --> ... <!-- scitex-api:end -->`. The generator
will call `scitex_dev.introspect.api(<pkg>)`, `<pkg> --help-recursive`,
`<pkg> mcp list-tools`, and `ls _skills/<pkg>/` — so the README can't
drift from reality. Tracked under scitex-dev TODO.

## Four Freedoms Footer

```markdown
## Part of SciTeX

PACKAGE is part of [**SciTeX**](https://scitex.ai).

>Four Freedoms for Research
>
>0. The freedom to **run** your research anywhere — your machine, your terms.
>1. The freedom to **study** how every step works — from raw data to final manuscript.
>2. The freedom to **redistribute** your workflows, not just your papers.
>3. The freedom to **modify** any module and share improvements with the community.
>
>AGPL-3.0 — because we believe research infrastructure deserves the same freedoms as the software it runs on.

---

<p align="center">
  <a href="https://scitex.ai" target="_blank"><img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40"/></a>
</p>

```

## SciTeX-Specific Rules

- **No `ywatanabe@scitex.ai`** in footer — community project (audit: **PS-111**)
- **`import scitex`** and **`import scitex as stx`** are both acceptable
  in code blocks; pick one and stay consistent within a single README.
  (Reality: the umbrella canonical README and most skill docs use `as stx`;
  earlier guidance forbidding `as stx` was inconsistent with practice.)
- **Verify all format/feature claims** against actual `_builtin_handlers.py` or source code
- **Match quickstart.rst** — README Quickstart and Sphinx quickstart should show the same examples
- **Add Logo and Icon** — either `docs/assets/images/{scitex-logo-blue-cropped.png,scitex-icon-navy-inverted.png}`
  or `docs/{scitex-logo-blue-cropped.png,scitex-icon-navy-inverted.png}`
  is accepted (audit: **PS-112** for the top logo).

## Canonical Template + Audit Rules

The literal canonical README lives at
[`04_docs/01_readme_template.md`](01_readme_template.md).
Run `scitex-dev ecosystem audit-project <pkg>` to check a repo against
the template. The following warn-only rules enforce its load-bearing
sections:

| Code  | Enforces                                                            |
|-------|---------------------------------------------------------------------|
| PS-106 | Coverage badge in the first ~4 KB                                   |
| PS-107 | Required H2 sections: `## Installation`, `## Quick Start`, `## Part of SciTeX` |
| PS-109 | PyPI version badge in the first ~4 KB                               |
| PS-110 | Four Freedoms for Research blockquote present                       |
| PS-111 | Banned personal email `ywatanabe@scitex.ai` absent                  |
| PS-112 | SciTeX logo image in the first ~4 KB                                |

---

## Project README.md Examples

### Header

``` markdown
# SciTeX (<code>scitex</code>)

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/assets/images/scitex-logo-blue-cropped.png" alt="SciTeX" width="400">
  </a>
</p>

<p align="center"><b>Python Library for Science. For AI and Human Researchers</b></p>

<p align="center">
  <a href="https://badge.fury.io/py/scitex"><img src="https://badge.fury.io/py/scitex.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/scitex/"><img src="https://img.shields.io/pypi/pyversions/scitex.svg" alt="Python Versions"></a>
  <a href="https://scitex-python.readthedocs.io"><img src="https://readthedocs.org/projects/scitex-python/badge/?version=latest" alt="Documentation"></a>
  <a href="https://github.com/ywatanabe1989/scitex-python/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ywatanabe1989/scitex-python" alt="License"></a>
</p>

<p align="center">
  <a href="https://scitex-python.readthedocs.io">Docs</a> &middot;
  <a href="https://scitex-python.readthedocs.io/en/latest/quickstart.html">Quick Start</a> &middot;
  <a href="https://scitex-python.readthedocs.io/en/latest/api/index.html">API</a> &middot;
  <code>pip install scitex[all]</code>
</p>

---
```

### Problem and Solution

``` markdown
This repository provides `scitex`, the orchestration layer of the SciTeX ecosystem — solving key problems in scientific research:

## Problem and Solution

| # | Problem | Solution |
|---|---------|----------|
| 1 | **Fragmented tools** -- literature search, statistics, figures, and writing each require separate tools with incompatible formats | **Unified toolkit** -- `import scitex as stx` provides 73 modules under one namespace, accessible via Python API, CLI, and MCP. These modules are standalone packages but loosely coupled through a plugin registry — each works on its own, yet composes into designed synergy (save a figure → auto-exports CSV + YAML recipe → hash-tracked by Clew → citeable in scitex-writer). |
| 2 | **No verification** -- existing tools address whether work *could* be reproduced, not whether it *has* been verified | **Cryptographic verification** -- Clew builds SHA-256 hash-chain DAGs linking every manuscript claim back to source data |
| 3 | **AI agents lack context** -- general-purpose LLMs cannot operate across the full research lifecycle without domain-specific tools | **323 MCP tools** -- AI agents run statistics, create figures, search literature, and compile manuscripts through structured tool calls |
| 4 | **No custom tooling** -- every lab needs domain-specific tools, but building and sharing them requires deep infrastructure knowledge | **App Maker and Store** -- researchers create custom apps with [scitex-app](https://github.com/ywatanabe1989/scitex-app) SDK and share via [SciTeX Cloud](https://scitex.ai) |
| 5 | **Vendor lock-in** -- cloud research tools (Overleaf, Zotero, Mendeley, Colab, GitHub Copilot) keep data on third-party servers and depend on APIs that can disappear overnight or monetize tomorrow | **Open and self-hostable** -- every SciTeX package is AGPL-3.0; the full 39-package ecosystem runs on your own hardware (or SciTeX Cloud which itself is self-hostable); cloud integrations are pluggable extras, not requirements |
```

### Installation

Every package's README **must** lead the Installation section with
`uv pip install <package>[all]` as the recommended form. uv's parallel
Rust resolver handles the SciTeX dep set in 1-3 min where pip's serial
backtracker can take 30+ min on the full extras. Plain `pip install`
remains supported and SHOULD be shown alongside as the fallback, never
removed. See sibling rule
[02_package/10_dev-venv-isolation.md](../02_package/10_dev-venv-isolation.md)
for the per-package `.venv/` convention this works with.

The umbrella `scitex` README is canonical:

``` markdown
## Installation

```bash
# Recommended — uv resolver (10-30× faster than pip on the full extras set)
uv pip install scitex[all]

# Plain pip — slower (~30-90 min on first install; see Installation Tips)
pip install scitex[all]
```

<details>
<summary><strong>Per-module extras</strong></summary>

```bash
pip install scitex                     # Core only (minimal)
pip install scitex[plt,stats,scholar]  # Typical research setup
pip install scitex[plt]                # Publication-ready figures (figrecipe)
pip install scitex[stats]              # Statistical testing (23+ tests)
pip install scitex[scholar]            # Literature search, PDF download, BibTeX enrichment
pip install scitex[writer]             # LaTeX manuscript compilation
pip install scitex[audio]              # Text-to-speech
pip install scitex[ai]                 # LLM APIs (OpenAI, Anthropic, Google) + ML tools
pip install scitex[dataset]            # Scientific datasets (DANDI, OpenNeuro, PhysioNet)
pip install scitex[browser]            # Web automation (Playwright)
pip install scitex[capture]            # Screenshot capture and monitoring
pip install scitex[cloud]              # Cloud platform integration
```

Requires Python 3.10+. We recommend [uv](https://docs.astral.sh/uv/) for fast installs.
</details>
```

### Quick Start

``` markdown
## Quick Start

<details>
<summary><strong><code>@scitex.session</code> -- Reproducible Experiment Tracking</strong></summary>

One decorator gives you: auto-CLI, YAML config injection, random seed fixation, structured output, and logging.

```python
import scitex as stx
import numpy as np

@stx.session
def main(
    data_path: str = "./data.csv",   # --data-path data.csv
    n_samples: int = 100,            # --n-samples 200
    CONFIG=stx.session.INJECTED,     # Aggregated ./config/*.yaml
    plt=stx.session.INJECTED,        # Pre-configured matplotlib
    logger=stx.session.INJECTED,     # Session logger
):
    """Analyze data. Docstring becomes --help text."""
    
    # Load
    data = stx.io.load(data_path)
    
    # Demo data
    x = np.linspace(0, 2 * np.pi, n_samples)
    y = np.sin(x) + np.random.randn(n_samples) * 0.1
    
    # FigRecipe Plot
    fig, ax = stx.plt.subplots()
    ax.plot(x, y)
    ax.set_xyt("Time", "Amplitude", "Noisy Sine Wave")
    
    # Save sine.png + sine.csv with logging message
    stx.io.save(fig, "sine.png")
    
    return 0

if __name__ == "__main__":
    main()
```

```bash
$ python script.py --data-path experiment.csv --n-samples 200
$ python script.py --help
# usage: script.py [-h] [--data-path DATA_PATH] [--n-samples N_SAMPLES]
# Analyze data. Docstring becomes --help text.
```

```
script_out/FINISHED_SUCCESS/2026-03-18_14-30-00_Z5MR/
├── sine.png, sine.csv         # Figure + auto-exported plot data
├── CONFIGS/CONFIG.yaml        # Frozen parameters
└── logs/{stdout,stderr}.log   # Execution logs
```

The injected `CONFIG` is a `DotDict` merging YAML user configs with session-resolved keys:

| Key | Meaning |
|-----|---------|
| `CONFIG.ID` | Session identifier, e.g. `2026-04-23T21-30-00_Z5MR` |
| `CONFIG.PID` | Python process ID |
| `CONFIG.START_DATETIME` | When the session started |
| `CONFIG.FILE` | Path to caller script |
| `CONFIG.SDIR_OUT` | Base output dir, e.g. `analysis_out/` |
| `CONFIG.SDIR_RUN` | This run's dir, e.g. `analysis_out/FINISHED_SUCCESS/<ID>/` |
| `CONFIG.ARGS` | Parsed CLI args |
| `CONFIG.MODEL.*` | Values from `./config/MODEL.yaml` (one namespace per YAML file) |

Use `CONFIG.SDIR_RUN / "results.csv"` to re-load a file saved earlier in the same session. A frozen copy of `CONFIG` is persisted to `CONFIG.SDIR_RUN/CONFIGS/{CONFIG.yaml,CONFIG.pkl}` so any run is fully auditable. See [25_session-config](./src/scitex/_skills/general/25_session-config.md) for the full reference.
</details>


<details>
<summary><strong><code>scitex.io</code> -- Unified File I/O (50+ Formats)</strong></summary>

```python
import scitex as stx

# Save and load -- format detected from extension.
# symlink_from_cwd=True drops a symlink at cwd so round-trip by filename works;
# without it, save() routes to <script>_out/ and load() must use an absolute path.
stx.io.save(df, "results.csv", symlink_from_cwd=True)
df = stx.io.load("results.csv")

stx.io.save(arr, "data.npy", symlink_from_cwd=True)
arr = stx.io.load("data.npy")

stx.io.save(fig, "figure.png")       # Also exports figure data as CSV
stx.io.save(config, "config.yaml")
stx.io.save(model, "model.pkl")

# Aggregate ./config/*.yaml into a single DotDict
CONFIG = stx.io.load_configs(config_dir="./config")
print(CONFIG.MODEL.hidden_size)      # Dot-notation access

# Register custom formats
@stx.io.register_saver(".custom")
def save_custom(obj, path, **kw):
    with open(path, "w") as f:
        f.write(str(obj))

@stx.io.register_loader(".custom")
def load_custom(path, **kw):
    with open(path) as f:
        return f.read()
```

Supports: CSV, JSON, YAML, TOML, HDF5, NPY, NPZ, PKL, PNG, JPG, SVG, PDF, Excel, Parquet, Zarr, INI, TXT, MAT, WAV, MP3, BibTeX, and more.

**Built-in features**: Auto directory creation, path resolution to `<script_name>_out/`, symlinks (`symlink_from_cwd=True`), save logging with file size, and Clew hash tracking.
</details>

...

</details>
```

### Footer

``` markdown
## Part of SciTeX

scitex-io is part of [**SciTeX**](https://scitex.ai). When used inside the SciTeX framework, I/O is seamless:

```python
import scitex

@scitex.session
def main(CONFIG=scitex.INJECTED):
    data = scitex.io.load("input.csv")     # auto-tracked by clew
    result = process(data)
    scitex.io.save(result, "output.csv")   # auto-tracked by clew
    return 0
```

`scitex.io` delegates to `scitex_io` — they share the same API and registry.

The SciTeX system follows the Four Freedoms for Research below, inspired by [the Free Software Definition](https://www.gnu.org/philosophy/free-sw.en.html):

>Four Freedoms for Research
>
>0. The freedom to **run** your research anywhere — your machine, your terms.
>1. The freedom to **study** how every step works — from raw data to final manuscript.
>2. The freedom to **redistribute** your workflows, not just your papers.
>3. The freedom to **modify** any module and share improvements with the community.
>
>AGPL-3.0 — because we believe research infrastructure deserves the same freedoms as the software it runs on.

---

<p align="center">
  <a href="https://scitex.ai" target="_blank"><img src="docs/assets/images/scitex-icon-navy-inverted.png" alt="SciTeX" width="40"/></a>
</p>

```
