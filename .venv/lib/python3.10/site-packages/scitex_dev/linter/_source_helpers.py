"""Source-level helper predicates for the SciTeX linter.

Extracted from ``checker.py`` to keep that module under the line-count cap.
``checker.py`` re-exports these names, so existing imports keep working
unchanged — notably ``from .checker import _is_allowed_by_comment`` in
``_fm_checker`` and the public ``is_script`` in the linter API list.
"""

import re
from pathlib import Path

__all__ = ["is_script", "_is_allowed_by_comment", "_STX_ALLOW_RE"]


def is_script(filepath: str, config=None) -> bool:
    """Check if file is a script (not a library module).

    Uses config.library_patterns and config.library_dirs to determine
    which files are library modules (exempt from script-only rules).
    """
    from .config import load_config, matches_library_pattern

    if config is None:
        config = load_config(start_path=filepath)

    path = Path(filepath)
    name = path.name

    # Check filename against library patterns (e.g., __*__.py, test_*.py)
    if matches_library_pattern(name, config):
        return False

    # Check if file is inside a library directory (e.g., src/)
    parts = path.parts
    for lib_dir in config.library_dirs:
        if lib_dir in parts:
            return False

    # Check if file is inside a script directory (e.g., scripts/)
    # These are utility scripts called by shell, not SciTeX session scripts
    for script_dir in config.script_dirs:
        if script_dir in parts:
            return False

    return True


# STX-allow regex.
#
# Before 2026-06-14 this was ``r"#\s*stx-allow\b(?::?\s*(.+))?"`` — the
# greedy ``.+`` captured EVERYTHING after the colon, including prose. So
# ``# stx-allow: STX-P006  (prose explanation)`` parsed the ids string as
# ``"STX-P006  (prose explanation)"``, the comma-split saw a single
# element that didn't equal ``STX-P006``, and the suppression silently
# failed. Operators kept hitting this when annotating with reasons inline
# (neurovista elevation 2026-06-14, item 6).
#
# Tightened regex captures ONLY characters valid in a rule-id list:
# uppercase letters, digits, dash, comma, whitespace. Stops at the first
# non-matching character so inline prose after the ids is ignored.
# Supported forms (now correct):
#
#   x  # stx-allow                         → bare; suppress ALL
#   x  # stx-allow: STX-S003               → suppress STX-S003
#   x  # stx-allow: STX-S003, STX-I001     → suppress both
#   x  # stx-allow: STX-S003  (because foo) → suppress STX-S003; ignore prose
#
# The form ``# stx-allow:lower-case-id`` is still NOT supported — rule
# ids are uppercase by convention; lower-case suggests a typo. The regex
# stops at the lower-case letter and the id list is empty → bare-allow
# fallback (suppress all on the line) does NOT fire because the colon
# was consumed; it's a no-op suppression — visible as a non-matching
# rule. That's the desired loud behaviour.
_STX_ALLOW_RE = re.compile(r"#\s*stx-allow\b(?::\s*([A-Z0-9\-,\s]*))?")


def _is_allowed_by_comment(source_line: str, rule_id: str) -> bool:
    """Check if a source line has a ``# stx-allow`` comment suppressing *rule_id*.

    Supported forms::

        x = 1  # stx-allow                     → suppresses ALL rules on this line
        x = 1  # stx-allow: STX-S003           → suppresses STX-S003
        x = 1  # stx-allow: STX-S003, STX-I001 → suppresses both
    """
    if not source_line:
        return False
    m = _STX_ALLOW_RE.search(source_line)
    if m is None:
        return False
    ids_str = m.group(1)
    if not ids_str:
        return True  # bare ``# stx-allow`` suppresses everything
    allowed = {s.strip() for s in ids_str.split(",")}
    return rule_id in allowed
