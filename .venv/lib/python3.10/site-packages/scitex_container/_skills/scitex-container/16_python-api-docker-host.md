---
description: |
  [TOPIC] Python API Reference — docker, host, top-level
  [DETAILS] Python API reference for scitex-container — docker module, host module, top-level env_snapshot.
tags: [scitex-container-python-api-docker-host]
---

# Python API Reference — docker, host, top-level

```python
import scitex_container.docker as docker
import scitex_container.host as host
from scitex_container import env_snapshot
```

---

## docker module

```python
docker.rebuild(
    env: str = "dev",
    project_dir: str | Path | None = None,
) -> int
# Runs: docker compose -f <compose_file> build --no-cache
# Returns exit code (0 = success)

docker.restart(
    env: str = "dev",
    project_dir: str | Path | None = None,
) -> int
# Runs: docker compose down then docker compose up -d
# Returns exit code of up command

docker.status(
    env: str = "dev",
    project_dir: str | Path | None = None,
) -> dict
# Returns {"compose_file": str, "containers": [{"name", "state", "image", "raw"}], "returncode": int}

docker.get_dev_mounts(repos: list[dict]) -> list[str]
# repos: [{"host": str, "container": str, "mode": "ro"|"rw"}]
# Returns ["../../repo:/repo:ro", ...] for docker-compose volumes
```

---

## host module

```python
host.check_packages() -> dict
# Returns {
#   "texlive": {"installed": bool, "version": str, "binaries": [str, ...]},
#   "imagemagick": {"installed": bool, "version": str, "binaries": [str, ...]},
# }

host.install_packages(
    texlive: bool = False,
    imagemagick: bool = False,
    all: bool = False,
    check_only: bool = False,
) -> dict
# Calls scripts/install-host-packages.sh via sudo
# Returns {"texlive": {"status": "installed|failed|skipped", "returncode": int}, ...}

host.get_texlive_binds(prefix: str = "/usr") -> list[dict]
# Returns [{"host": str, "container": str, "mode": "ro"}, ...] for TeXLive mounts

host.get_mount_config(
    texlive_prefix: str = "",
    host_mounts_raw: str = "",
) -> dict
# Returns {"bind_args": ["--bind", spec, ...], "path_additions": [str], "mounts": [dict]}
# host_mounts_raw: comma/newline-separated "host:container[:mode]" specs

# Constants:
host.TEXLIVE_BINARIES  # list[str]: pdflatex, bibtex, latexmk, latexdiff, ...
host.TEXLIVE_DIRS      # list[str]: share/texlive, share/texmf-dist
```

---

## Top-level

```python
from scitex_container import env_snapshot

env_snapshot(
    containers_dir: str | Path | None = None,
    dev_repos: list[str | Path] | None = None,
) -> dict
# Capture JSON-serializable environment snapshot.
# Returns {
#   "schema_version": "1.0",
#   "timestamp": "<ISO8601>",
#   "container": {"version": str, "sif_path": str, "sif_sha256": str, "def_hash": str},
#   "host": {"texlive": {...}, "imagemagick": {...}},
#   "dev_repos": [{"name", "path", "commit", "branch", "dirty"}, ...],
#   "lock_files": {"pip": str, "dpkg": str},
# }
# Never raises; gracefully omits unavailable fields.
```
