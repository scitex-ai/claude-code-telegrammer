"""CLI handler for the 'list-python-apis' subcommand."""

import json
import sys

# (module, kind, name, signature, docstring)
# kind: F=Function, C=Class, V=Variable
_PUBLIC_API = [
    (
        "scitex_linter.checker",
        "F",
        "lint_file",
        "(filepath, config=None) -> list[Issue]",
        "Lint a Python file and return list of issues.",
    ),
    (
        "scitex_linter.checker",
        "F",
        "lint_source",
        "(source, filepath, config=None) -> list[Issue]",
        "Lint a Python source string and return list of issues.",
    ),
    (
        "scitex_linter.checker",
        "F",
        "is_script",
        "(filepath, config=None) -> bool",
        "Check if a file is a runnable script (has __main__ guard or @stx.session).",
    ),
    (
        "scitex_linter.checker",
        "C",
        "Issue",
        "(rule, line, col, source_line)",
        "A lint issue found in source code.",
    ),
    (
        "scitex_linter.fixer",
        "F",
        "fix_source",
        "(source, filepath, config=None) -> str",
        "Auto-fix lint issues in source string.",
    ),
    (
        "scitex_linter.fixer",
        "F",
        "fix_file",
        "(filepath, write=True, config=None) -> tuple",
        "Auto-fix lint issues in file.",
    ),
    (
        "scitex_linter.formatter",
        "F",
        "format_issue",
        "(issue, filepath, color=False) -> str",
        "Format a single issue for terminal display.",
    ),
    (
        "scitex_linter.formatter",
        "F",
        "format_summary",
        "(issues, filepath, color=False) -> str",
        "Format a summary line for terminal display.",
    ),
    (
        "scitex_linter.formatter",
        "F",
        "to_json",
        "(issues, filepath) -> list[dict]",
        "Convert issues to JSON-serializable dicts.",
    ),
    (
        "scitex_linter.rules",
        "V",
        "ALL_RULES",
        "dict[str, Rule]",
        "All built-in lint rules keyed by ID.",
    ),
    (
        "scitex_linter.rules",
        "V",
        "SEVERITY_ORDER",
        "dict[str, int]",
        "Severity name to numeric priority mapping.",
    ),
    (
        "scitex_linter.config",
        "C",
        "LinterConfig",
        "dataclass (load via load_config())",
        "Linter configuration loaded from pyproject.toml or defaults.",
    ),
    (
        "scitex_linter",
        "F",
        "list_rules",
        "(category=None) -> list[Rule]",
        "List all rules (built-in + plugins).",
    ),
]


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "list-python-apis",
        help="List public Python API",
        description="List all public Python API functions and classes.",
        aliases=["api"],
    )
    p.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON")
    p.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Verbosity: -v signatures, -vv +docstrings, -vvv full",
    )
    p.set_defaults(func=_cmd_api)


def _cmd_api(args) -> int:
    v = args.verbose

    if args.as_json:
        data = [
            {"module": m, "kind": k, "name": n, "signature": s, "doc": d}
            for m, k, n, s, d in _PUBLIC_API
        ]
        print(json.dumps(data, indent=2))
        return 0

    use_color = sys.stdout.isatty()
    cyan = "\033[96m" if use_color else ""
    green = "\033[92m" if use_color else ""
    yellow = "\033[93m" if use_color else ""
    blue = "\033[94m" if use_color else ""
    dim = "\033[2m" if use_color else ""
    reset = "\033[0m" if use_color else ""

    kind_color = {"F": green, "C": yellow, "V": blue}

    print(f"API tree of scitex_linter ({len(_PUBLIC_API)} items):")
    print("Legend: [M]=Module [C]=Class [F]=Function [V]=Variable")

    current_mod = None
    for mod, kind, name, sig, doc in _PUBLIC_API:
        if mod != current_mod:
            print(f"{cyan}[M] {mod}{reset}")
            current_mod = mod
        kc = kind_color.get(kind, "")
        if v == 0:
            print(f"  {kc}[{kind}]{reset} {name}")
        elif v >= 1:
            sep = "" if sig.startswith("(") else " "
            print(f"  {kc}[{kind}]{reset} {name}{sep}{sig}")
            if v >= 2 and doc:
                print(f"       {dim}{doc}{reset}")

    return 0
