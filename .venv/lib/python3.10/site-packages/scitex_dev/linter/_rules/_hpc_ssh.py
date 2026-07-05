"""Category HPC: HPC/SSH connection-hygiene rules.

Codifies the Spartan admin incident (2026-06-17): disabling ssh connection
multiplexing (turning the control-master / control-path off) on SSH to an HPC
login node opens a FRESH connection per call, which is exactly how the ecosystem
reached 440+ login-node connections. STX-HPC001 fails CI if that pattern is
reintroduced in committed source — the commit/CI-time complement to the runtime
pre-tool-use hook that blocks login-node ``du`` / ``find`` live. (Prose here
avoids the literal option tokens so the rule does not flag its own definition.)
"""

from ._base import Rule

HPC001 = Rule(
    id="STX-HPC001",
    severity="warning",
    category="hpc-ssh",
    message=(
        # Prose avoids the literal option tokens (ast folds adjacent string
        # literals, so naming them here would flag this rule's own definition).
        "SSH connection multiplexing is disabled on the HPC path (ssh control-"
        "master / control-path turned off) — opens a fresh login-node connection "
        "per call (Spartan admin incident 2026-06-17: 440+ connections)."
    ),
    suggestion=(
        "Multiplex instead: ControlMaster=auto + ControlPersist + a dedicated "
        "ControlPath, so calls reuse one master per host. See "
        "scitex_dev.ci.runner.config.SSH_MUX_OPTS for the canonical opts. If a "
        "fresh connection is genuinely required, add `# stx-allow: STX-HPC001`."
    ),
)
