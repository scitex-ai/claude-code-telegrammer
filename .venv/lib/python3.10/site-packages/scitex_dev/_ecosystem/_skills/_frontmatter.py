"""YAML frontmatter utilities for skill markdown files."""

from __future__ import annotations

from pathlib import Path


def _parse_frontmatter(path: Path) -> dict[str, str]:
    """Parse YAML frontmatter from a markdown file."""
    try:
        text = path.read_text()
    except Exception:
        return {}

    if not text.startswith("---"):
        return {}

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    result = {}
    for line in parts[1].strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _stamp_frontmatter_field(content: str, key: str, value: str) -> str:
    """Set or insert a field in a markdown file's YAML frontmatter.

    Used at ``skills export`` time to stamp every cached leaf with the
    exporting package's ``version`` and ``exported_via`` fields. The
    runtime drift check (``skills get`` / ``skills list``) reads these
    stamps to compare against ``importlib.metadata.version()``.
    """
    import re

    if re.search(rf"^{key}:", content, re.MULTILINE):
        return re.sub(
            rf"^({key}:\s*).*$",
            rf"\g<1>{value}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    # Insert before the closing ``---`` of the frontmatter block. If the
    # file has no frontmatter (legacy), prepend a minimal block.
    if content.startswith("---\n"):
        # Find the second ``---\n`` and insert before it.
        end = content.find("\n---\n", 4)
        if end != -1:
            return content[: end + 1] + f"{key}: {value}\n" + content[end + 1 :]
    # No frontmatter at all — prepend a minimal one.
    return f"---\n{key}: {value}\n---\n\n" + content
