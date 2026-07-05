---
description: |
  [TOPIC] scitex-dev linter Installation
  [DETAILS] pip install scitex-dev, optional [mcp] extra; smoke verify with `scitex-dev linter --version`.
tags: [scitex-dev-linter-installation]
---

# Installation

## Standard

```bash
pip install scitex-dev
```

## Optional extras

| Extra | Adds                                          |
|-------|-----------------------------------------------|
| `mcp` | fastmcp (expose linter rules to AI agents)    |
| `all` | every extra above                             |

```bash
pip install 'scitex-dev[mcp]'
```

## Verify

```bash
python -c "from scitex_dev import linter; print(scitex_dev.linter.__version__)"
scitex-dev linter --help
scitex-dev linter list-rules | head
```

## Optional flake8 plugin

`scitex-dev linter` registers a flake8 entry point (`STX`) once installed —
no extra step required.
