"""Category NL: numeric-literal rules (PEP 515 `_` separators).

See `_skills/general/03_interface/01_python-api/14_numeric-literals.md`
for the rationale and carve-outs (years, ports, HTTP codes).
"""

from ._base import Rule

NL001 = Rule(
    id="STX-NL001",
    severity="warning",
    category="style",
    message=(
        "Integer literal with four or more digits should use `_` "
        "thousands separators (PEP 515)."
    ),
    suggestion=(
        "Rewrite `21600` as `21_600`, `1048576` as `1_048_576`. "
        "Identifiers that read as a whole (years, ports, HTTP codes) "
        "may stay bare — see the carve-outs in "
        "`_skills/general/03_interface/01_python-api/14_numeric-literals.md`. "
        "Suppress per-line with `# stx-allow: STX-NL001` when an identifier "
        "should not be split."
    ),
)
