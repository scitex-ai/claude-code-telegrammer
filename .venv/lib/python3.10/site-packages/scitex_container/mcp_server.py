#!/usr/bin/env python3
# Timestamp: "2026-02-25"
# File: src/scitex_container/mcp_server.py
"""FastMCP server for scitex-container.

Usage:
    scitex-container-mcp               # stdio (Claude Desktop)
    python -m scitex_container mcp     # alternative entry point
"""

from __future__ import annotations

from scitex_dev import try_import_optional

FastMCP = try_import_optional("fastmcp", "FastMCP", extra="mcp", pkg="scitex-container")
FASTMCP_AVAILABLE = FastMCP is not None

__all__ = ["mcp", "main", "FASTMCP_AVAILABLE"]

if FASTMCP_AVAILABLE:
    mcp = FastMCP(
        name="scitex-container",
        instructions="""\
scitex-container: Container management for Apptainer/Singularity and Docker.

## Available Tools

### Apptainer container operations
- container_build     — Build a SIF or sandbox from a .def file
- container_list_versions — List versioned SIFs with active marker
- container_switch    — Switch active container version
- container_rollback  — Roll back to the previous version
- container_deploy    — Copy active SIF to production target
- container_cleanup   — Remove old versions (keep N most recent)

### Sandbox operations
- sandbox_create      — Convert a SIF to a writable sandbox directory

### Docker Compose operations
- docker_rebuild      — Rebuild images without cache
- docker_restart      — Restart containers (down + up -d)

### Host package management
- host_install        — Install TeXLive / ImageMagick on the host
- host_check          — Check which host packages are installed

### Unified status
- container_status    — Dashboard: Apptainer + host packages + Docker

### Integrity verification
- container_verify    — Verify SIF SHA256, .def origin, and lock file consistency

### Clew reproducibility
- container_env_snapshot — Capture environment snapshot (container + host + git)
""",
    )
else:
    mcp = None


# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------

