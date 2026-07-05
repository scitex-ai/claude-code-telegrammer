#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/apptainer/_command_builder.py
"""Build apptainer exec arguments for terminal sessions.

All configuration is passed as explicit function parameters so this module
has no dependency on Django settings or any project-specific config files.
"""

from __future__ import annotations

import logging
from pathlib import Path

from scitex_container._compat import supports_return_as

logger = logging.getLogger(__name__)

# TeX Live binary names to bind-mount from the host prefix
_TEXLIVE_BINS = [
    "pdflatex",
    "bibtex",
    "latexmk",
    "latexdiff",
    "kpsewhich",
    "makeindex",
]

# TeX Live share directories to bind-mount from the host prefix
_TEXLIVE_SHARE_DIRS = [
    "texlive",
    "texmf-dist",
]


@supports_return_as
def build_dev_pythonpath(dev_repos: list[dict]) -> str:
    """Build a PYTHONPATH string that prepends ``/opt/dev/{name}/src`` for each dev repo.

    Packages in dev repos are assumed to follow the src-layout convention
    (i.e. ``repo_root/src/<package>``), so we add ``/opt/dev/{name}/src``.

    Parameters
    ----------
    dev_repos : list[dict]
        List of dev repo dicts, each with a ``name`` key.

    Returns
    -------
    str
        Colon-separated PYTHONPATH string, or empty string if no repos.
    """
    if not dev_repos:
        return ""
    parts = [f"/opt/dev/{repo['name']}/src" for repo in dev_repos]
    return ":".join(parts)


@supports_return_as
def build_host_mount_binds(
    host_mounts: list[dict] | None = None,
    texlive_prefix: str = "",
) -> list[str]:
    """Build ``--bind`` argument pairs for host package mounts.

    Parameters
    ----------
    host_mounts : list[dict], optional
        Generic list of ``{host_path, container_path, mode}`` dicts.
    texlive_prefix : str
        Host prefix for TeX Live installation (e.g. ``/usr``). When set,
        auto-generates bind entries for TeX Live share directories and binaries.
        Example: ``/usr`` generates ``--bind`` entries for
        ``/usr/share/texlive``, ``/usr/share/texmf-dist``,
        ``/usr/bin/pdflatex`` (and all ``_TEXLIVE_BINS``), each ``:ro``.

    Returns
    -------
    list[str]
        Flat list of alternating ``"--bind"`` / ``"<spec>"`` strings
        ready to be inserted into the apptainer argv list.
    """
    bind_args: list[str] = []

    for mount in host_mounts or []:
        spec = f"{mount['host_path']}:{mount['container_path']}:{mount['mode']}"
        bind_args += ["--bind", spec]
        logger.debug("Host mount: %s", spec)

    if texlive_prefix:
        prefix = texlive_prefix.rstrip("/")

        for share_dir in _TEXLIVE_SHARE_DIRS:
            path = f"{prefix}/share/{share_dir}"
            spec = f"{path}:{path}:ro"
            bind_args += ["--bind", spec]
            logger.debug("TeX Live share mount: %s", spec)

        for binary in _TEXLIVE_BINS:
            path = f"{prefix}/bin/{binary}"
            spec = f"{path}:{path}:ro"
            bind_args += ["--bind", spec]
            logger.debug("TeX Live bin mount: %s", spec)

    return bind_args


@supports_return_as
def build_exec_args(
    container_path: str,
    username: str,
    host_user_dir: Path,
    host_project_dir: Path,
    project_slug: str,
    dev_repos: list[dict] | None = None,
    host_mounts: list[dict] | None = None,
    texlive_prefix: str = "",
) -> list[str]:
    """Build the ``apptainer exec`` argument list.

    Handles:

    - Sandbox vs SIF detection. Both use ``--writable-tmpfs`` for user
      sessions so each user gets a clean per-session tmpfs overlay.
    - For SIF images, ``--containall`` is added to prevent host mounts
      leaking in.
    - Dev repo bind mounts.
    - PYTHONPATH injection for dev repos (src-layout).
    - Host package bind mounts (TeX Live, etc.).
    - Standard ``--env``, ``--home``, ``--bind`` args.

    Parameters
    ----------
    container_path : str
        Path to the SIF file or sandbox directory.
    username : str
        Username for the session (used for home dir and env vars).
    host_user_dir : Path
        Host path to the user's home directory.
    host_project_dir : Path
        Host path to the project directory.
    project_slug : str
        Project identifier (e.g. "my-project").
    dev_repos : list[dict], optional
        Dev repo dicts with ``name`` and ``host_path`` keys.
    host_mounts : list[dict], optional
        Generic host mount dicts with ``host_path``, ``container_path``, ``mode``.
    texlive_prefix : str
        Host prefix for TeX Live (e.g. ``/usr``).

    Returns
    -------
    list[str]
        Flat list starting with ``["apptainer", "exec", ...]``.
    """
    dev_repos = dev_repos or []

    # Dev repo bind mounts
    dev_bind_args: list[str] = []
    for repo in dev_repos:
        spec = f"{repo['host_path']}:/opt/dev/{repo['name']}:ro"
        dev_bind_args += ["--bind", spec]
        logger.debug("Dev mode: mounting %s from %s", repo["name"], repo["host_path"])

    dev_pythonpath = build_dev_pythonpath(dev_repos)
    host_mount_binds = build_host_mount_binds(
        host_mounts=host_mounts,
        texlive_prefix=texlive_prefix,
    )

    args: list[str] = ["apptainer", "exec"]

    # Always isolate — both SIF and sandbox need --containall
    # to prevent host filesystem leakage and ensure user isolation
    args.append("--containall")

    args += [
        "--cleanenv",
        "--writable-tmpfs",
        "--hostname",
        "scitex-cloud",
        "--env",
        "TERM=xterm-256color",
        "--env",
        "SCITEX_CLOUD=true",
        "--env",
        f"SCITEX_PROJECT={project_slug}",
        "--env",
        f"SCITEX_USER={username}",
        "--env",
        f"USER={username}",
        "--env",
        f"LOGNAME={username}",
        "--env",
        "SHELL=/bin/bash",
        "--env",
        "PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin",
    ]

    if dev_pythonpath:
        args += ["--env", f"PYTHONPATH={dev_pythonpath}"]

    args += [
        "--home",
        f"{host_user_dir}:/home/{username}",
        "--bind",
        f"{host_project_dir}:/home/{username}/proj/{project_slug}:rw",
        *dev_bind_args,
        *host_mount_binds,
        "--pwd",
        f"/home/{username}/proj/{project_slug}",
        container_path,
    ]

    return args


