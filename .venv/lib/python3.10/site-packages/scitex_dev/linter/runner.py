"""Run a Python script after linting it.

Core function used by the `scitex-dev linter run-python` subcommand.
"""

import os
import subprocess
import sys

from .checker import lint_file
from .formatter import format_issue, format_summary
from .rules import SEVERITY_ORDER


def _is_git_root() -> bool:
    """Check if the current working directory is a git repository root."""
    return os.path.isdir(os.path.join(os.getcwd(), ".git"))


def run_script(filepath: str, strict: bool = False, script_args: list = None) -> int:
    """Lint a script then execute it.

    Returns the subprocess return code, or 2 if strict mode blocks execution.
    """
    if script_args is None:
        script_args = []

    # Check if running from git root
    use_color = sys.stderr.isatty()
    if not _is_git_root():
        hint = "\033[94mInfo\033[0m" if use_color else "Info"
        print(
            f"{hint}: not running from a git root directory (cwd: {os.getcwd()})",
            file=sys.stderr,
        )

    # Lint
    issues = lint_file(filepath)

    has_errors = any(i.rule.severity == "error" for i in issues)
    has_warnings = any(
        SEVERITY_ORDER[i.rule.severity] >= SEVERITY_ORDER["warning"] for i in issues
    )

    if issues:
        header = "\033[1mSciTeX Lint\033[0m" if use_color else "SciTeX Lint"
        print(f"\n{header}\n", file=sys.stderr)

        for issue in issues:
            print(format_issue(issue, filepath, color=use_color), file=sys.stderr)
        print(format_summary(issues, filepath, color=use_color), file=sys.stderr)
        print(file=sys.stderr)

    if strict and has_errors:
        msg = "\033[91mAborted\033[0m" if use_color else "Aborted"
        print(f"{msg}: errors found (--strict mode)\n", file=sys.stderr)
        return 2

    if not has_errors and not has_warnings:
        ok = "\033[92mOK\033[0m" if use_color else "OK"
        print(f"{ok} {filepath}", file=sys.stderr)

    # Execute
    sep = "\u2500" * 60
    if use_color:
        print(f"\n\033[90m{sep}\033[0m", file=sys.stderr)
    else:
        print(f"\n{sep}", file=sys.stderr)

    cmd = [sys.executable, filepath] + script_args
    result = subprocess.run(cmd)
    return result.returncode