if FASTMCP_AVAILABLE and mcp is not None:

    @mcp.tool()
    async def container_build(
        name: str = "scitex-final",
        sandbox: bool = False,
        force: bool = False,
        base: bool = False,
    ) -> dict:
        """Build an Apptainer/Singularity SIF image (or writable sandbox dir) from a `.def` recipe, auto-versioning the output and writing a lock file. Drop-in replacement for manual `apptainer build --fakeroot image.sif recipe.def` shell loops + custom version-tag scripts. Use whenever the user asks to "build a SIF", "build the container", "rebuild with force", "build a sandbox instead", "build the base image", or mentions `.def` / Apptainer / Singularity recipe.

        Args:
            name: Name of the .def file (without extension).
            sandbox: Build a sandbox directory instead of a SIF.
            force: Force rebuild even if the .def is unchanged.
            base: Build the base image instead of the final image.
        """
        from ._mcp.handlers import build_handler

        return await build_handler(name=name, sandbox=sandbox, force=force, base=base)

    @mcp.tool()
    async def container_list_versions(containers_dir: str = "") -> dict:
        """Enumerate every versioned SIF in the containers directory with size, build date, and a marker for the currently-active symlink target. Drop-in replacement for hand-rolled `ls -la /opt/scitex/containers/*.sif` + `readlink active.sif`. Use when the user asks "which containers do I have?", "list SIF versions", "what's active?", or is choosing a version to switch to.

        Args:
            containers_dir: Path to containers directory (auto-detected if empty).
        """
        from ._mcp.handlers import list_handler

        return await list_handler(containers_dir=containers_dir or None)

    @mcp.tool()
    async def container_switch(
        version: str,
        containers_dir: str = "",
        use_sudo: bool = False,
    ) -> dict:
        """Atomically re-point the `active.sif` symlink to a specific version — the next `apptainer exec active.sif` picks up the new container without touching any user scripts. Drop-in replacement for `ln -sf scitex-v2.19.5.sif active.sif`. Use when the user asks to "switch to version X", "activate v2.19.5", "change the active container", or is promoting a tested build.

        Args:
            version: Target version string (e.g. "2.19.5").
            containers_dir: Path to containers directory (auto-detected if empty).
            use_sudo: Use sudo for symlink operations (needed for /opt paths).
        """
        from ._mcp.handlers import switch_handler

        return await switch_handler(
            version=version,
            containers_dir=containers_dir or None,
            use_sudo=use_sudo,
        )

    @mcp.tool()
    async def container_rollback(
        containers_dir: str = "",
        use_sudo: bool = False,
    ) -> dict:
        """Flip the active symlink back to the second-newest SIF — instant recovery when a new build breaks production. Drop-in replacement for remembering the old version number and running `container_switch` by hand. Use when the user asks to "rollback", "revert the container", "the new container is broken", "go back to the previous version", or is reacting to a bad deploy.

        Args:
            containers_dir: Path to containers directory (auto-detected if empty).
            use_sudo: Use sudo for symlink operations.
        """
        from ._mcp.handlers import rollback_handler

        return await rollback_handler(
            containers_dir=containers_dir or None,
            use_sudo=use_sudo,
        )

    @mcp.tool()
    async def container_deploy(
        target_dir: str = "/opt/scitex/singularity",
        containers_dir: str = "",
    ) -> dict:
        """Copy the currently-active SIF + its lock file to a production/shared path (default `/opt/scitex/singularity`) for SLURM / HPC / cluster consumption. Drop-in replacement for manual `cp active.sif /opt/scitex/singularity/ && cp *.lock /opt/scitex/singularity/`. Use when the user asks to "deploy the container", "push to /opt for SLURM", "make this available on HPC", or mentions cluster / shared / production deployment.

        Args:
            target_dir: Deployment target path.
            containers_dir: Source containers directory (auto-detected if empty).
        """
        from ._mcp.handlers import deploy_handler

        return await deploy_handler(
            target_dir=target_dir,
            containers_dir=containers_dir or None,
        )

    @mcp.tool()
    async def container_cleanup(
        keep: int = 3,
        containers_dir: str = "",
    ) -> dict:
        """Delete stale SIFs from the containers directory, keeping the N newest + whatever is currently active (never deletes active). SIFs are ~2–10 GB each, so cleanup reclaims serious disk. Drop-in replacement for eyeballing `ls -t *.sif | tail -n +N | xargs rm`. Use when the user asks to "clean up old SIFs", "prune old containers", "free container disk space", or is running low on storage.

        Args:
            keep: Number of recent versions to keep.
            containers_dir: Containers directory (auto-detected if empty).
        """
        from ._mcp.handlers import cleanup_handler

        return await cleanup_handler(keep=keep, containers_dir=containers_dir or None)

    @mcp.tool()
    async def container_status() -> dict:
        """One-shot dashboard combining Apptainer state (containers dir, active version, all versions), host package check (TeXLive, ImageMagick), and Docker Compose status for both dev+prod environments. Drop-in replacement for running `apptainer --version`, `dpkg -l texlive-*`, `docker compose ps` separately. Use when the user asks "is my container env healthy?", "show container status", "what's the dashboard?", or before a release / on a new machine."""
        from ._mcp.handlers import status_handler

        return await status_handler()

    @mcp.tool()
    async def sandbox_create(
        source_sif: str,
        output_dir: str = "",
        force: bool = False,
    ) -> dict:
        """Unpack a read-only SIF into a writable directory so you can `apptainer shell --writable sandbox/` and patch packages / configs inside, then rebuild a new SIF from it. Drop-in replacement for `apptainer build --sandbox sandbox/ image.sif`. Use when the user asks to "make this container editable", "open the SIF for editing", "create a sandbox to debug", "patch inside the container", or is iterating on a broken image.

        Args:
            source_sif: Path to the source .sif file.
            output_dir: Output sandbox path (defaults to <sif_stem>-sandbox/).
            force: Overwrite if the sandbox already exists.
        """
        from ._mcp.handlers import sandbox_create_handler

        return await sandbox_create_handler(
            source_sif=source_sif,
            output_dir=output_dir or None,
            force=force,
        )

    @mcp.tool()
    async def docker_rebuild(env: str = "dev") -> dict:
        """Force a from-scratch Docker Compose rebuild (`docker compose build --no-cache && up -d`) of the dev or prod stack, bypassing stale layer cache that hides Dockerfile changes. Drop-in replacement for `docker compose -f docker-compose.dev.yml build --no-cache && docker compose up -d`. Use when the user asks to "rebuild docker", "force rebuild the stack", "the Docker cache is stale", "recreate compose services", or after editing a Dockerfile.

        Args:
            env: Environment name used to locate the compose file (dev/prod).
        """
        from ._mcp.handlers import docker_rebuild_handler

        return await docker_rebuild_handler(env=env)

    @mcp.tool()
    async def docker_restart(env: str = "dev") -> dict:
        """Bounce a Docker Compose stack (`compose down` + `compose up -d`) without rebuilding — preserves images, wipes running state, re-reads env vars + volume mounts. Drop-in replacement for `docker compose down && docker compose up -d`. Use when the user asks to "restart docker", "bounce the stack", "the service is stuck", "reload env vars", or after editing `.env` / compose.yml.

        Args:
            env: Environment name (dev/prod).
        """
        from ._mcp.handlers import docker_restart_handler

        return await docker_restart_handler(env=env)

    @mcp.tool()
    async def host_install(
        texlive: bool = False,
        imagemagick: bool = False,
        all: bool = True,  # noqa: A002
    ) -> dict:
        """Apt-install the host-side dependencies SciTeX containers bind-mount or shell out to — TeXLive (for scitex-writer LaTeX compile) and ImageMagick (for figure conversion). Drop-in replacement for copy-pasting `sudo apt install texlive-full imagemagick` onto every new machine. Use when the user asks to "install host dependencies", "set up a new machine for scitex", "install TeXLive", "install ImageMagick", or onboards a fresh workstation.

        Args:
            texlive: Install TeXLive packages.
            imagemagick: Install ImageMagick.
            all: Install all packages (default when no specific flag is set).
        """
        from ._mcp.handlers import host_install_handler

        return await host_install_handler(
            texlive=texlive, imagemagick=imagemagick, all=all
        )

    @mcp.tool()
    async def host_check() -> dict:
        """Probe the host for required SciTeX packages (TeXLive, ImageMagick) and report version / path / missing. Drop-in replacement for `dpkg -l texlive-*`, `which convert`, `pdflatex --version`. Use when the user asks "is TeXLive installed?", "why is LaTeX compile failing?", "audit host packages", or is diagnosing a scitex-writer build error."""
        from ._mcp.handlers import host_check_handler

        return await host_check_handler()

    @mcp.tool()
    async def container_verify(
        sif_path: str = "",
        def_path: str = "",
        lock_dir: str = "",
    ) -> dict:
        """Cryptographic + provenance audit of a SIF — recompute SHA256 and compare against the saved lock, verify the `.def` recipe matches what built the image, diff pip/conda/apt lock against container reality. Catches tampering, accidental overwrites, lock/image drift. Drop-in replacement for `sha256sum image.sif` + manual `.def` diff + eyeballing lock files. Use when the user asks to "verify the container", "is this SIF tampered with?", "audit SIF provenance", "check lock file matches", or before a reproducibility claim / Clew commit.

        Args:
            sif_path: Path to .sif to verify (defaults to active SIF).
            def_path: Path to .def file to verify origin against.
            lock_dir: Directory with lock files (defaults to SIF directory).
        """
        from ._mcp.handlers import verify_handler

        return await verify_handler(
            sif_path=sif_path, def_path=def_path, lock_dir=lock_dir
        )

    @mcp.tool()
    async def container_env_snapshot(
        containers_dir: str = "",
        dev_repos: str = "",
    ) -> dict:
        """Freeze a complete reproducibility manifest into one JSON — active container version + SIF SHA256, host packages (TeXLive/ImageMagick versions), pip freeze, conda env export, apt dpkg list, every dev-repo git commit + dirty flag, and all lock file hashes — designed to be attached to a Clew claim / paper / experiment record. Drop-in replacement for hand-running `pip freeze > reqs.txt`, `conda env export > env.yml`, `dpkg -l > apt.txt`, `git rev-parse HEAD` across every repo, then gluing them together by hand. Use when the user asks to "snapshot my environment", "capture env for reproducibility", "freeze everything for a paper", "record container + host state", or is producing a `\\vclaim` provenance record.

        Args:
            containers_dir: Path to containers directory (auto-detected if empty).
            dev_repos: Comma-separated paths to git repos to include.
        """
        from ._mcp.handlers import env_snapshot_handler

        repos = (
            [r.strip() for r in dev_repos.split(",") if r.strip()]
            if dev_repos
            else None
        )
        return await env_snapshot_handler(
            containers_dir=containers_dir or None,
            dev_repos=repos,
        )

    # §5 — skills introspection tools (per audit-mcp-tools convention)
    @mcp.tool()
    def container_skills_list() -> str:
        """List the names of every skill page shipped by scitex-container.

        Returns
        -------
            JSON string with `{"success": true, "package": "scitex-container",
            "skills": ["01_quick-start", "02_python-api", ...]}`.
        """
        import json
        from pathlib import Path

        try:
            skills_dir = Path(__file__).parent / "_skills" / "scitex-container"
            names = sorted(
                p.stem for p in skills_dir.glob("*.md") if p.name != "SKILL.md"
            )
            return json.dumps(
                {"success": True, "package": "scitex-container", "skills": names},
                indent=2,
            )
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @mcp.tool()
    def container_skills_get(name: str) -> str:
        """Fetch the full Markdown content of one scitex-container skill page.

        Args:
            name: Skill page name without `.md`, e.g. `01_quick-start`.

        Returns
        -------
            JSON string with `{"success": true, "package": "scitex-container",
            "name": <name>, "content": <markdown>}`, or an error envelope.
        """
        import json
        from pathlib import Path

        try:
            skills_dir = Path(__file__).parent / "_skills" / "scitex-container"
            target = skills_dir / f"{name}.md"
            if not target.exists():
                available = sorted(
                    p.stem for p in skills_dir.glob("*.md") if p.name != "SKILL.md"
                )
                return json.dumps(
                    {
                        "success": False,
                        "error": f"unknown skill {name!r}; available: {available}",
                    },
                    indent=2,
                )
            return json.dumps(
                {
                    "success": True,
                    "package": "scitex-container",
                    "name": name,
                    "content": target.read_text(encoding="utf-8"),
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for scitex-container-mcp command (stdio transport)."""
    if not FASTMCP_AVAILABLE:
        import sys

        print("=" * 60)
        print("fastmcp is required: pip install 'scitex-container[mcp]'")
        print("=" * 60)
        sys.exit(1)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

# EOF
