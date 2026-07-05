"""Category P (plot): session-injected ``plt`` over top-level ``figrecipe``.

``STX-P010`` flags figure work done through a *top-level* ``figrecipe``
import inside a module whose ``main(...)`` is decorated with
``@stx.session``. The session decorator already INJECTS a fully-styled
``plt`` (a figrecipe-backed pyplot facade) into the function signature —
``def main(..., plt=stx.session.INJECTED): fig, ax = plt.subplots()``.

Reaching for ``import figrecipe as fr`` and calling ``fr.subplots(...)``
(or any other ``fr.<call>``) inside that module bypasses the injected
handle: the figure is no longer wired to the session's output directory,
the SCITEX_STYLE font/line/marker sizes are not guaranteed to be applied
the same way, and per-call style overrides (``fontsize=``, ``figsize=``)
creep back in — the exact regressions STX-P007 (no ``fontsize=``) and
STX-FM010 (``set_xyt`` over separate label setters) already guard.

This is an ENGINE rule (not a figrecipe-plugin rule like STX-P001-P009)
because it is fundamentally about the ``@stx.session`` injection contract
— the same surface as STX-S006 (declare the INJECTED params) and STX-I009
(don't import seaborn; use the wrapper). It is the next free STX-P code
(P001-P009 are taken by figrecipe's plugin). Per neurovista handoff
2026-06-14 (Ask 1).

The ``requires="scitex"`` gate matches the sibling session/figure rules:
the recommendation only makes sense when the umbrella that supplies the
injected ``plt`` is installed.
"""

from ._base import Rule

# Shared fix-it text — kept verbatim across the import-level and call-level
# detections so the agent sees a single consistent remediation regardless
# of which shape (``import figrecipe`` vs ``fr.subplots(...)``) tripped it.
_P010_SUGGESTION = (
    "Use the session-injected `plt.subplots` instead of top-level "
    "figrecipe:\n"
    "  @stx.session\n"
    "  def main(..., plt=stx.session.INJECTED):\n"
    "      fig, ax = plt.subplots()   # figrecipe-backed, wired to the\n"
    "                                 # session output dir\n"
    "Font sizes come from SCITEX_STYLE — drop per-call `fontsize=` "
    "(see STX-P007). Set labels with `ax.set_xyt(x, y, t)` (STX-FM010)."
)

P010 = Rule(
    id="STX-P010",
    severity="warning",
    category="plot",
    message=(
        "top-level `figrecipe` used inside @stx.session — use the "
        "session-injected `plt` (e.g. `plt.subplots()`) instead"
    ),
    suggestion=_P010_SUGGESTION,
    requires="scitex",
)
