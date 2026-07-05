"""CLI handlers for 'rule' and 'rules' subcommands."""

import json
import sys

from .rules import ALL_RULES

# =========================================================================
# Subcommand: rule (built-in only, JSON-capable)
# =========================================================================


def register_rule(subparsers) -> None:
    p = subparsers.add_parser(
        "rule",
        help="List all lint rules",
        description="List all available SciTeX lint rules.",
    )
    p.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON")
    p.add_argument(
        "--category",
        help="Filter by category (comma-separated: structure,import,io,plot,stats)",
    )
    p.add_argument(
        "--severity",
        choices=["error", "warning", "info"],
        help="Filter by severity",
    )
    p.set_defaults(func=_cmd_rule)


def _cmd_rule(args) -> int:
    categories = set(args.category.split(",")) if args.category else None
    rules_list = list(ALL_RULES.values())

    if categories:
        rules_list = [r for r in rules_list if r.category in categories]
    if args.severity:
        rules_list = [r for r in rules_list if r.severity == args.severity]

    if args.as_json:
        data = [
            {
                "id": r.id,
                "severity": r.severity,
                "category": r.category,
                "message": r.message,
                "suggestion": r.suggestion,
            }
            for r in rules_list
        ]
        print(json.dumps(data, indent=2))
        return 0

    use_color = sys.stdout.isatty()
    sev_color = {"error": "\033[91m", "warning": "\033[93m", "info": "\033[94m"}
    reset = "\033[0m"

    for r in rules_list:
        if use_color:
            c = sev_color.get(r.severity, "")
            print(f"  {c}{r.id}{reset}  [{r.severity}]  {r.message}")
        else:
            print(f"  {r.id}  [{r.severity}]  {r.message}")

    print(f"\n  {len(rules_list)} rules")
    return 0


# =========================================================================
# Subcommand: rules (built-in + plugin)
# =========================================================================


def register_rules(subparsers) -> None:
    p = subparsers.add_parser(
        "rules",
        help="List all lint rules (built-in + plugin)",
        description="List all available SciTeX lint rules, including plugin-contributed rules.",
    )
    p.add_argument(
        "--category",
        help="Filter by category (e.g. io, plot, structure, import, stats)",
    )
    p.add_argument(
        "--severity",
        choices=["error", "warning", "info"],
        help="Filter by severity",
    )
    p.set_defaults(func=_cmd_rules)


def _cmd_rules(args) -> int:
    from . import list_rules

    category = args.category if args.category else None
    rules_list = list_rules(category=category)

    if args.severity:
        rules_list = [r for r in rules_list if r.severity == args.severity]

    use_color = sys.stdout.isatty()
    sev_color = {"error": "\033[91m", "warning": "\033[93m", "info": "\033[94m"}
    reset = "\033[0m"

    for r in rules_list:
        if use_color:
            c = sev_color.get(r.severity, "")
            print(f"  {c}{r.id}{reset}  [{r.severity}]  {r.category}: {r.message}")
        else:
            print(f"  {r.id}  [{r.severity}]  {r.category}: {r.message}")

    print(f"\n  {len(rules_list)} rules")
    return 0
