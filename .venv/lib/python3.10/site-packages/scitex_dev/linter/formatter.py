"""Output formatting for terminal and JSON."""

__all__ = ["format_issue", "format_summary", "to_json"]

from .checker import Issue

# ANSI colors
_RED = "\033[91m"
_YELLOW = "\033[93m"
_BLUE = "\033[94m"
_GREEN = "\033[92m"
_GRAY = "\033[90m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

_SEV_COLOR = {"error": _RED, "warning": _YELLOW, "info": _BLUE}
_SEV_ICON = {"error": "E", "warning": "W", "info": "I"}


def format_issue(issue: Issue, filepath: str, color: bool = True) -> str:
    if not color:
        return _format_plain(issue, filepath)

    sev = issue.rule.severity
    c = _SEV_COLOR.get(sev, "")
    icon = _SEV_ICON.get(sev, "?")
    lines = [
        f"  {c}{icon}{_RESET} {_BOLD}{filepath}:{issue.line}:{issue.col}{_RESET}"
        f"  {c}{issue.rule.id}{_RESET}",
    ]
    if issue.source_line:
        lines.append(f"    {_GRAY}{issue.source_line}{_RESET}")
    lines.append(f"    {c}{issue.rule.message}{_RESET}")
    lines.append(f"    {_GREEN}{issue.rule.suggestion}{_RESET}")
    return "\n".join(lines)


def _format_plain(issue: Issue, filepath: str) -> str:
    icon = _SEV_ICON.get(issue.rule.severity, "?")
    lines = [
        f"  {icon} {filepath}:{issue.line}:{issue.col}  {issue.rule.id}",
    ]
    if issue.source_line:
        lines.append(f"    {issue.source_line}")
    lines.append(f"    {issue.rule.message}")
    lines.append(f"    {issue.rule.suggestion}")
    return "\n".join(lines)


def format_summary(issues: list, filepath: str, color: bool = True) -> str:
    if not issues:
        if color:
            return f"{_GREEN}OK{_RESET} {filepath}"
        return f"OK {filepath}"

    errors = sum(1 for i in issues if i.rule.severity == "error")
    warnings = sum(1 for i in issues if i.rule.severity == "warning")
    infos = sum(1 for i in issues if i.rule.severity == "info")

    parts = []
    if errors:
        label = f"{errors} error{'s' if errors != 1 else ''}"
        parts.append(f"{_RED}{label}{_RESET}" if color else label)
    if warnings:
        label = f"{warnings} warning{'s' if warnings != 1 else ''}"
        parts.append(f"{_YELLOW}{label}{_RESET}" if color else label)
    if infos:
        label = f"{infos} info"
        parts.append(f"{_BLUE}{label}{_RESET}" if color else label)

    fp = f"{_BOLD}{filepath}{_RESET}" if color else filepath
    return f"  {', '.join(parts)} in {fp}"


def to_json(issues: list, filepath: str) -> dict:
    return {
        "file": filepath,
        "issues": [
            {
                "rule_id": i.rule.id,
                "severity": i.rule.severity,
                "category": i.rule.category,
                "line": i.line,
                "col": i.col,
                "message": i.rule.message,
                "suggestion": i.rule.suggestion,
                "source_line": i.source_line,
            }
            for i in issues
        ],
        "summary": {
            "errors": sum(1 for i in issues if i.rule.severity == "error"),
            "warnings": sum(1 for i in issues if i.rule.severity == "warning"),
            "infos": sum(1 for i in issues if i.rule.severity == "info"),
        },
    }
