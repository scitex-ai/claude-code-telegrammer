---
description: |
  [TOPIC] Installation
  [DETAILS] pip install scitex-config (no system deps, pure Python). Optional yaml extra brings PyYAML for load_yaml() / yaml-cascade resolution.
tags: [scitex-config-installation]
---

# Installation

## Standard

```bash
pip install scitex-config
```

Pulls only `pyyaml` (for YAML config) and `python-dotenv` (for `load_dotenv()`).
No system deps; pure-Python.

## Verify

```bash
python -c "import scitex_config; print(scitex_config.__version__)"
python -c "from scitex_config import PriorityConfig, get_config, get_paths; print('ok')"
```

## Editable install (development)

```bash
git clone https://github.com/ywatanabe1989/scitex-config
cd scitex-config
pip install -e .
```

## Used by

scitex-config is a foundational dependency — pulled in transitively by most
`scitex-*` packages. You rarely install it standalone unless writing a new
SciTeX package or using its primitives directly.
