#!/usr/bin/env python3
# Timestamp: "2026-05-24"
# File: src/scitex_container/apptainer/_lockgen.py
"""Lock capture, locked-def generation, and version-set comparison.

Three pure pieces of the reproducible round-trip:

1. ``capture_lock`` — introspect a built SIF for the *actually installed*
   versions (pip / dpkg / node) and write a single combined ``.lock``
   file. The lock is only knowable post-build; that's why up-front
   pinning is impossible and the round-trip is needed.
2. ``generate_locked_def`` — emit a new ``.def`` from a rough ``.def``
   plus a captured lock, pinning every pip package to its frozen
   version (``pip install pkg==ver``). apt/node pinning is captured in
   the lock for the round-trip comparison but apt-version injection is
   deferred (operator step 3) — the version-set comparison still proves
   reproducibility of the pip surface, the dominant drift source.
3. ``compare_locks`` — the round-trip gate: are two locks' version sets
   identical? Returns a structured diff naming what drifted.

The on-disk ``.lock`` format is a single text file with section headers
so a human can read it and ``compare_locks`` can parse it back::

    # scitex-container lock
    [pip]
    numpy==2.1.0
    ...
    [dpkg]
    libc6=2.39-0ubuntu8
    ...
    [node]
    {"dependencies": {...}}
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from scitex_container._compat import supports_return_as

from ._utils import detect_container_cmd

logger = logging.getLogger(__name__)

_SECTIONS = ("pip", "dpkg", "node")


@dataclass
class Lock:
    """Parsed version sets captured from a SIF.

    pip / dpkg are ``{name: version}`` maps; node is the raw
    ``npm list -g --json`` text (kept verbatim — the JSON shape is the
    version set for node globals).
    """

    pip: dict[str, str] = field(default_factory=dict)
    dpkg: dict[str, str] = field(default_factory=dict)
    node: str = ""

    def version_set(self) -> dict[str, str]:
        """Flat ``{qualified_name: version}`` map for set comparison.

        node packages are flattened from the npm JSON into
        ``node:<name> -> <version>`` entries so a node-global drift is
        caught by the same comparison as pip/dpkg.
        """
        merged: dict[str, str] = {}
        for name, ver in self.pip.items():
            merged[f"pip:{name}"] = ver
        for name, ver in self.dpkg.items():
            merged[f"dpkg:{name}"] = ver
        for name, ver in _parse_node_versions(self.node).items():
            merged[f"node:{name}"] = ver
        return merged


def _parse_node_versions(node_json: str) -> dict[str, str]:
    """Extract ``{name: version}`` from ``npm list -g --json`` output."""
    if not node_json.strip():
        return {}
    try:
        data = json.loads(node_json)
    except (json.JSONDecodeError, ValueError):
        return {}
    deps = data.get("dependencies", {}) if isinstance(data, dict) else {}
    out: dict[str, str] = {}
    for name, info in deps.items():
        if isinstance(info, dict) and "version" in info:
            out[name] = str(info["version"])
    return out


def _parse_pip_freeze(text: str) -> dict[str, str]:
    """Parse ``pip freeze`` output into ``{name: version}``.

    Handles the common ``name==ver`` form; lines without ``==`` (editable
    installs, VCS pins, ``-e`` URLs) are kept under their raw key so a
    drift in them is still caught.
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" in line:
            name, ver = line.split("==", 1)
            out[name.strip().lower()] = ver.strip()
        else:
            # editable / VCS / url pin — key on the whole line, no version
            out[line] = ""
    return out


