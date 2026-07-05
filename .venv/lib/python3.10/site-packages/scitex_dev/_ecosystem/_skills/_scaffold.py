"""Scaffold a `_skills/<pip-name>/` directory for a SciTeX package.

Backs `scitex-dev skills init`. Mirrors the standard-template spec at
`general/03_interface/04_skills/13_standard-template.md` so a fresh
package starts auditor-clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Single source of truth for the leaf bodies. Kept short on purpose —
# the spec leaf has the full reference; this is just enough to clear
# auditor checks and prompt the author to fill in real content.

_SKILL_MD = """\
---
name: {pip}
description: |
  [WHAT] TODO: one-line verb-phrase describing what {pip} does.
  [WHEN] TODO: trigger condition (when an agent should reach for this).
  [HOW] TODO: primary entry point — e.g., `import {imp}` or `{pip} --help`.
tags: [{tag}]
{allowed_tools_line}primary_interface: python
interfaces:
  python: 3
  cli: {cli_n}
  mcp: {mcp_n}
  skills: 3
  http: {http_n}
---

# {pip}

TODO: one-paragraph overview. Lives here, not in a separate `00_overview.md`.

## Sub-skills

### Core (01–09)
- [01_installation.md](01_installation.md) — install + import sanity check
- [02_quick-start.md](02_quick-start.md) — 30-second tour
- [03_python-api.md](03_python-api.md) — Python API surface
{cli_index_line}{mcp_index_line}{http_index_line}
### Meta (20+)
{env_index_line}"""

_INSTALL_MD = """\
---
description: |
  [TOPIC] Installation
  [DETAILS] pip install {pip}; verify with `python -c "import {imp}"`.
tags: [{tag}-installation]
---

# Installation

```bash
pip install {pip}
```

System requirements: Python ≥ 3.11.
"""

_QUICKSTART_MD = """\
---
description: |
  [TOPIC] Quick Start
  [DETAILS] Smallest useful example demonstrating the primary use case in
  under 30 seconds.
tags: [{tag}-quick-start]
---

# Quick Start

```python
import {imp}
# TODO: smallest useful example
```
"""

_PYTHON_API_MD = """\
---
description: |
  [TOPIC] Python API
  [DETAILS] Public Python API of {pip} — exported functions, signatures,
  return types, and minimal usage examples per function.
tags: [{tag}-python-api]
---

# Python API

```python
from {imp} import TODO
```

## TODO(arg1, arg2=default) -> ReturnType

TODO: example, expected output, edge cases.
"""

_CLI_REF_MD = """\
---
description: |
  [TOPIC] CLI Reference
  [DETAILS] {pip} CLI subcommands — noun-verb structure with universal flags.
tags: [{tag}-cli-reference]
---

# CLI Reference

```bash
{pip} --help
```

| Command | Purpose |
|---|---|
| `{pip} <noun> <verb>` | TODO |

See `general/03_interface/02_cli/`.
"""

_MCP_TOOLS_MD = """\
---
description: |
  [TOPIC] MCP Tools
  [DETAILS] MCP tools registered by {pip} — agent-callable surface.
tags: [{tag}-mcp-tools]
---

# MCP Tools

| Tool | Purpose |
|---|---|
| `{imp}_<verb>_<noun>` | TODO |

See `general/03_interface/03_mcp/`.
"""

_HTTP_API_MD = """\
---
description: |
  [TOPIC] HTTP API
  [DETAILS] HTTP routes shipped by {pip} — request/response shapes.
tags: [{tag}-http-api]
---

# HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/TODO` | TODO |
"""

_ENV_VARS_MD = """\
---
description: |
  [TOPIC] Environment Variables
  [DETAILS] SCITEX_<MODULE>_* variables read by {pip}; defaults and effects.
tags: [{tag}-env-vars]
---

# Environment Variables

| Name | Default | Purpose |
|---|---|---|
| `SCITEX_<MODULE>_<NAME>` | `<default>` | TODO |

