---
description: |
  [TOPIC] Interface Cli Umbrella Passthrough
  [DETAILS] Umbrella `scitex` re-exports each standalone CLI as a single click.Group — never duplicates help, never forwards via subprocess. Branded packages (e.g. socialia → `scitex social`) rewrite the program name on mount.
tags: [scitex-general-interface-cli-umbrella-passthrough]
---

# §5b. Umbrella subcommand passthrough — single source of truth

> One sentence: **the umbrella owns the namespace; the package owns its surface; the umbrella never re-types what the package already declares.**

This is distinct from §1c (tool pass-through to upstream binaries). §1c forwards to non-scitex tools (`git`, `uv`); §5b connects the umbrella `scitex` to a standalone `scitex-<pkg>` (or branded sibling like `socialia`) that already ships its own click tree.

## The rule

When a `scitex-<pkg>` package ships a CLI, the umbrella `scitex` MUST expose it as a single re-exported `click.Group`. The umbrella adds exactly two things: the subcommand **name** and the install-fallback message. Every other byte of help text, examples, sub-tree, deprecation alias, and shell completion lives in the standalone CLI module.

### Canonical shim

```python
# scitex-python: src/scitex/cli/<short>.py
import click

try:
    from scitex_<pkg>._cli import main as _main  # branded: e.g. `from socialia._cli import main as _main`
except ImportError:
    _main = None

if _main is not None:
    <short> = _main
    <short>.name = "<short>"   # ← rewrites prog-name fragment shown under `scitex`
else:
    @click.command("<short>")
    def <short>():
        """scitex-<pkg> not installed."""
        click.secho("Install with: pip install scitex-<pkg>", fg="red")
        raise SystemExit(1)
```

Click composes the `Usage:` line from the parent command path, so `scitex <short> --help` automatically renders `Usage: scitex <short> [OPTIONS] ...` even though the standalone renders `Usage: scitex-<pkg> [OPTIONS] ...`. **No duplication, no drift.**

### Forbidden anti-pattern

```python
# DO NOT do this
_DATASET_COMMANDS = {"openneuro": "Fetch from OpenNeuro", ...}

@click.command("dataset")
@click.argument("args", nargs=-1)
def dataset(args):
    """Hand-typed help that drifts the moment scitex-dataset reshapes."""
    subprocess.call(["scitex-dataset", *args])
```

This loses click context, env-var inheritance, exit-code semantics, tab-completion, `--help-recursive`, and — most importantly — drifts the moment the standalone CLI grows or reshapes. The 2026-05-06 dataset escalation (`GITIGNORED/ESCALATION.md`) was filed because exactly this shape masked the standalone's migration from flat (`openneuro / dandi`) to 3-level (`<domain> <dataset> <action>`) for an entire release cycle.

## Branded packages (program-name rewriting)

Some downstream packages do not carry the `scitex-` prefix (`socialia`, `figrecipe`, `newb`). When mounted under the umbrella, the program-name fragment must also be rewritten:

| Standalone invocation        | Umbrella invocation         | How                                                    |
|------------------------------|-----------------------------|--------------------------------------------------------|
| `scitex-dataset --help`      | `scitex dataset --help`     | `dataset = _ds_main; dataset.name = "dataset"`         |
| `socialia --help`            | `scitex social --help`      | `social = _socialia_main; social.name = "social"`      |
| `figrecipe --help`           | `scitex plt --help`         | `plt = _figrecipe_main; plt.name = "plt"` (mount-only) |

**Both** invocations must keep working — the standalone keeps its own brand, the umbrella shows its namespace. Click handles this naturally via the parent command path.

### Help text inside the standalone

Standalone help/examples/epilogs MUST avoid hardcoded `scitex-<pkg>` / brand strings where the same line will be rendered under the umbrella. Two acceptable patterns:

1. **Reference the running prog name from context:**
   ```python
   @click.command()
   @click.pass_context
   def fetch(ctx):
       """Fetch a dataset.

       \b
       Examples:
         $ {prog} fetch openneuro ds000001
       """
       fetch.help = fetch.help.format(prog=ctx.find_root().info_name)
   ```

2. **Use a brand-neutral placeholder** (`<cli>` is the existing convention in this skill set — see [10_help-format.md](10_help-format.md)) and document it in the package's own README. The auditor accepts `<cli>` as a non-violation.

The brand-rewrite registry — which package ships under which umbrella subcommand name — lives in the ecosystem registry (`scitex_dev._ecosystem._core.ECOSYSTEM`) under the optional `umbrella_subcommand` field. If absent, the auditor assumes `<short>` = the package name with `scitex-` stripped.

## Adoption checklist

For each `scitex-<pkg>` (or branded sibling) the maintainer must:

- [ ] Replace `scitex-python: src/scitex/cli/<short>.py` with the re-export shim above.
- [ ] Confirm `scitex <short> --help` is byte-identical to the standalone `--help` (modulo the program-name fragment in `Usage:`).
- [ ] Confirm the standalone's help text contains no hardcoded `scitex-<pkg>` / brand strings — use `{prog}` or `<cli>` instead.
- [ ] If branded (no `scitex-` prefix), add `umbrella_subcommand: "<short>"` to the package's `ECOSYSTEM` entry.
- [ ] Run `scitex-dev ecosystem audit-cli scitex-<pkg>` and confirm the umbrella-drift section is clean.

## See also

- [05_pass-through.md](05_pass-through.md) — verbatim forwarding to **upstream** binaries (`git`, `uv`). Different concept.
- MCP equivalent: [03_interface/03_mcp/02_server-registration.md](../03_mcp/02_server-registration.md) — `safe_mount(..., namespace="<short>")`.
- Source escalation: `GITIGNORED/ESCALATION.md` (2026-05-06, scitex-dataset audit).
