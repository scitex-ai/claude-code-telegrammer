"""Category NET: outbound-network-call timeout hygiene.

Codifies the sac ``listen`` daemon incident (2026-07-01): a daemon bound to
127.0.0.1:7878 died, and every client calling it had NO explicit ``timeout``.
Each call degraded to a ~30s connect-hang (the OS default) instead of failing
fast, which the operator read as "everything is slow" fleet-wide.

STX-NET001 flags any outbound network call in non-test source that omits an
explicit ``timeout`` (positional OR keyword). The bounded shape that PASSES is
scitex-todo's fixed wake POST — a call with ``timeout=`` set (and fail-soft).

Severity is WARNING by design, and the rule participates in the linter's
NEW-ONLY gate (``check-files --new-only``): it fires on newly-changed code but
legacy unbounded calls stay visible-yet-non-blocking. A CI-failing (ERROR) rule
that over-triggers would wedge every fleet repo. PROMOTABLE to ERROR after a
clean ecosystem sweep confirms no legitimate unbounded-call backlog remains.
"""

from ._base import Rule

NET001 = Rule(
    id="STX-NET001",
    severity="warning",
    category="network",
    message=(
        "Outbound network call without an explicit `timeout` — a dead/slow peer "
        "makes it hang on the OS default (~seconds) instead of failing fast "
        "(sac listen-daemon incident 2026-07-01: 'everything is slow' fleet-wide)."
    ),
    suggestion=(
        "Pass an explicit, small `timeout=` (scitex-todo's wake POST uses 1.5s + "
        "fail-soft). urllib.request.urlopen takes timeout as the 3rd positional or "
        "`timeout=`; requests/httpx take `timeout=`; socket.create_connection takes "
        "it 2nd-positional or `timeout=`. If a genuinely-unbounded call is required, "
        "add `# stx-allow: STX-NET001`."
    ),
)
