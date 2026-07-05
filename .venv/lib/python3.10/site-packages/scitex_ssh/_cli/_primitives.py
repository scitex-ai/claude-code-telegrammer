#!/usr/bin/env python3
"""CLI commands for SSH primitives (exec/copy/attach)."""

from __future__ import annotations

import shlex

import click


def _split_opts(s: str | None) -> list[str]:
    return shlex.split(s) if s else []


@click.command("exec")
@click.argument("host")
@click.argument("command")
@click.option(
    "--ssh-opts",
    default=None,
    help='Extra ssh flags as a single shell-quoted string (e.g. "-A -o StrictHostKeyChecking=no").',
)
@click.option("--timeout", type=float, default=None, help="Timeout in seconds.")
@click.option("--dry-run", is_flag=True, help="Print plan without running command.")
@click.option(
    "-y", "--yes", is_flag=True, help="Suppress interactive confirmation (assume yes)."
)
def exec_cmd(host, command, ssh_opts, timeout, dry_run, yes):
    """Run a command on HOST via ssh.

    \b
    Example:
      $ scitex-ssh exec myhost "uname -a"
      $ scitex-ssh exec myhost "ls /tmp" --timeout 5
      $ scitex-ssh exec myhost "rm -rf /tmp/foo" --dry-run
    """
    if dry_run:
        click.echo(
            f"DRY RUN — would exec on {host}: {command} "
            f"(ssh_opts={ssh_opts!r}, timeout={timeout})"
        )
        return
    from scitex_ssh import exec_remote

    result = exec_remote(host, command, ssh_opts=_split_opts(ssh_opts), timeout=timeout)
    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.stderr:
        click.echo(result.stderr, err=True, nl=False)
    raise SystemExit(result.returncode)


def _split_host_path(arg: str) -> tuple[str | None, str]:
    """Return (host, path) for HOST:PATH; (None, path) for local."""
    # Be tolerant of Windows-style or absolute paths without colon.
    if ":" in arg and not arg.startswith("/") and not arg.startswith("./"):
        host, _, path = arg.partition(":")
        if host and "/" not in host:
            return host, path
    return None, arg


@click.command("copy")
@click.argument("src")
@click.argument("dest")
@click.option("-r", "--recursive", is_flag=True, help="Recursive copy.")
@click.option(
    "--ssh-opts",
    default=None,
    help="Extra ssh flags as a single shell-quoted string.",
)
@click.option("--dry-run", is_flag=True, help="Print plan without copying.")
@click.option(
    "-y", "--yes", is_flag=True, help="Suppress interactive confirmation (assume yes)."
)
def copy_cmd(src, dest, recursive, ssh_opts, dry_run, yes):
    """Copy files between local and a remote HOST:PATH.

    \b
    Example:
      $ scitex-ssh copy local.txt myhost:/tmp/local.txt
      $ scitex-ssh copy myhost:/etc/hostname ./hostname
      $ scitex-ssh copy ./dir/ myhost:/tmp/dir/ -r --dry-run
    """
    if dry_run:
        click.echo(f"DRY RUN — would copy {src} -> {dest} (recursive={recursive})")
        return
    from scitex_ssh import copy_from, copy_to

    src_host, src_path = _split_host_path(src)
    dest_host, dest_path = _split_host_path(dest)
    opts = _split_opts(ssh_opts)

    if src_host and not dest_host:
        result = copy_from(
            src_host, src_path, dest_path, recursive=recursive, ssh_opts=opts
        )
    elif dest_host and not src_host:
        result = copy_to(
            dest_host, src_path, dest_path, recursive=recursive, ssh_opts=opts
        )
    elif src_host and dest_host:
        click.secho(
            "ERROR: remote-to-remote copy is not supported.", fg="red", err=True
        )
        raise SystemExit(2)
    else:
        click.secho(
            "ERROR: at least one of SRC or DEST must be HOST:PATH.", fg="red", err=True
        )
        raise SystemExit(2)

    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.stderr:
        click.echo(result.stderr, err=True, nl=False)
    raise SystemExit(result.returncode)


@click.command("sync")
@click.argument("src")
@click.argument("dest")
@click.option(
    "--exclude",
    "exclude",
    multiple=True,
    help="Glob to exclude (repeatable), e.g. --exclude index.db --exclude '*.db-wal'.",
)
@click.option("--delete", is_flag=True, help="Mirror deletions (rsync --delete).")
@click.option(
    "--extra-opts",
    default=None,
    help='Extra rsync flags as one shell-quoted string (e.g. "--checksum --mkpath").',
)
@click.option(
    "--ssh-opts",
    default=None,
    help="Extra ssh flags as a single shell-quoted string (wired via rsync -e).",
)
@click.option("--dry-run", is_flag=True, help="Print plan without running rsync.")
@click.option(
    "-y", "--yes", is_flag=True, help="Suppress interactive confirmation (assume yes)."
)
def sync_cmd(src, dest, exclude, delete, extra_opts, ssh_opts, dry_run, yes):
    """Rsync a directory one-way between local and a remote HOST:PATH.

    \b
    Example:
      $ scitex-ssh sync ~/.scitex/scholar/library/ spartan:~/.scitex/scholar/library/ \\
          --exclude index.db --exclude '*.db-wal' --exclude '*.db-shm'
      $ scitex-ssh sync spartan:~/data/ ./data/ --delete
    """
    src_host, src_path = _split_host_path(src)
    dest_host, dest_path = _split_host_path(dest)

    if src_host and dest_host:
        click.secho(
            "ERROR: remote-to-remote sync is not supported.", fg="red", err=True
        )
        raise SystemExit(2)
    if not src_host and not dest_host:
        click.secho(
            "ERROR: exactly one of SRC or DEST must be HOST:PATH.", fg="red", err=True
        )
        raise SystemExit(2)

    if dest_host:
        direction, host, local, remote = "push", dest_host, src_path, dest_path
    else:
        direction, host, local, remote = "pull", src_host, dest_path, src_path

    if dry_run:
        click.echo(
            f"DRY RUN — would rsync ({direction}) {src} -> {dest} "
            f"(exclude={list(exclude)}, delete={delete})"
        )
        return

    from scitex_ssh import sync_dir

    result = sync_dir(
        host,
        local,
        remote,
        direction=direction,
        exclude=exclude,
        delete=delete,
        extra_opts=_split_opts(extra_opts),
        ssh_opts=_split_opts(ssh_opts),
    )
    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.stderr:
        click.echo(result.stderr, err=True, nl=False)
    raise SystemExit(result.returncode)


@click.command("attach")
@click.argument("host")
@click.option("--command", "-c", default=None, help="Command to run after attaching.")
@click.option(
    "--ssh-opts",
    default=None,
    help="Extra ssh flags as a single shell-quoted string.",
)
def attach_cmd(host, command, ssh_opts):
    """Open an interactive ssh -t session to HOST.

    \b
    Example:
      $ scitex-ssh attach myhost
      $ scitex-ssh attach myhost --command "tmux attach -t main"
    """
    from scitex_ssh import attach

    rc = attach(host, command, ssh_opts=_split_opts(ssh_opts))
    raise SystemExit(rc)


# EOF