def _parse_dpkg(text: str) -> dict[str, str]:
    """Parse ``dpkg-query -W -f=${Package}=${Version}`` into a map."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        name, ver = line.split("=", 1)
        out[name.strip()] = ver.strip()
    return out


@supports_return_as
def capture_lock(
    sif_path: str | Path,
    lock_path: str | Path,
) -> Lock:
    """Introspect a built SIF and write a combined ``.lock`` file.

    Parameters
    ----------
    sif_path : str or Path
        Path to the built ``.sif``.
    lock_path : str or Path
        Destination for the combined lock file (``<layer>-<ts>.lock``).

    Returns
    -------
    Lock
        The captured version sets.

    Raises
    ------
    FileNotFoundError
        If the SIF or the container command is missing.
    """
    sif_path = Path(sif_path)
    if not sif_path.exists():
        raise FileNotFoundError(f"SIF not found: {sif_path}")

    cmd = detect_container_cmd()
    lock = Lock()

    # pip may be `pip` or `pip3` depending on the base image; try both and
    # take the first that yields output.
    for pip_bin in ("pip", "pip3"):
        pip_out = _exec_capture(cmd, sif_path, [pip_bin, "freeze"])
        if pip_out.strip():
            lock.pip = _parse_pip_freeze(pip_out)
            break

    dpkg_out = _exec_capture(
        cmd, sif_path, ["dpkg-query", "-W", "-f=${Package}=${Version}\n"]
    )
    lock.dpkg = _parse_dpkg(dpkg_out)

    node_out = _exec_capture(
        cmd, sif_path, ["npm", "list", "-g", "--depth=0", "--json"]
    )
    lock.node = node_out

    write_lock(lock, lock_path)
    logger.info(
        "Captured lock: %d pip, %d dpkg, %d node packages",
        len(lock.pip),
        len(lock.dpkg),
        len(_parse_node_versions(lock.node)),
    )
    return lock


def _exec_capture(cmd: str, sif_path: Path, argv: list[str]) -> str:
    """Run an introspection command inside the SIF, isolated from the host.

    Uses ``--cleanenv --no-home --containall`` so the *container's* own
    package managers and site-packages are introspected — NOT the host's.
    Without these, apptainer auto-mounts ``$HOME`` and inherits the host
    ``PATH`` / ``PYTHONPATH`` / ``~/.local``, so ``pip freeze`` would
    capture the host environment and silently defeat reproducibility.

    Returns the command's stdout, or ``""`` when it fails (e.g. the tool
    is absent from this base image).
    """
    result = subprocess.run(
        [cmd, "exec", "--cleanenv", "--no-home", str(sif_path), *argv],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


@supports_return_as
def write_lock(lock: Lock, lock_path: str | Path) -> Path:
    """Serialize a ``Lock`` to the combined ``.lock`` text format."""
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# scitex-container lock", "[pip]"]
    for name in sorted(lock.pip):
        ver = lock.pip[name]
        lines.append(f"{name}=={ver}" if ver else name)
    lines.append("[dpkg]")
    for name in sorted(lock.dpkg):
        lines.append(f"{name}={lock.dpkg[name]}")
    lines.append("[node]")
    lines.append(lock.node.strip())

    lock_path.write_text("\n".join(lines) + "\n")
    return lock_path


@supports_return_as
def read_lock(lock_path: str | Path) -> Lock:
    """Parse a combined ``.lock`` file back into a ``Lock``."""
    lock_path = Path(lock_path)
    text = lock_path.read_text()
    lock = Lock()

    section: str | None = None
    node_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        m = re.match(r"^\[(\w+)\]$", stripped)
        if m and m.group(1) in _SECTIONS:
            section = m.group(1)
            continue
        if section == "pip":
            if not stripped:
                continue
            if "==" in stripped:
                name, ver = stripped.split("==", 1)
                lock.pip[name.strip().lower()] = ver.strip()
            else:
                lock.pip[stripped] = ""
        elif section == "dpkg":
            if not stripped or "=" not in stripped:
                continue
            name, ver = stripped.split("=", 1)
            lock.dpkg[name.strip()] = ver.strip()
        elif section == "node":
            node_lines.append(line)

    lock.node = "\n".join(node_lines).strip()
    return lock


@supports_return_as
def generate_locked_def(
    rough_def: str | Path,
    lock: Lock,
    out_def: str | Path,
) -> Path:
    """Emit a version-pinned ``.def`` from a rough ``.def`` + a lock.

    The locked def is the rough def with a pinned-pip ``%post`` stanza
    appended: ``pip install pkg==ver ...`` for every frozen pip package.
    Re-installing already-installed packages at their exact versions is a
    no-op in the happy path and *forces* the pin in the drift path — so a
    rebuild from this def reproduces the captured pip version set.

    apt/node version sets are recorded in the lock and compared by the
    round-trip, but apt-version injection into the def is deferred
    (operator step 3 — ``pkg=ver`` from dpkg or ``snapshot.ubuntu.com``).

    Parameters
    ----------
    rough_def : str or Path
        The loosely-pinned recipe the rough build used.
    lock : Lock
        Captured versions from the rough build.
    out_def : str or Path
        Destination for the generated locked ``.def``.

    Returns
    -------
    Path
        Path to the written locked ``.def``.
    """
    rough_def = Path(rough_def)
    out_def = Path(out_def)
    base = rough_def.read_text()

    pins = [f"{name}=={ver}" for name, ver in sorted(lock.pip.items()) if ver]

    stanza_lines = [
        "",
        "# --- scitex-container: pinned pip versions (generated) ---------------",
        "# Re-pin every pip package to the version frozen from the rough build.",
        "# A no-op when the resolver already lands these versions; forces the",
        "# pin when it would otherwise drift. Reproduces the captured pip set.",
        "%post",
        "    set -e",
    ]
    if pins:
        # Heredoc a requirements file rather than a long argv — robust to
        # any pin count and shell-quoting-safe.
        stanza_lines.append("    cat > /tmp/scitex-pins.txt <<'SCITEX_PINS'")
        for pin in pins:
            stanza_lines.append(f"{pin}")
        stanza_lines.append("SCITEX_PINS")
        # Pick the pip the base ships (pip / pip3) and add
        # --break-system-packages only when this pip understands it
        # (PEP 668 environments: Ubuntu 24.04, Debian 12, alpine 3.19+).
        # --no-deps: pin exactly the captured set without re-resolving.
        stanza_lines += [
            '    _pip="$(command -v pip3 || command -v pip)"',
            '    _bsp=""',
            '    if "$_pip" install --help 2>/dev/null | grep -q -- '
            "--break-system-packages; then",
            '        _bsp="--break-system-packages"',
            "    fi",
            '    "$_pip" install --no-deps $_bsp -r /tmp/scitex-pins.txt',
            "    rm -f /tmp/scitex-pins.txt",
        ]
    else:
        stanza_lines.append("    : # no pip packages captured")
    stanza_lines.append(
        "# --- end scitex-container pins ---------------------------------------"
    )
    stanza_lines.append("")

    out_def.parent.mkdir(parents=True, exist_ok=True)
    out_def.write_text(base.rstrip("\n") + "\n" + "\n".join(stanza_lines))
    logger.info(
        "Generated locked def with %d pinned pip packages: %s", len(pins), out_def
    )
    return out_def


@dataclass(frozen=True)
class LockDiff:
    """Result of comparing two locks' version sets."""

    identical: bool
    changed: dict[str, tuple[str, str]] = field(default_factory=dict)  # name -> (a, b)
    only_in_a: dict[str, str] = field(default_factory=dict)
    only_in_b: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        """One-paragraph human summary of the drift, or 'identical'."""
        if self.identical:
            return "version sets identical"
        parts: list[str] = []
        if self.changed:
            sample = ", ".join(
                f"{n}: {a} -> {b}" for n, (a, b) in sorted(self.changed.items())[:10]
            )
            parts.append(f"{len(self.changed)} changed ({sample})")
        if self.only_in_a:
            parts.append(f"{len(self.only_in_a)} only in rough")
        if self.only_in_b:
            parts.append(f"{len(self.only_in_b)} only in rebuild")
        return "; ".join(parts)


@supports_return_as
def compare_locks(lock_a: Lock, lock_b: Lock) -> LockDiff:
    """Compare two locks' flat version sets — the round-trip gate.

    Parameters
    ----------
    lock_a, lock_b : Lock
        The rough-build lock and the rebuild lock.

    Returns
    -------
    LockDiff
        ``identical=True`` when every package name maps to the same
        version in both; otherwise the structured diff names every
        changed / added / missing package.
    """
    set_a = lock_a.version_set()
    set_b = lock_b.version_set()

    names_a = set(set_a)
    names_b = set(set_b)

    only_in_a = {n: set_a[n] for n in names_a - names_b}
    only_in_b = {n: set_b[n] for n in names_b - names_a}
    changed = {
        n: (set_a[n], set_b[n]) for n in names_a & names_b if set_a[n] != set_b[n]
    }

    identical = not (changed or only_in_a or only_in_b)
    return LockDiff(
        identical=identical,
        changed=changed,
        only_in_a=only_in_a,
        only_in_b=only_in_b,
    )


# EOF
