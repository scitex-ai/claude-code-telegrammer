---
description: |
  [TOPIC] scitex-container Python API
  [DETAILS] Top-level public surface — submodules (apptainer/docker/host), env_snapshot, plus MCP-parity re-exports (build, status, verify, sandbox_create, etc.).
tags: [scitex-container-python-api]
---

# Python API

Top-level public surface re-exported from `scitex_container`.
Detailed per-area docs live in numbered companion leaves (13–16).

## Submodules

| Name        | Purpose                                                |
|-------------|--------------------------------------------------------|
| `apptainer` | Build, freeze, verify, version SIFs; sandbox; SLURM    |
| `docker`    | Compose-aware Docker host helpers                      |
| `host`      | Host runtime detection + install                       |

## Top-level callables

| Name             | Purpose                                                  |
|------------------|----------------------------------------------------------|
| `__version__`    | Installed package version                                |
| `env_snapshot()` | Capture OS / Python / pip-freeze / sys-pkg state to YAML |

## MCP-parity re-exports

These mirror the MCP tool surface so AI agents and Python users see the
same names. They dispatch to the appropriate submodule.

| Name                | Dispatches to                                       |
|---------------------|-----------------------------------------------------|
| `build()`           | `apptainer.build`                                   |
| `build_reproducible()` | `apptainer.build_reproducible`                  |
| `cleanup()`         | `apptainer.cleanup`                                 |
| `deploy()`          | `apptainer.deploy`                                  |
| `list_versions()`   | `apptainer.list_versions`                           |
| `rollback()`        | `apptainer.rollback`                                |
| `status()`          | `apptainer.status`                                  |
| `switch()`          | `apptainer.switch_version`                          |
| `verify()`          | `apptainer.verify`                                  |
| `verify_roundtrip()`| `apptainer.verify_roundtrip`                        |
| `check_verified()`  | `apptainer.check_verified`                          |
| `list_builds()`     | `apptainer.list_builds`                             |
| `sandbox_create()`  | `apptainer.sandbox_create`                          |
| `docker_rebuild()`  | `docker.rebuild`                                    |
| `docker_restart()`  | `docker.restart`                                    |
| `host_check()`      | `host.check_packages`                               |
| `host_install()`    | `host.install_packages`                             |

## Example

```python
import scitex_container as ctr

ctr.host_check()                                            # detect runtimes
ctr.build(def_name="scitex-final", sandbox=False)            # build SIF
ctr.verify(sif_path="/opt/containers/scitex-final.sif")     # integrity check
snap = ctr.env_snapshot()                                   # capture host state
print(snap)
```

## Detailed per-area references

- `13_python-api.md` — `apptainer` build/freeze/verify/status, SIF
  versioning, utilities
- `14_python-api-sandbox.md` — sandbox management & versioning
- `15_python-api-builders.md` — SLURM / exec command builders
- `16_python-api-docker-host.md` — `docker`, `host`, top-level
  `env_snapshot`
