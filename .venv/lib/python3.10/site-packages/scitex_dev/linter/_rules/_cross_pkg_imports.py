"""Category I: cross-package private-submodule import rule (I008).

Flags importing a *peer* scitex package's underscore-prefixed (private)
submodule, e.g. ``from scitex_io._save import save``. Reaching into a peer's
private internals is fragile: a historical case was the scitex-gen
``_norm`` -> ``_numeric._norm`` reorg, which silently broke scitex-dsp and
scitex-nn (both had imported the private path directly). The same risk
applies to every peer: scitex_io._save, scitex_str._color_text, etc.

Packages must depend only on a peer's *public* API
(``from scitex_io import save``). Same-package private imports — a module
inside ``scitex_io`` importing ``scitex_io._save`` — are allowed; only
*cross*-package private imports are flagged.
"""

from ._base import Rule

I008 = Rule(
    id="STX-I008",
    severity="warning",
    category="import",
    message=(
        "Cross-package import of a peer's PRIVATE submodule — import the "
        "peer's public API instead"
    ),
    suggestion=(
        "Reaching into another scitex package's underscore-prefixed module "
        "(e.g. `from scitex_io._save import save`) is fragile: the peer "
        "can rename or move that private path without notice. Import the "
        "public symbol instead (e.g. `from scitex_io import save`). If "
        "the symbol is not yet public, ask the owning package to export it."
    ),
)
