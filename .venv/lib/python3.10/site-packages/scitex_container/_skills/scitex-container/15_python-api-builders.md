---
description: |
  [TOPIC] Python API Reference — command builders
  [DETAILS] Python API reference for scitex-container — apptainer SLURM / exec command builders.
tags: [scitex-container-python-api-builders]
---

# Python API Reference — command builders

```python
import scitex_container.apptainer as apptainer
```

These helpers compose `apptainer exec` / `srun` / `sbatch` arg lists for
SLURM-aware launchers. They return plain `list[str]` ready for `subprocess`.

---

## SLURM / apptainer exec

```python
apptainer.build_exec_args(
    container_path: str,
    username: str,
    host_user_dir: Path,
    host_project_dir: Path,
    project_slug: str,
    dev_repos: list[dict] | None = None,
    host_mounts: list[dict] | None = None,
    texlive_prefix: str = "",
) -> list[str]
# Returns ["apptainer", "exec", "--containall", "--cleanenv", "--writable-tmpfs", ...]
# dev_repos dicts: {"name": str, "host_path": str}
# host_mounts dicts: {"host_path": str, "container_path": str, "mode": str}

apptainer.build_srun_command(
    container_path: str,
    username: str,
    host_user_dir: Path,
    host_project_dir: Path,
    project_slug: str,
    dev_repos: list[dict] | None = None,
    host_mounts: list[dict] | None = None,
    texlive_prefix: str = "",
    slurm_partition: str = "compute",
    slurm_time_limit: str = "8:00:00",
    slurm_cpus: int = 4,
    slurm_memory_gb: int = 16,
) -> list[str]
# Returns ["srun", "--pty", "--chdir=/tmp", ...]

apptainer.build_sbatch_command(
    instance_name: str,
    script_path: str,
    slurm_partition: str = "compute",
    slurm_time_limit: str = "8:00:00",
    slurm_cpus: int = 4,
    slurm_memory_gb: int = 16,
    username: str = "",
    project_slug: str = "",
) -> list[str]

apptainer.build_instance_start_script(
    container_path: str,
    username: str,
    host_user_dir: Path,
    host_project_dir: Path,
    project_slug: str,
    instance_name: str,
    dev_repos: list[dict] | None = None,
    host_mounts: list[dict] | None = None,
    texlive_prefix: str = "",
) -> str
# Returns bash script content for sbatch submission

apptainer.build_shell_in_allocation_command(
    job_id: str,
    instance_name: str,
    username: str = "",
) -> list[str]
# Returns ["srun", "--pty", "--overlap", "--jobid=...", "apptainer", "exec", ...]

apptainer.build_dev_pythonpath(dev_repos: list[dict]) -> str
# Returns colon-separated PYTHONPATH e.g. "/opt/dev/scitex-python/src:..."
# Each repo dict must have "name" key

apptainer.build_host_mount_binds(
    host_mounts: list[dict] | None = None,
    texlive_prefix: str = "",
) -> list[str]
# Returns flat ["--bind", "spec", "--bind", "spec", ...] list
```
