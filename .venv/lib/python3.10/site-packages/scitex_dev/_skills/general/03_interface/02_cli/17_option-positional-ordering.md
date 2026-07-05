---
description: |
  [TOPIC] Interface Cli Option Positional Ordering
  [DETAILS] Allow options before AND after the positional argument — `cli <pos> --flag val` and `cli --flag val <pos>` must both parse. Click's `invoke_without_command=True` group breaks this by default; pre-Click argv reorder fixes it.
tags: [scitex-general-interface-cli-option-positional-ordering]
---

# §10. Option / positional ordering — both forms must work

## Rule

A SciTeX CLI that accepts a positional argument **must accept options on either side** of that positional. Both forms parse identically:

```bash
cli <POSITIONAL> --flag value     # natural ("act on this thing, this way")
cli --flag value <POSITIONAL>     # un-natural but allowed
```

Users reach for the natural form first. A CLI that only accepts the un-natural form (typical with `click.group(invoke_without_command=True)` + a positional) is **broken**.

## Why this is non-default in Click

Click's `@click.group(invoke_without_command=True)` with a positional `argument` treats anything **after** the positional as a subcommand name. So:

```bash
mycli /some/path --format json
# → SOURCE=/some/path, subcommand="--format"  → "Error: No such command '--format'"
```

This is hostile to muscle memory built on `pytest path/to/test.py -v`, `cargo build --release`, etc.

## Required fix — pre-Click argv reorder

Add a small reorder hook between the console-script entry point and Click. Wire it into both:

1. The `[project.scripts]` entry (`mycli = "mypkg._cli:cli_entrypoint"`)
2. `__main__.py` (for `python -m mypkg` parity)

```python
_SUBCOMMANDS = {"templates", "skills", "mcp", ...}  # registered subcommand names
_VALUE_TAKING = {"--model", "--runs", "--template", "--format", "--runtime"}

def _reorder_argv(argv: list[str]) -> list[str]:
    """Move the SOURCE positional to the end so Click's group sees all
    options before any positional. Subcommand invocations and `--`-
    separated argv pass through untouched."""
    if not argv or "--" in argv:
        return argv
    options, positional, rest = [], None, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if positional is not None:
            rest.append(a); i += 1; continue
        if a.startswith("-"):
            options.append(a)
            if a in _VALUE_TAKING and i + 1 < len(argv) and not argv[i+1].startswith("-"):
                options.append(argv[i+1]); i += 2; continue
            i += 1; continue
        if a in _SUBCOMMANDS:
            return argv  # real subcommand — Click routes
        positional = a
        i += 1
    return options + rest + ([positional] if positional else [])

def cli_entrypoint():
    sys.argv[1:] = _reorder_argv(sys.argv[1:])
    return main()  # the Click group
```

Tests: cover all forms — `<pos> --flag value`, `--flag value <pos>`, value-taking flag, subcommand passthrough, `--` separator, empty argv, just-positional.

## Exemption

CLIs with no positional on the top-level group (pure subcommand routers) don't need the hook. The rule only fires when `--help` shows `[OPTIONS] [POSITIONAL] COMMAND [ARGS]`.

## Auditor

The CLI auditor (`07_audit-cli.md`) enforces this via a synthetic invocation: if the CLI declares any top-level positional, the auditor calls it both ways and asserts the same result. CLIs that fail one form **fail the audit** (rule **PS-134** — *option-positional-order*).

## Background

Adopted from the newb CLI (2026-05) after users repeatedly hit `Error: No such command '--format'` on `newb /path --format markdown`. The natural form is the one users write; the CLI must meet it.
