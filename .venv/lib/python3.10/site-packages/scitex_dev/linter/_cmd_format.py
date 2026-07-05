"""CLI handler for the 'format' subcommand."""

import difflib
import sys
from pathlib import Path

from .fixer import fix_source


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "format",
        help="Auto-fix SciTeX pattern issues",
        description="Auto-fix SciTeX pattern issues (e.g. insert missing INJECTED parameters).",
    )
    p.add_argument("path", help="Python file or directory to format")
    p.add_argument(
        "--check",
        action="store_true",
        help="Check if changes needed without writing (exit 1 if changes needed)",
    )
    p.add_argument("--diff", action="store_true", help="Show diff of changes")
    p.set_defaults(func=cmd_format)


def cmd_format(args) -> int:
    from .cli import _collect_files
    from .config import load_config

    config = load_config(args.path)
    target = Path(args.path)
    if not target.exists():
        print(f"Error: {args.path} not found", file=sys.stderr)
        return 2

    files = _collect_files(target, config=config)
    if not files:
        print(f"No Python files found in {args.path}", file=sys.stderr)
        return 0

    changed_count = 0
    for f in files:
        original = f.read_text(encoding="utf-8")
        fixed = fix_source(original, filepath=str(f), config=config)
        if fixed != original:
            changed_count += 1
            if args.diff:
                diff = difflib.unified_diff(
                    original.splitlines(keepends=True),
                    fixed.splitlines(keepends=True),
                    fromfile=str(f),
                    tofile=str(f),
                )
                sys.stdout.writelines(diff)
            if not args.check:
                f.write_text(fixed, encoding="utf-8")
                print(f"Fixed {f}")
            else:
                print(f"Would fix {f}")

    if changed_count == 0:
        print("All files clean")
        return 0

    if args.check:
        print(f"\n{changed_count} file(s) would be changed")
        return 1

    print(f"\n{changed_count} file(s) fixed")
    return 0