@supports_return_as
def build_instance_start_script(
    container_path: str,
    username: str,
    host_user_dir: Path,
    host_project_dir: Path,
    project_slug: str,
    instance_name: str,
    dev_repos: list[dict] | None = None,
    host_mounts: list[dict] | None = None,
    texlive_prefix: str = "",
) -> str:
    """Build a bash script that starts an apptainer instance and keeps it alive.

    This script is designed to be submitted via ``sbatch``. It:

    1. Starts an apptainer instance with ``--writable-tmpfs`` (shared overlay).
    2. Prints ``INSTANCE_READY`` on success or ``INSTANCE_FAILED`` on failure.
    3. Sleeps in a loop while the instance is alive (sbatch keeps the
       allocation open).

    Parameters
    ----------
    container_path : str
        Path to the SIF file or sandbox directory.
    username : str
        Username for the session.
    host_user_dir : Path
        Host path to the user's home directory.
    host_project_dir : Path
        Host path to the project directory.
    project_slug : str
        Project identifier.
    instance_name : str
        Name for the apptainer instance (e.g. ``scitex-user-project``).
    dev_repos : list[dict], optional
        Dev repo dicts with ``name`` and ``host_path`` keys.
    host_mounts : list[dict], optional
        Generic host mount dicts.
    texlive_prefix : str
        Host prefix for TeX Live.

    Returns
    -------
    str
        Complete bash script content.
    """
    # Reuse build_exec_args logic but extract only the flags (skip "apptainer exec")
    exec_args = build_exec_args(
        container_path=container_path,
        username=username,
        host_user_dir=host_user_dir,
        host_project_dir=host_project_dir,
        project_slug=project_slug,
        dev_repos=dev_repos,
        host_mounts=host_mounts,
        texlive_prefix=texlive_prefix,
    )
    # exec_args = ["apptainer", "exec", "--containall", ..., container_path]
    # For instance start, we need the flags between "exec" and container_path,
    # then replace "exec" with "instance start" and append instance_name.
    # The container_path is the last element.
    flags = exec_args[2:-1]  # Skip "apptainer", "exec", and final container_path
    # --pwd is exec/run-only; strip it and its value for instance start
    flags = [
        f
        for i, f in enumerate(flags)
        if f != "--pwd" and (i == 0 or flags[i - 1] != "--pwd")
    ]
    import shlex

    flags_str = " ".join(shlex.quote(f) for f in flags)
    container_quoted = shlex.quote(container_path)
    instance_quoted = shlex.quote(instance_name)

    script = f"""#!/bin/bash
# Auto-generated by scitex-container for shared allocation
# Instance: {instance_name}, User: {username}, Project: {project_slug}
set -e

apptainer instance start {flags_str} {container_quoted} {instance_quoted}
if [ $? -ne 0 ]; then
    echo "INSTANCE_FAILED"
    exit 1
fi
echo "INSTANCE_READY"

# Keep allocation alive while instance is running
while apptainer instance list 2>/dev/null | grep -q {instance_quoted}; do
    sleep 10
done
echo "INSTANCE_STOPPED"
"""
    return script


