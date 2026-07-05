#!/usr/bin/env python3
# Timestamp: 2026-03-13
# File: scitex_dev/dev_mcp/handlers.py

"""MCP handler implementations for developer utilities.

All handlers return structured Result JSON via wrap_as_mcp.
"""

from __future__ import annotations


from .._ecosystem._mcp import wrap_as_mcp
from .._core.types import Result


async def list_versions_handler(
    packages: list[str] | None = None,
    *,
    _list_versions_fn=None,
) -> str:
    """Report the installed version of every SciTeX package (scitex, scitex-io, scitex-stats, figrecipe, scitex-writer, scitex-scholar, scitex-notebook, scitex-audio, scitex-clew, scitex-dev, scitex-linter, …). Use when the user asks "what versions of scitex do I have?", "list ecosystem versions", "show every scitex-* version", or before a release to see the current state. Optionally filter to a subset with `packages=[...]`."""
    if _list_versions_fn is None:
        from .._release.versions import list_versions as _list_versions_fn

    return wrap_as_mcp(
        _list_versions_fn,
        idempotent=True,
        packages=packages,
    )


async def get_config_handler() -> str:
    """Show the active `DevConfig` — which hosts are configured, which packages are registered in the ecosystem, default HPC partition / time / memory, editable-install paths. Use when the user asks "show my dev config", "what hosts does scitex-dev know?", "dump the config", or is debugging why `sync` / `test_hpc_run` can't find a host."""
    from .._core.config import config_to_dict, get_config_path, load_config

    def _get_config():
        config = load_config()
        return config_to_dict(config, config_path=get_config_path())

    return wrap_as_mcp(
        _get_config,
        idempotent=True,
    )


async def test_run_handler(
    module: str = "",
    fast: bool = False,
    coverage: bool = False,
    exitfirst: bool = True,
    pattern: str = "",
    parallel: str = "auto",
) -> str:
    """Run pytest locally against a SciTeX package — `fast` skips slow tests, `coverage` collects coverage, `exitfirst` stops on first failure, `pattern` filters test IDs, `parallel='auto'` uses `pytest-xdist`. Drop-in replacement for hand-typing `cd path/to/pkg && pytest …`. Use when the user asks to "run tests for X", "test scitex-io", "run the test suite", "rerun failing tests fast", or before committing."""
    from ..test_runner import TestConfig, run_local

    def _run():
        config = TestConfig(
            module=module,
            fast=fast,
            coverage=coverage,
            exitfirst=exitfirst,
            pattern=pattern,
            parallel=parallel,
        )
        exit_code = run_local(config)
        return {"exit_code": exit_code}

    return wrap_as_mcp(
        _run,
        idempotent=True,
    )


async def test_hpc_run_handler(
    module: str = "",
    fast: bool = False,
    hpc_cpus: int = 8,
    hpc_partition: str = "sapphire",
    hpc_time: str = "00:10:00",
    hpc_mem: str = "16G",
    async_mode: bool = False,
) -> str:
    """Submit the test suite to a remote HPC cluster via Slurm — rsyncs the repo, then uses `sbatch` (async, returns `job_id`) or `srun` (sync, blocks until done). Drop-in replacement for manually `rsync`-ing + `ssh user@hpc 'sbatch job.sh'`. Use whenever the user asks to "run tests on the HPC", "submit a Slurm job for tests", "sbatch the test suite", or has tests too slow/large for the laptop. Set `async_mode=True` to return immediately with a `job_id` for later polling via `test_hpc_poll`."""
    from ..test_runner import (
        TestConfig,
        _check_ssh,
        _get_hpc_config,
        run_hpc_sbatch,
        run_hpc_srun,
        sync_to_hpc,
    )

    config = TestConfig(
        module=module,
        fast=fast,
        hpc_cpus=hpc_cpus,
        hpc_partition=hpc_partition,
        hpc_time=hpc_time,
        hpc_mem=hpc_mem,
    )
    hpc_cfg = _get_hpc_config(config)
    host = hpc_cfg["host"]

    if not _check_ssh(host):
        return Result(
            success=False,
            error=f"Cannot connect to {host}",
            error_code="E007",
            hints_on_error=[f"Check SSH connectivity to {host}"],
        ).to_json()

    if not sync_to_hpc(config):
        return Result(
            success=False,
            error="rsync failed",
            error_code="E007",
            hints_on_error=["Check rsync and SSH configuration"],
        ).to_json()

    if async_mode:
        job_id = run_hpc_sbatch(config)
        if job_id:
            return Result(
                success=True,
                data={"job_id": job_id, "host": host},
                side_effects=["hpc_job: submits Slurm job on remote HPC"],
            ).to_json()
        return Result(
            success=False,
            error="Failed to submit job",
            error_code="E999",
        ).to_json()
    else:
        exit_code = run_hpc_srun(config)
        return Result(
            success=exit_code == 0,
            data={"exit_code": exit_code, "host": host},
            side_effects=["hpc_job: submits Slurm job on remote HPC"],
        ).to_json()


