---
description: |
  [TOPIC] Interface Cli Pass Through
  [DETAILS] SciTeX CLI pass-through entry points — tool wrappers (`<cli> git ...`), script exec (`<cli> run script.py`), one-shot eval. Exempt from §1 noun-verb rule.
tags: [scitex-general-interface-cli-pass-through]
---

# §1c. Pass-through exceptions

Entry points that forward arguments verbatim — bypass parsing entirely after their own name.

| Pattern           | Example                                       | Why                                      |
|-------------------|-----------------------------------------------|------------------------------------------|
| Tool pass-through | `<cli> git <anything>`, `<cli> uv <anything>` | Args handed to upstream binary unchanged |
| Script exec       | `<cli> run <script.py> -- <args>`             | `--` preserves downstream flag semantics |
| One-shot eval     | `<cli> eval "<code>"`                         | Body is opaque to the parser             |

## Rules

- **Must** be declared in `--help` (the description should say "passes args to `<tool>`" or equivalent).
- **Must not** rewrite or reorder forwarded arguments.
- Pass-through entry points are exempt from the §1 noun-verb rule.

## How to declare a pass-through (so the auditor skips it)

The auditor ([07_audit-cli.md](07_audit-cli.md)) recognises pass-throughs by either of these markers — choose one per entry point:

1. **Click `context_settings`** with `ignore_unknown_options=True` AND `allow_extra_args=True`:

   ```python
   @cli.command(
       context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
       help="Pass-through to upstream `git`. Args are forwarded verbatim.",
   )
   @click.argument("args", nargs=-1, type=click.UNPROCESSED)
   def git(args):
       subprocess.run(["git", *args], check=False)
   ```

2. **Module-level marker** in the package's CLI module:

   ```python
   # src/<pkg>/cli/__init__.py
   PASS_THROUGH_COMMANDS: list[str] = ["git", "uv", "run", "eval"]
   ```

The auditor reads `PASS_THROUGH_COMMANDS` (if present) and inspects each Click command's `context_settings`; any match in either is exempted from §1 / §1d reports. Without one of these markers the auditor will flag the entry as a bare-noun or bare-verb violation.
