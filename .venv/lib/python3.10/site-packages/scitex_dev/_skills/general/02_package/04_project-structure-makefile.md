---
description: |
  [TOPIC] Package Makefile
  [DETAILS] Makefile + `./scripts/makefile/` pattern for a SciTeX package. The root Makefile is a thin one-line dispatcher per target; the actual logic lives as standalone shell scripts under `./scripts/makefile/`. Each script is independently runnable from the shell, testable in isolation, and easy to share across repos via symlink. Canonical target inventory (install / test-changed / test-full / coverage-html / lint / clean / build / upload-pypi-test / upload-pypi / release / docs).
tags: [scitex-general-package-project-structure-makefile]
---

# `./scripts/makefile/` — Makefile target backing scripts

> Sibling leaves: [`./root`](01_project-structure-root.md) · [`./src`](02_project-structure-src.md) · [`./scripts`](03_project-structure-scripts.md) · [`./examples`](05_project-structure-examples.md) · [`./tests`](06_project-structure-tests.md)

## The pattern

The root `Makefile` is a thin dispatcher; each target's actual logic lives as **one script per target** under `./scripts/makefile/`:

```
./scripts/makefile/
├── install.sh
├── test-changed.sh
├── test-full.sh
├── coverage-html.sh
├── lint.sh
├── clean.sh
├── build.sh
├── upload-pypi-test.sh
├── upload-pypi.sh
├── release.sh
└── docs.sh
```

Root `Makefile`:

```make
.PHONY: install test-changed test-full coverage-html lint clean build \
        upload-pypi-test upload-pypi release docs

install:           ; @./scripts/makefile/install.sh
test-changed:      ; @./scripts/makefile/test-changed.sh
test-full:         ; @./scripts/makefile/test-full.sh
coverage-html:     ; @./scripts/makefile/coverage-html.sh
lint:              ; @./scripts/makefile/lint.sh
clean:             ; @./scripts/makefile/clean.sh
build:             ; @./scripts/makefile/build.sh
upload-pypi-test:  ; @./scripts/makefile/upload-pypi-test.sh
upload-pypi:       ; @./scripts/makefile/upload-pypi.sh
release:           ; @./scripts/makefile/release.sh
docs:              ; @./scripts/makefile/docs.sh
```

## Why

- Each target is independently runnable from the shell — `./scripts/makefile/test-full.sh` works without `make` involved.
- Each target is testable in isolation (the script is just bash).
- Easy to share between repos — symlink one canonical script across multiple projects.
- The Makefile stops growing into a 200-line shell program inlined inside `make` recipes.
- Same script can be invoked manually for debugging without going through `make` (no quoting/escaping headaches).

## Canonical target inventory

| Target | What it does |
| :--- | :--- |
| `install` | Install the package + dev deps (`pip install -e '.[dev]'`) |
| `test-changed` | pytest only on files changed vs `develop` |
| `test-full` | Full pytest suite (slow; CI-only) |
| `coverage-html` | Coverage report to `./tests/coverage/` |
| `lint` | ruff / shellcheck / etc. |
| `clean` | Remove `build/`, `__pycache__/`, `tests/coverage/`, etc. |
| `build` | Build wheel + sdist into `./dist/` |
| `upload-pypi-test` | Twine upload to TestPyPI |
| `upload-pypi` | Twine upload to PyPI |
| `release` | Version bump + tag + push (+ optionally GitHub release) |
| `docs` | Build Sphinx HTML and refresh `src/<pkg>/_sphinx_html/` (see [02_package/01_project-structure-root.md](01_project-structure-root.md#production-served-sphinx-html--bundled-in-srcpkg_sphinx_html)) |

## Script template

Use the project's standard bash template (see ywatanabe's `~/.claude/skills/ywatanabe/03_project-structure/04_shell-script-template.md`):

```bash
#!/bin/bash
# -*- coding: utf-8 -*-
# Timestamp: <auto-managed>
# File: ./scripts/makefile/test-full.sh

set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(realpath "$THIS_DIR/../..")"

main() {
    cd "$ROOT_DIR"
    pytest tests/ -v
}

main "$@" 2>&1 | tee "./tests/logs/$(basename "$0").log"
```

## When NOT to dispatch

If a target is genuinely a one-line make recipe (`@echo "hello"`), inline it. The `scripts/makefile/<target>.sh` indirection earns its keep when the target has at least 5 lines of actual logic.