See `general/01_ecosystem/04_environment-variables.md`.
"""


@dataclass(frozen=True)
class ScaffoldPlan:
    """What `scaffold_package_skills` would (or did) write."""

    dest: Path
    files: dict[str, str]  # relative filename → content


def _short_tag(pip_name: str) -> str:
    """Tag stem for frontmatter — drops a leading `scitex-` if any."""
    return pip_name


def build_plan(
    *,
    pip_name: str,
    import_name: str,
    dest: Path,
    with_cli: bool = True,
    with_mcp: bool = False,
    with_http: bool = False,
    with_env: bool = True,
) -> ScaffoldPlan:
    """Build the in-memory scaffold without touching the filesystem."""
    tag = _short_tag(pip_name)
    fmt = dict(pip=pip_name, imp=import_name, tag=tag)

    cli_index_line = (
        "- [04_cli-reference.md](04_cli-reference.md) — CLI subcommands\n"
        if with_cli
        else ""
    )
    mcp_index_line = (
        "- [05_mcp-tools.md](05_mcp-tools.md) — MCP tool surface\n" if with_mcp else ""
    )
    http_index_line = (
        "- [06_http-api.md](06_http-api.md) — HTTP routes\n" if with_http else ""
    )
    env_index_line = (
        "- [20_env-vars.md](20_env-vars.md) — Environment variables\n"
        if with_env
        else "- TODO: add a 20_env-vars.md when the package reads any env var.\n"
    )
    allowed_tools_line = f"allowed-tools: mcp__{import_name}__*\n" if with_mcp else ""

    skill_md = _SKILL_MD.format(
        **fmt,
        allowed_tools_line=allowed_tools_line,
        cli_n=2 if with_cli else 0,
        mcp_n=2 if with_mcp else 0,
        http_n=2 if with_http else 0,
        cli_index_line=cli_index_line,
        mcp_index_line=mcp_index_line,
        http_index_line=http_index_line,
        env_index_line=env_index_line,
    )

    files: dict[str, str] = {
        "SKILL.md": skill_md,
        "01_installation.md": _INSTALL_MD.format(**fmt),
        "02_quick-start.md": _QUICKSTART_MD.format(**fmt),
        "03_python-api.md": _PYTHON_API_MD.format(**fmt),
    }
    if with_cli:
        files["04_cli-reference.md"] = _CLI_REF_MD.format(**fmt)
    if with_mcp:
        files["05_mcp-tools.md"] = _MCP_TOOLS_MD.format(**fmt)
    if with_http:
        files["06_http-api.md"] = _HTTP_API_MD.format(**fmt)
    if with_env:
        files["20_env-vars.md"] = _ENV_VARS_MD.format(**fmt)

    return ScaffoldPlan(dest=dest, files=files)


def scaffold_package_skills(
    plan: ScaffoldPlan,
    *,
    force: bool = False,
) -> tuple[list[Path], list[Path]]:
    """Materialize `plan` on disk. Returns (written, skipped) absolute paths.

    Skips any file that already exists unless `force=True`. Never deletes.
    When SKILL.md is in the skipped set (existing file preserved), the
    function still appends references to any newly-written leaves to that
    SKILL.md so the auditor's SK-302 (leaf-not-referenced) check stays clean.
    """
    plan.dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    skipped: list[Path] = []
    for rel, body in plan.files.items():
        target = plan.dest / rel
        if target.exists() and not force:
            skipped.append(target)
            continue
        target.write_text(body)
        written.append(target)
    _update_skill_index(plan.dest, written)
    return written, skipped


_SUBSKILL_HEADING = "## Sub-skills"

_LEAF_BLURBS = {
    "01_installation.md": "install + import sanity check",
    "02_quick-start.md": "30-second tour",
    "03_python-api.md": "Python API surface",
    "04_cli-reference.md": "CLI subcommands",
    "05_mcp-tools.md": "MCP tool surface",
    "06_http-api.md": "HTTP routes",
    "20_env-vars.md": "Environment variables",
}


def _update_skill_index(dest: Path, written: list[Path]) -> None:
    """Append refs for newly-written leaves to an existing SKILL.md.

    No-op if SKILL.md doesn't exist (caller wrote a fresh one with full
    index already), or if the leaf is already referenced.
    """
    skill = dest / "SKILL.md"
    if not skill.exists() or skill in written:
        return
    text = skill.read_text()
    new_leaves = [p for p in written if p.name != "SKILL.md" and p.name not in text]
    if not new_leaves:
        return
    new_lines = [
        f"- [{p.name}]({p.name}) — {_LEAF_BLURBS.get(p.name, 'TODO')}"
        for p in sorted(new_leaves, key=lambda x: x.name)
    ]
    if _SUBSKILL_HEADING in text:
        text = text.rstrip() + "\n" + "\n".join(new_lines) + "\n"
    else:
        text = (
            text.rstrip() + f"\n\n{_SUBSKILL_HEADING}\n\n" + "\n".join(new_lines) + "\n"
        )
    skill.write_text(text)


__all__ = ["ScaffoldPlan", "build_plan", "scaffold_package_skills"]
