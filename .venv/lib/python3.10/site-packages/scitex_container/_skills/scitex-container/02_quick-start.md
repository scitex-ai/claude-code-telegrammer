---
description: |
  [TOPIC] scitex-container Quick Start
  [DETAILS] Smallest example — build an Apptainer SIF from a definition file and run it (HPC-friendly default).
tags: [scitex-container-quick-start]
---

# Quick Start

This package supports both Apptainer/Singularity and Docker. Quick-start
shows **Apptainer** (the HPC-friendly default); Docker examples live in
`16_python-api-docker-host.md` and `04_cli-reference.md`.

## CLI: build a SIF

```bash
scitex-container apptainer build env.def env.sif
scitex-container apptainer status env.sif
scitex-container apptainer verify env.sif
```

`build` invokes `apptainer build` under the hood; `status` reports SIF
metadata; `verify` checks SHA256 against a freeze lock.

## CLI: snapshot the host environment

```bash
scitex-container env snapshot ./snapshots/2026-05-03.yaml
```

Records OS / Python / pip freeze / system package versions for
reproducibility.

## Python: build + freeze

```python
import scitex_container.apptainer as apptainer
from pathlib import Path

apptainer.build(Path("env.def"), Path("env.sif"))
apptainer.freeze(Path("env.sif"), Path("env.lock.yaml"))
apptainer.verify(Path("env.sif"), Path("env.lock.yaml"))
```

## Python: top-level convenience

```python
import scitex_container
scitex_container.env_snapshot("./snapshots/today.yaml")
```

## Next steps

- `04_cli-reference.md` — full CLI subcommand surface
- `13_python-api.md` — apptainer module reference
- `14_python-api-sandbox.md` — writable sandbox workflow
- `15_python-api-builders.md` — SLURM / exec command builders
- `16_python-api-docker-host.md` — Docker + host helpers