async def test_hpc_poll_handler(
    job_id: str | None = None,
) -> str:
    """Check the Slurm status of a previously submitted `test_hpc_run` job (PENDING / RUNNING / COMPLETED / FAILED / CANCELLED). Drop-in replacement for `ssh hpc 'squeue -j JOB_ID'`. Use when the user asks "is my HPC job done?", "check my sbatch job", "poll job 12345", or is waiting on an async test run. Omit `job_id` to poll the most recent submission."""
    from ..test_runner import poll_hpc_job

    return wrap_as_mcp(
        poll_hpc_job,
        idempotent=True,
        job_id=job_id,
    )


async def test_hpc_result_handler(
    job_id: str | None = None,
) -> str:
    """Retrieve the stdout/stderr log of a completed Slurm test job from the HPC. Use when the user asks "what were the test results?", "show me the output of my HPC job", "fetch job 12345's log", or after `test_hpc_poll` returns `COMPLETED`. Omit `job_id` to grab the last submission."""
    from ..test_runner import fetch_hpc_result

    def _fetch():
        output = fetch_hpc_result(job_id=job_id)
        return {"output": output, "job_id": job_id or "last"}

    return wrap_as_mcp(
        _fetch,
        idempotent=True,
    )


async def sync_handler(
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    install: bool = True,
    safe: bool = True,
    confirm: bool = False,
) -> str:
    """Push local SciTeX changes to every configured remote host — `git pull` each repo, `pip install -e` if it changed, with an ahead-check safeguard that skips any remote with unpushed commits (so you never clobber someone's in-progress work). Use whenever the user asks to "sync my changes to the lab machines", "update scitex on all my hosts", "deploy these fixes to gpu01/gpu02", "push to HPC", or is rolling out a cross-package change. Set `safe=False` to force, `confirm=True` to actually execute (default is dry-run).

    When ``safe`` is True (default), per-package ahead-check skips
    remote working copies that have unpushed commits so we never
    clobber work. Pass safe=False to force pull regardless.
    """
    from .._sync import sync_all

    return wrap_as_mcp(
        sync_all,
        side_effects=["remote_exec: git pull + pip install on remote hosts"],
        hosts=hosts,
        packages=packages,
        install=install,
        safe=safe,
        confirm=confirm,
    )


async def sync_local_handler(
    packages: list[str] | None = None,
    confirm: bool = False,
) -> str:
    """`pip install -e .` every SciTeX package in the local ecosystem — ensures imports resolve to the working-tree version, not the last PyPI release. Use whenever the user asks to "install all scitex packages in editable mode", "make pip see my local changes", "sync local editable installs", "reinstall after cloning fresh", or is fixing a version mismatch introduced by `pip install scitex`."""
    from .._sync import sync_local

    return wrap_as_mcp(
        sync_local,
        side_effects=["pip_install: installs packages in editable mode"],
        packages=packages,
        confirm=confirm,
    )


async def remote_diff_handler(
    host: str | None = None,
    packages: list[str] | None = None,
) -> str:
    """SSH to each configured remote host and run `git status` / `git diff` across every SciTeX repo — surfaces work that still lives only on gpu01 / laptop / HPC. Use when the user asks "is anything uncommitted on my other machines?", "show remote diffs", "what have I changed on the HPC?", or before a sync to check for drift."""
    from .._sync import remote_diff

    return wrap_as_mcp(
        remote_diff,
        idempotent=True,
        host=host,
        packages=packages,
    )


async def remote_commit_handler(
    host: str,
    packages: list[str] | None = None,
    message: str | None = None,
    push: bool = True,
    confirm: bool = False,
) -> str:
    """SSH to a remote host and `git commit` (+ optionally `git push`) dirty changes across SciTeX repos — useful for rescuing work left behind on an HPC session or another machine. Use when the user asks to "commit what's on gpu01", "save the HPC-side changes", "push remote work to origin", "grab that half-finished change I made on the lab server". Pass `confirm=True` to actually commit (default previews)."""
    from .._sync import remote_commit

    return wrap_as_mcp(
        remote_commit,
        side_effects=[
            "git_commit: commits changes on remote host",
            "git_push: pushes to origin",
        ],
        host=host,
        packages=packages,
        message=message,
        push=push,
        confirm=confirm,
    )


