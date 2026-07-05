---
description: |
  [TOPIC] Interface Cli Example
  [DETAILS] SciTeX CLI reference shape — canonical top-level help output that conforms to §1 (noun groups + sub-verbs, compound leaves, no bare transitive leaves).
tags: [scitex-general-interface-cli-example]
---

# Reference example — canonical shape

The example below shows the **target shape** for a SciTeX package CLI that fully conforms to §1. The current `scitex-plt` / `figrecipe` CLI still uses bare-verb leaves (`plot`, `validate`, `extract`, `compose`, …) at top level — those are §1 anti-patterns and are tracked for migration in [TODO.md](TODO.md).

```
$ scitex-plt
Usage: scitex-plt [OPTIONS] COMMAND [ARGS]...

  FigRecipe — reproducible, style-editable scientific figures via YAML recipes.

Options:
  -V, --version     Show version and exit.
  --help-recursive  Show help for all commands.
  -h, --help        Show this message and exit.

Figure (noun group):
  figure create        Create a figure from a declarative YAML/JSON spec.
  figure reproduce     Reproduce a figure from a YAML recipe.
  figure compose       Compose multiple figures into one.
  figure extract       Extract plotted data arrays from a recipe.
  figure validate      Validate that a recipe reproduces its original figure.
  figure show          Show information about a recipe.

Image (noun group):
  image convert        Convert between figure formats.
  image crop           Crop an image to its content area.
  image diff           Compare two images and report pixel differences.
  image hitmap         Generate hitmap visualization from two images.

Diagram (noun group):
  diagram create       Create a diagram from a spec (flowchart, pipeline, etc.).
  diagram render       Render a diagram to an image.
  diagram list         List available diagrams.

Style & font (noun groups):
  style list           List available style presets.
  style show           Show a style preset.
  style apply          Apply a style preset to a figure.
  font list            List available fonts.
  font check           Verify a font is installed and usable.

GUI (noun group, lifecycle):
  gui start            Launch interactive GUI editor.
  gui stop             Stop the running GUI editor.

MCP (noun group):
  mcp start                MCP (Model Context Protocol) server.
  mcp doctor               Self-diagnose the MCP install.
  mcp list-tools           Enumerate registered MCP tools (-v|-vv|-vvv, --json).
  mcp show-installation    Print snippet for Claude Code / MCP-host config.

Reference (noun groups):
  docs list                List package documentation pages.
  docs show                Show a documentation page.
  docs search              Search documentation.
  skills list              List package skills.
  skills show              Show a skill page.
  skills search            Search skills.

Top-level compound leaves (verb-noun, no group):
  list-python-apis            List public Python APIs (-v|-vv|-vvv, --json).
  install-shell-completion    Install shell completion script (--shell bash).
  print-shell-completion      Print shell completion script to stdout.

Single-token exceptions (intransitive verbs):
  doctor               Self-diagnose installation / environment.
```

## Why this shape

- **Every leaf is `<noun> <verb>` or `<verb>-<noun>` compound.** No bare transitive verbs at top level — see §1 [02_subcommand-structure-noun-verb.md](02_subcommand-structure-noun-verb.md).
- **Noun groups (`figure`, `image`, `diagram`, …)** appear when a noun has 3+ sibling verbs. With 1–2 actions a compound leaf (`list-python-apis`) is preferred.
- **No bare `completion` or `version` subcommands.** `--version` is a reserved flag (§1b [04_exceptions.md](04_exceptions.md)); shell-completion is a verb-noun compound (`install-shell-completion`, `print-shell-completion`).
- **`doctor` is the only single-token leaf.** It's an intransitive exception (§1b). `repl` / `shell` are also allowed when the package ships an interactive session; this example doesn't.
- **`mcp list-tools` follows the same `-v|-vv|-vvv` ladder** as `list-python-apis` — see [03_required-introspection-commands.md](03_required-introspection-commands.md).
- **No `kill` / `display` / `rm` / `enumerate`** — synonyms picked from the canonical catalog ([06_noun-verb-catalog.md](06_noun-verb-catalog.md)).

## Auto-generation note

This file should ideally be auto-generated from a real package's `--help-recursive` output, not hand-maintained — see [TODO.md](TODO.md). Hand-written examples drift; generated ones can't.
