---
description: |
  [TOPIC] scitex-logging Installation
  [DETAILS] pip install scitex-logging (pure Python, stdlib-only); smoke verify with import + getLogger.
tags: [scitex-logging-installation]
---

# Installation

## Standard

```bash
pip install scitex-logging
```

Pure-Python; no required runtime dependencies (built on stdlib `logging`
and `warnings`). Drop-in replacement for the stdlib loggers with extra
SUCCESS / FAIL levels and an exception hierarchy.

## Verify

```bash
python -c "import scitex_logging; print(scitex_logging.__version__)"
python -c "from scitex_logging import getLogger, configure, SciTeXError; print('ok')"
```

## Editable install (development)

```bash
git clone https://github.com/ywatanabe1989/scitex-logging
cd scitex-logging
pip install -e '.[dev]'
```

## Umbrella alternative

```bash
pip install scitex   # exposes scitex.logging as a submodule
```

See SKILL.md for the standalone-vs-umbrella import rule and
[20_env-vars.md](20_env-vars.md) for `SCITEX_LOGGING_LEVEL` and friends.
