---
description: |
  [TOPIC] Skills Skill Md As Index
  [DETAILS] SKILL.md is an index file only — frontmatter (name, description, tags, allowed-tools, primary_interface, interfaces), one-line interface header, prose intro, "Installation & import" snippet, and grouped links to numbered leaves. Substantive content goes in focused leaf files. Includes the converged template (>70% adoption across the ecosystem) and per-leaf authoring rules.
tags: [scitex-general-interface-skills-skill-md-as-index]
---

# SKILL.md as Index, Sub-skills as Leaves

SKILL.md is an **index file only**. Content goes in focused sub-skill files. The shape below was extracted from the 12-package audit — every block matches a pattern adopted by ≥10 packages.

## Converged SKILL.md template

```markdown
---
name: scitex-io
description: Universal scientific file I/O supporting 30+ formats. Use when loading or saving data.
tags: [scitex-io, scitex-package]
allowed-tools: mcp__scitex__io_*
primary_interface: python
interfaces:
  python: 3
  cli: 2
  mcp: 2
  skills: 3
  hook: 0
  http: 0
---

# scitex-io

> **Interfaces:** Python ⭐⭐⭐ · CLI ⭐⭐ · MCP ⭐⭐ · Skills ⭐⭐⭐ · Hook — · HTTP —

Universal scientific data I/O with plugin registry.

## Installation & import

```bash
pip install scitex-io
```

```python
import scitex_io as sio
```

## Sub-skills

### Core (01–09)
- [01_quick-start.md](01_quick-start.md) — 30-second tour
- [02_python-api.md](02_python-api.md) — `save()`, `load()`, registry
- [03_cli-reference.md](03_cli-reference.md) — `scitex-io` subcommands
- [04_mcp-tools.md](04_mcp-tools.md) — `io_save`, `io_load` tools

### Features (10–19)
- [10_supported-formats.md](10_supported-formats.md) — All 30+ format tables
- [11_centralized-config.md](11_centralized-config.md) — `load_configs()`, DotDict

### Meta (20+)
- [20_env-vars.md](20_env-vars.md) — `SCITEX_IO_*` environment variables
```

(See [04_numbered-prefix-convention.md](04_numbered-prefix-convention.md) for the standard-5 leaf set every package should ship.)

## Sub-skill (leaf) template

Each leaf covers one feature with actual code examples:

```markdown
---
name: save-and-load
description: Core save/load API with two-tier format registry.
tags: [scitex-io, scitex-package]
---

# Save and Load

## save()

```python
def save(obj, path, makedirs=True, ...):
    ...
```

[Actual function signature, parameters, behavior]

### Auto path routing

[Table showing context → output directory]

### use_caller_path

[When and why to use it, with before/after examples]

## load()

[Same pattern — signature, examples, edge cases]
```

**Rules for sub-skill files:**
1. Cover main features of that topic
2. Include actual code examples (not just descriptions)
3. Verify all claims against source code
4. Be consistent with README and Read the Docs

## Size Limits

- SKILL.md: ≤ ~6 KB / ~120 lines (index discipline; bumped 2026-05 from 4 KB / 80 lines to fit structured 3W1H frontmatter)
- Each leaf: ≤ ~10 KB / ~200 lines, one focused topic per file

If a leaf exceeds 10 KB, split it. If SKILL.md exceeds 120 lines, the content has leaked from a leaf back into the index — promote it to a new leaf.

## Cross-references

- [04_numbered-prefix-convention.md](04_numbered-prefix-convention.md) — leaf naming + standard-5 set
- [05_frontmatter-metadata.md](05_frontmatter-metadata.md) — every frontmatter field explained
- [13_standard-template.md](13_standard-template.md) — copy-paste scaffold matching this template
- [12_quality-checklist.md](12_quality-checklist.md) — release-gate verification
