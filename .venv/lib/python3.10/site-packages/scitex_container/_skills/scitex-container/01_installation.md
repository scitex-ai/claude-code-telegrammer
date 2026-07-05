---
description: |
  [TOPIC] scitex-container Installation
  [DETAILS] pip install scitex-container; needs apptainer or docker on host; smoke verify host setup.
tags: [scitex-container-installation]
---

# Installation

## Standard

```bash
pip install scitex-container
```

Pure-Python wrapper. The package shells out to **either** Apptainer/
Singularity **or** Docker — at least one runtime must be on PATH for
the matching surface to work.

## Optional MCP extra

```bash
pip install 'scitex-container[mcp]'   # exposes 14 MCP tools to AI agents
```

Installs `fastmcp` and registers `scitex-container-mcp` as a separate
console script.

## Umbrella

```bash
pip install scitex            # also exposes import scitex.container
```

`pip install scitex-container` alone does NOT make `import
scitex.container` work — install the umbrella for that form. See
`../../general/02_interface-python-api.md`.

## Host runtime

| Runtime               | Install                                     | Best for     |
|-----------------------|---------------------------------------------|--------------|
| Apptainer/Singularity | `apt install apptainer` / module load       | HPC, SLURM   |
| Docker                | https://docs.docker.com/engine/install/     | Workstations |

## Verify

```bash
python -c "import scitex_container; print(scitex_container.__version__)"
scitex-container --help
scitex-container host check         # detects which runtime is available
```

Expected: a version string, the CLI help, then a host-check report
listing detected runtimes (Apptainer / Singularity / Docker).
