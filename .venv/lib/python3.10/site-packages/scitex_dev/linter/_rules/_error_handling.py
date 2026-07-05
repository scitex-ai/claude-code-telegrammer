"""Category EH: Error-handling rules."""

from ._base import Rule

EH001 = Rule(
    id="STX-EH001",
    severity="warning",
    category="error-handling",
    message=(
        "Narrow `except ImportError` may miss runtime-init errors from optional deps."
    ),
    suggestion=(
        "Consider `except Exception as e: logger.debug(...)` so misconfigured ML "
        "runtimes (e.g. tensorflow with mismatched protobuf raising "
        "`google.protobuf.runtime_version.VersionError`) don't crash callers that "
        "don't even use the lib."
    ),
)