async def pull_local_handler(
    packages: list[str] | None = None,
    confirm: bool = False,
    stash: bool = True,
) -> str:
    """`git pull` every local SciTeX repo from origin — with an optional `git stash` first to survive dirty trees. Drop-in replacement for walking each `~/proj/scitex-*` folder and running `git pull`. Use when the user asks to "update all my local scitex repos", "pull origin on every package", "sync local with GitHub", "stash and pull all scitex", or at session start."""
    from .._sync import pull_local

    return wrap_as_mcp(
        pull_local,
        side_effects=["git_pull: pulls from origin to local repos"],
        packages=packages,
        confirm=confirm,
        stash=stash,
    )


async def rename_handler(
    pattern: str,
    replacement: str,
    directory: str = ".",
    confirm: bool = False,
    regex: bool = False,
    django_safe: bool = True,
    extra_excludes: list[str] | None = None,
    force: bool = False,
    skip_ids: list[str] | None = None,
    use_sudo: bool = False,
    sudo_password: str | None = None,
    scope: str = "",
    recursive: bool = True,
) -> str:
    """Rename an identifier across an entire project — updates filenames, directory names, symlink targets, AND file contents in one shot, with git-safety guards (refuses to run if uncommitted changes exist unless `force=True`). Drop-in replacement for `sed -i` + `git mv` + find-and-replace scripting. Use whenever the user asks to "rename foo → bar everywhere", "refactor this symbol globally", "bulk rename in this directory", "search-and-replace across files", or is restructuring naming before a release. Pass `regex=True` for regex patterns. Dry-runs by default; set `confirm=True` to apply."""
    from dataclasses import asdict

    from ..rename import RenameConfig, bulk_rename
    from ..rename.safety import has_uncommitted_changes

    if confirm and not force and has_uncommitted_changes(directory):
        return Result(
            success=False,
            error="Uncommitted changes detected. Commit or stash first.",
            error_code="E009",
            hints_on_error=[
                "Run 'git commit' or 'git stash' first",
                "Or pass force=True to skip this check",
            ],
        ).to_json()

    if use_sudo and sudo_password:
        from ..rename.io import set_sudo_password

        set_sudo_password(sudo_password)

    def _rename():
        config = RenameConfig(
            pattern=pattern,
            replacement=replacement,
            directory=directory,
            dry_run=not confirm,
            regex=regex,
            django_safe=django_safe,
            scope=scope,
            recursive=recursive,
            extra_excludes=extra_excludes or [],
            skip_ids=skip_ids or [],
            use_sudo=use_sudo,
        )
        result = bulk_rename(config)
        return asdict(result)

    try:
        return wrap_as_mcp(
            _rename,
            side_effects=["file_modify: renames files, directories, and content"],
        )
    finally:
        if use_sudo and sudo_password:
            from ..rename.io import set_sudo_password

            set_sudo_password(None)


async def fix_mismatches_handler(
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    local: bool = True,
    remote: bool = True,
    confirm: bool = False,
) -> str:
    """Scan every SciTeX package (locally and on every configured remote host) for installed-version drift against `pyproject.toml`, and restore consistency via `pip install` + `git pull`. Use whenever the user asks "are all my scitex installs in sync?", "fix version mismatches", "why is scitex-io saying 0.3.1 on gpu01 but 0.3.2 here?", "audit and repair ecosystem versions", or before a release/demo where version drift would bite. Defaults to dry-run; pass `confirm=True` to actually install."""
    from .._release.fix import fix_mismatches

    return wrap_as_mcp(
        fix_mismatches,
        side_effects=[
            "pip_install: fixes mismatched package versions",
            "remote_exec: git pull on remote hosts",
        ],
        hosts=hosts,
        packages=packages,
        local=local,
        remote=remote,
        confirm=confirm,
    )


async def skills_list_handler(
    package: str | None = None,
) -> str:
    """Enumerate every skill page shipped by every SciTeX package — scitex-io's `01_save-and-load`, scitex-stats' `01_test-catalog`, figrecipe's `02_plot-types`, scitex-writer's `13_claims`, etc. Use whenever the user asks "what skill pages exist?", "list all scitex skills", "what docs are shipped with these packages?", or is discovering learning resources. Filter to one package with `package='scitex-io'`."""
    from .._ecosystem._skills.skills import list_skills

    return wrap_as_mcp(list_skills, idempotent=True, package=package)


async def skills_get_handler(
    package: str,
    name: str,
) -> str:
    """Fetch the full Markdown of one skill page — e.g. `package='scitex-io', name='01_save-and-load'` returns that file's contents. Use whenever the user asks "show me the scitex-io quick-start skill", "read the figrecipe composition skill", "get the claims skill page from scitex-writer", or is diving into a specific guide. Pair with `skills_list_handler` to discover names."""
    from .._ecosystem._skills.skills import get_skill

    return wrap_as_mcp(get_skill, idempotent=True, package=package, name=name)


# EOF
