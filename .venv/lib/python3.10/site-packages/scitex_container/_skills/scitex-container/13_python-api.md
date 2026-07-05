---
description: |
  [TOPIC] Python API Reference — apptainer module
  [DETAILS] Python API reference for scitex-container — apptainer module (build/freeze/verify/status, SIF versioning, utilities).
tags: [scitex-container-python-api]
---

# Python API Reference — apptainer module

```python
import scitex_container.apptainer as apptainer
```

See also:
- [03_python-api-sandbox.md](03_python-api-sandbox.md) — sandbox management
- [04_python-api-builders.md](04_python-api-builders.md) — SLURM / exec command builders
- [05_python-api-docker-host.md](05_python-api-docker-host.md) — docker, host, top-level

---

## Build / freeze / verify / status

### build

```python
apptainer.build(
    def_name: str = "scitex-cloud-shared-v0.1.0",
    output_dir: str | Path | None = None,
    force: bool = False,
    sandbox: bool = False,
) -> Path
```

Build an Apptainer SIF or sandbox directory from a `.def` file.
Auto-detects containers dir. Auto-freezes lock files after SIF builds.
Raises `FileNotFoundError` if `.def` not found; `RuntimeError` on build failure.

### freeze

```python
apptainer.freeze(
    sif_path: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Path]
```

Extract pinned versions from a built SIF.
Returns `{"pip": Path, "dpkg": Path, "node": Path}` for available lock files.

### verify

```python
apptainer.verify(
    sif_path: str | Path,
    def_path: str | Path | None = None,
    lock_dir: str | Path | None = None,
) -> dict
```

Verify SIF integrity: SHA256, `.def` origin hash, pip/dpkg lock consistency.
Returns `{"sif": {...}, "def_origin": {...}, "pip_lock": {...}, "dpkg_lock": {...}, "overall": "pass|fail"}`.

### status

```python
apptainer.status(
    containers_dir: str | Path | None = None,
) -> list[dict]
```

List containers and their status (needs_rebuild flag).
Returns list of dicts with keys: `name`, `def_path`, `sif_path`, `sif_size`, `sif_date`, `hash_current`, `hash_stored`, `needs_rebuild`.

---

## SIF versioning

```python
apptainer.list_versions(containers_dir: Path) -> list[dict]
# Each dict: {"version", "path", "size", "date", "active"}

apptainer.get_active_version(containers_dir: Path) -> str | None
# Returns version string from current.sif symlink, or None

apptainer.switch_version(
    version: str,
    containers_dir: Path,
    use_sudo: bool = False,
) -> None

apptainer.rollback(
    containers_dir: Path,
    use_sudo: bool = False,
) -> str
# Returns the version string that is now active

apptainer.deploy(
    source_dir: Path,
    target_dir: Path = Path("/opt/scitex/singularity"),
) -> None
# Copy active SIF + base SIF to target_dir, recreate current.sif symlink

apptainer.cleanup(
    containers_dir: Path,
    keep: int = 3,
) -> list[Path]
# Remove old scitex-v*.sif files; never removes active version or base images
```

---

## Utilities

```python
apptainer.detect_container_cmd() -> str
# Returns "apptainer" or "singularity"; raises FileNotFoundError if neither found

apptainer.find_containers_dir() -> Path
# Auto-detects containers directory by walking up from cwd
```
