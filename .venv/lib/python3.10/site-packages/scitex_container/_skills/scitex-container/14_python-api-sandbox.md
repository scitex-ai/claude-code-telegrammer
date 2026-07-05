---
description: |
  [TOPIC] Python API Reference — sandbox
  [DETAILS] Python API reference for scitex-container — apptainer sandbox management & versioning.
tags: [scitex-container-python-api-sandbox]
---

# Python API Reference — sandbox

```python
import scitex_container.apptainer as apptainer
```

---

## Sandbox management

```python
apptainer.sandbox_create(
    source: str | Path,
    containers_dir: str | Path | None = None,
    *,
    output_dir: str | Path | None = None,
) -> Path
# Creates sandbox-YYYYMMDD_HHMMSS/ and updates current-sandbox symlink

apptainer.is_sandbox(path: str | Path) -> bool
# True if path does NOT end with .sif

apptainer.sandbox_maintain(
    sandbox_dir: str | Path,
    command: list[str],
) -> int
# Run command inside sandbox with --writable --fakeroot; returns exit code

apptainer.sandbox_update(
    sandbox_dir: str | Path,
    *,
    proj_root: str | Path | None = None,  # default: ~/proj
    packages: tuple[str, ...] | None = None,  # default: all ecosystem packages
    install_deps: bool = False,
) -> dict[str, str]
# Returns {"pkg_name": "ok|failed|skipped", ...}
# Default packages: scitex, figrecipe, scitex-writer, scitex-dataset,
#                   crossref-local, openalex-local, socialia, scitex-linter, scitex-container

apptainer.sandbox_to_sif(
    sandbox_dir: str | Path,
    output_sif: str | Path,
) -> Path

apptainer.sandbox_configure_ps1(
    sandbox_dir: str | Path,
    default_ps1: str = r"\W $ ",
) -> None
# Writes PS1 to .singularity.d/env/90-environment.sh
# Override at runtime: apptainer exec --env SCITEX_CLOUD_APPTAINER_PS1='(mylab) \W $ '
```

---

## Sandbox versioning

```python
apptainer.list_sandboxes(containers_dir: Path) -> list[dict]
# Each dict: {"version": "YYYYMMDD_HHMMSS", "path", "date", "active"}

apptainer.get_active_sandbox(containers_dir: Path) -> str | None
# Returns timestamp from current-sandbox symlink, or None

apptainer.switch_sandbox(
    version: str,          # timestamp string e.g. "20260225_173700"
    containers_dir: Path,
    use_sudo: bool = False,
) -> None

apptainer.rollback_sandbox(
    containers_dir: Path,
    use_sudo: bool = False,
) -> str
# Returns timestamp of now-active sandbox

apptainer.cleanup_sandboxes(
    containers_dir: Path,
    keep: int = 5,
) -> list[Path]

apptainer.cleanup_sifs(
    containers_dir: Path,
    keep: int = 0,
) -> list[Path]
# Removes *.sif, *.sif.old, *.sif.backup.*, and current.sif symlink
```
