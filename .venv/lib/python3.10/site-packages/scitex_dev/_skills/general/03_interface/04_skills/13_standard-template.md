---
description: |
  [WHAT] The scaffold template every new SciTeX package should start from
  — full SKILL.md plus the standard-7 leaf set (01_installation,
  02_quick-start, 03_python-api, 04_cli-reference, 05_mcp-tools,
  06_http-api, 20_env-vars).
  [WHEN] Authoring a new package's `_skills/<pip-name>/` tree.
  [HOW] Copy the templates below by hand, or run
  `scitex-dev skills init --package <name>` once shipped.
tags: [scitex-general-interface-skills-standard-template]
---

# Standard `_skills/<pip-name>/` Scaffold

## How to scaffold

```bash
scitex-dev skills init --package my-package [--dest src/my_package/_skills/]
```

Status: the `skills init` CLI is planned (see [TODO.md](TODO.md)). It will scaffold the layout below. Until shipped, copy the templates by hand.

## Files created

```
src/<import_name>/_skills/<pip-name>/
  SKILL.md                  # mandatory — index + overview intro
  01_installation.md        # mandatory
  02_quick-start.md         # mandatory
  03_python-api.md          # conditional: package exposes Python API
  04_cli-reference.md       # conditional: [project.scripts] ships an entry
  05_mcp-tools.md           # conditional: MCP server entry-point present
  06_http-api.md            # conditional: package ships HTTP routes
  20_env-vars.md            # conditional: source reads any SCITEX_<MOD>_* env var
```

Add `10–19` workflows and optional `07_examples.md`, `08_troubleshooting.md`, `21_config.md`, `22_logging.md`, `30–39` architecture, `40–49` lessons as needed. See [04_numbered-prefix-convention.md](04_numbered-prefix-convention.md).

## Template — `SKILL.md`

```markdown
---
name: <pip-name>
description: |
  [WHAT] <verb-phrase describing what the package does>.
  [WHEN] <trigger condition>.
  [HOW] <primary entry point — e.g., `import <import_name>` or `<pip-name> --help`>.
tags: [scitex-<pkg>]
allowed-tools: mcp__<import_name>__*
primary_interface: python
interfaces:
  python: 3
  cli: 2
  mcp: 2
  skills: 3
  http: 0
---

# <pip-name>

<one-paragraph overview — this is the SKILL.md intro. Lives here, not in a separate `00_overview.md` file.>

## Sub-skills

### Core (01–09)
- [01_installation.md](01_installation.md) — install + import sanity check
- [02_quick-start.md](02_quick-start.md) — 30-second tour
- [03_python-api.md](03_python-api.md) — Python API surface
- [04_cli-reference.md](04_cli-reference.md) — CLI subcommands

### Meta (20+)
- [20_env-vars.md](20_env-vars.md) — Environment variables
```

Drop `allowed-tools` if no MCP server ships. Drop interface lines for unused channels.

## Template — `01_installation.md`

```markdown
---
description: |
  [TOPIC] Installation
  [DETAILS] pip install <pip-name>; verify with `python -c "import <import_name>"`.
tags: [scitex-<pkg>-installation]
---

# Installation

\`\`\`bash
pip install <pip-name>
\`\`\`

System requirements: Python ≥ 3.11.
```

## Template — `02_quick-start.md`

```markdown
---
description: |
  [TOPIC] Quick Start
  [DETAILS] Smallest useful example demonstrating the primary use case in under 30 seconds.
tags: [scitex-<pkg>-quick-start]
---

# Quick Start

\`\`\`python
import <import_name>
# <smallest useful example>
\`\`\`
```

## Template — `03_python-api.md`

```markdown
---
description: |
  [TOPIC] Python API
  [DETAILS] Public Python API of <pip-name> — exported functions, signatures,
  return types, and minimal usage examples per function.
tags: [scitex-<pkg>-python-api]
---

# Python API

\`\`\`python
from <import_name> import <fn_a>, <fn_b>
\`\`\`

## <fn_a>(arg1, arg2=default) -> ReturnType

[Example, expected output, edge cases.]
```

## Template — `04_cli-reference.md`

```markdown
---
description: |
  [TOPIC] CLI Reference
  [DETAILS] <pip-name> CLI subcommands — noun-verb structure with universal flags.
tags: [scitex-<pkg>-cli-reference]
---

# CLI Reference

\`\`\`bash
<pip-name> --help
\`\`\`

| Command | Purpose |
|---|---|
| `<pip-name> <noun> <verb>` | <one-line> |

See `general/03_interface/02_cli/`.
```

## Template — `05_mcp-tools.md`

```markdown
---
description: |
  [TOPIC] MCP Tools
  [DETAILS] MCP tools registered by <pip-name> — agent-callable surface.
tags: [scitex-<pkg>-mcp-tools]
---

# MCP Tools

| Tool | Purpose |
|---|---|
| `<module>_<verb>_<noun>` | <one-line> |

See `general/03_interface/03_mcp/`.
```

## Template — `20_env-vars.md`

```markdown
---
description: |
  [TOPIC] Environment Variables
  [DETAILS] SCITEX_<MODULE>_* variables read by <pip-name>; defaults and effects.
tags: [scitex-<pkg>-env-vars]
---

# Environment Variables

| Name | Default | Purpose |
|---|---|---|
| `SCITEX_<MODULE>_<NAME>` | `<default>` | <one-line> |

See `general/01_ecosystem/04_environment-variables.md`.
```

## Cross-references

See [03_skill-md-as-index.md](03_skill-md-as-index.md), [04_numbered-prefix-convention.md](04_numbered-prefix-convention.md), [05_frontmatter-metadata.md](05_frontmatter-metadata.md), [12_quality-checklist.md](12_quality-checklist.md).
