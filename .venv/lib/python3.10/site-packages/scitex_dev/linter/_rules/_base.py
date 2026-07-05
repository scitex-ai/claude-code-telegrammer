"""Rule dataclass definition."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str  # "error", "warning", "info"
    category: str  # "structure", "import", "io", "plot", "stats"
    message: str
    suggestion: str
    requires: str = ""
