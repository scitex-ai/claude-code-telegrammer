---
description: |
  [TOPIC] Interface Cli Help Format
  [DETAILS] SciTeX CLI required `--help` output structure — description, synopsis, example, flags, exit codes.
tags: [scitex-general-interface-cli-help-format]
---

# §4. Help output format

`--help` always includes:

1. One-line description **with the package version inline.** The
   canonical opening line is `<cli> (vX.Y.Z) — <description>`. The
   literal must come from `importlib.metadata.version("<dist>")` so
   pyproject.toml stays the single source of truth — never hardcode a
   string. Operators reading `<cli> --help` see which version they're
   on without a separate `--version` call. Auditor rule `§4`
   (`audit-cli`); the regex accepts pre-release suffixes
   (`rc1`/`dev0`/`post1`).
2. Usage synopsis: `Usage: <cli> <noun> <verb> [OPTIONS] ARG`.
3. **At least one concrete example.**
4. Flag list with descriptions.
5. Exit-code summary (if non-trivial).
6. **Categorized command list** when the top-level group exposes ≥6
   commands. Group commands under named sections (e.g. `Ecosystem:`,
   `Development:`, `Documentation:`, `Interface:`, `Shell:`, `Other:`)
   so a fresh agent can scan by intent instead of reading a flat 40-row
   list. Use `scitex_dev.click_helpers.CategorizedGroup` (Click `Group`
   subclass that overrides `format_commands`); pass a `COMMAND_CATEGORIES`
   list of `(section_name, [cmd_names])`. Anything not listed falls to
   `Other`. Auditor rule `C7`.

## Idiom — version-in-help via importlib.metadata

```python
from importlib.metadata import version as _v

@click.group(help=f"scitex-io (v{_v('scitex-io')}) — Universal scientific data I/O.")
def main():
    ...
```

Pass-through entry points (Click `ignore_unknown_options=True` +
`allow_extra_args=True`) are exempt — their help is forwarded
verbatim from the upstream tool.