@supports_return_as
def build_sbatch_command(
    instance_name: str,
    script_path: str,
    slurm_partition: str = "compute",
    slurm_time_limit: str = "8:00:00",
    slurm_cpus: int = 4,
    slurm_memory_gb: int = 16,
    username: str = "",
    project_slug: str = "",
) -> list[str]:
    """Build ``sbatch`` command to submit an allocation script.

    Parameters
    ----------
    instance_name : str
        Used to derive the SLURM job name.
    script_path : str
        Path to the bash script (from ``build_instance_start_script``).
    slurm_partition : str
        SLURM partition name.
    slurm_time_limit : str
        SLURM time limit (e.g. "8:00:00").
    slurm_cpus : int
        Number of CPUs per task.
    slurm_memory_gb : int
        Memory in GB.
    username : str
        Username (for job name).
    project_slug : str
        Project slug (for job name).

    Returns
    -------
    list[str]
        Command list ready for ``subprocess.run()``.
    """
    job_name = f"scitex_{username}_{project_slug}" if username else instance_name
    return [
        "sbatch",
        "--parsable",
        f"--partition={slurm_partition}",
        f"--time={slurm_time_limit}",
        f"--cpus-per-task={slurm_cpus}",
        f"--mem={slurm_memory_gb}G",
        f"--job-name={job_name}",
        "--output=/dev/null",
        script_path,
    ]


@supports_return_as
def build_shell_in_allocation_command(
    job_id: str,
    instance_name: str,
    username: str = "",
) -> list[str]:
    """Build ``srun --overlap`` command to attach a shell inside an existing allocation.

    Parameters
    ----------
    job_id : str
        SLURM job ID of the running allocation.
    instance_name : str
        Name of the apptainer instance to exec into.
    username : str
        Username for the shell session (used for user identity setup).

    Returns
    -------
    list[str]
        Command list ready for ``os.execvpe`` or ``pty.fork``.
    """
    return [
        "srun",
        "--pty",
        "--overlap",
        f"--jobid={job_id}",
        "apptainer",
        "exec",
        f"instance://{instance_name}",
        *_build_shell_command(username),
    ]


def _build_shell_command(username: str) -> list[str]:
    """Build shell entry command: fix user identity, cd to project dir, start bash."""
    setup_script = (
        # Fix user identity when running as root inside container
        'if [ "$(id -u)" = "0" ] && [ -n "$USER" ] && [ "$USER" != "root" ]; then '
        '  sed -i "s|^root:[^:]*:0:0:[^:]*:[^:]*:|$USER:x:0:0:$USER:/home/$USER:|" /etc/passwd 2>/dev/null; '
        "fi; "
        # Ensure HOME points to the user's home directory.
        # apptainer exec instance:// inherits env from the calling process,
        # which may have HOME set to the broker/Django process's home dir
        # rather than the container user's home. Without this, bash -l
        # looks for .bash_profile in the wrong directory and PS1 is never set.
        'if [ -n "$USER" ]; then export HOME="/home/$USER"; fi; '
        # cd to project dir (SCITEX_PROJECT is set by build_exec_args)
        'if [ -n "$SCITEX_PROJECT" ] && [ -n "$USER" ]; then '
        '  _proj="/home/$USER/proj/$SCITEX_PROJECT"; '
        '  if [ -d "$_proj" ]; then cd "$_proj"; '
        '  else echo "⚠ Project directory $_proj not found — project may have changed on SciTeX Cloud"; '
        "  fi; "
        "fi; "
        "exec /bin/bash -l"
    )
    return ["/bin/bash", "-c", setup_script]


@supports_return_as
def build_srun_command(
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
    screen_session: str = "scitex-0",  # Deprecated: kept for API compat, ignored
) -> list[str]:
    """Build the complete ``srun`` + ``apptainer`` command list.

    Combines the SLURM resource flags with the apptainer exec arguments
    produced by ``build_exec_args()``, launching a login bash shell directly
    (no screen).

    Parameters
    ----------
    container_path : str
        Path to the SIF file or sandbox directory.
    username : str
        Username for the session.
    host_user_dir : Path
        Host path to the user's home directory.
    host_project_dir : Path
        Host path to the project directory.
    project_slug : str
        Project identifier.
    dev_repos : list[dict], optional
        Dev repo dicts with ``name`` and ``host_path`` keys.
    host_mounts : list[dict], optional
        Generic host mount dicts.
    texlive_prefix : str
        Host prefix for TeX Live.
    slurm_partition : str
        SLURM partition name.
    slurm_time_limit : str
        SLURM time limit (e.g. "8:00:00").
    slurm_cpus : int
        Number of CPUs per task.
    slurm_memory_gb : int
        Memory in GB.
    screen_session : str
        Deprecated — ignored. Kept for backward compatibility.

    Returns
    -------
    list[str]
        Flat list ready to be passed to ``os.execvpe`` or ``subprocess.Popen``.
    """
    apptainer_args = build_exec_args(
        container_path=container_path,
        username=username,
        host_user_dir=host_user_dir,
        host_project_dir=host_project_dir,
        project_slug=project_slug,
        dev_repos=dev_repos,
        host_mounts=host_mounts,
        texlive_prefix=texlive_prefix,
    )

    cmd = [
        "srun",
        "--pty",
        "--chdir=/tmp",
        f"--partition={slurm_partition}",
        f"--time={slurm_time_limit}",
        f"--cpus-per-task={slurm_cpus}",
        f"--mem={slurm_memory_gb}G",
        f"--job-name=terminal_{username}",
        *apptainer_args,
        *_build_shell_command(username),
    ]

    return cmd


# EOF
