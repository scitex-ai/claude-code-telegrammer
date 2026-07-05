---
description: |
  [TOPIC] Interface Cli Flags
  [DETAILS] SciTeX CLI universal & convention flags — required (-h, --help-recursive, --json, --dry-run, -V, -y) and convention (-v, -q, -j/--jobs). No interactive prompts.
tags: [scitex-general-interface-cli-universal-flags]
---

# §2. Universal & convention flags

## Universal flags (required by context)

| Flag               | Purpose                                       | Required on                |
|--------------------|-----------------------------------------------|----------------------------|
| `-h`, `--help`     | Usage with at least one example               | Every command              |
| `--help-recursive` | Flatten help for all subcommands              | Top-level                  |
| `--json`           | Machine-readable JSON on stdout, no log noise | Every data-reading command |
| `--dry-run`        | Preview changes without side effects          | Every mutating command     |
| `--version`, `-V`  | Print `pkg/X.Y.Z`                             | Top-level                  |
| `--yes`, `-y`      | Bypass interactive confirm                    | Mutating commands          |

## Convention flags (optional but standardized when present)

When a command exposes one of these capabilities, it MUST use this exact spelling — not a synonym (`--n-cpus`, `--parallel`, `--silent`, etc.).

| Flag               | Purpose                                                       | When to add                                  |
|--------------------|---------------------------------------------------------------|----------------------------------------------|
| `--verbose`, `-v`  | Extra stderr logs (count style: `-v|-vv|-vvv`)                | Any command with multiple detail levels      |
| `--quiet`, `-q`    | Suppress non-error stderr                                     | Any command with default chatter             |
| `--jobs N`, `-j N` | Parallelism. `1` = serial (default). `0` or `auto` = all CPUs. Matches `make`, `cargo`, `ninja`. | Any command that fans out across packages, files, or items |

## Verbosity ladder

`--verbose` / `-v` is **count-style** — repeating it raises the level. Each level is **additive** (extends the previous level, never replaces). Required on the introspection commands ([03_required-introspection-commands.md](03_required-introspection-commands.md)); optional but recommended elsewhere.

| Level   | Meaning                                                                |
|---------|------------------------------------------------------------------------|
| (none)  | Default: minimal output (names, summary).                              |
| `-v`    | Adds signatures / one-line context.                                    |
| `-vv`   | Adds docstrings / multi-line detail.                                   |
| `-vvv`  | Adds source paths / JSON-schema / debug-level context.                 |

`--verbose` and `--quiet` are mutually exclusive — passing both → exit 2.

## No interactive prompts

- Commands must run unattended (CI, agent, cron).
- Missing input → fail fast with exit 2 + clear stderr.
- Never `input()`, `read`, or block on sudo.
- Mutating commands MAY show a confirmation prompt **only when stdin is a TTY**; otherwise auto-fail (use `--yes` to bypass even on a TTY).

## `--json` scope

- Required on every **data-reading** command (introspection, list, show, get, search, …).
- Recommended on every command that emits structured output the user might pipe.
- On non-data commands (lifecycle: `start`, `stop`, …) `--json` may emit `{"status": "ok"}` or be a no-op — the rule is: if the command exits, exit code carries the success signal; `--json` adds machine-readable detail when meaningful.

## `--json` content parity (data superset rule)

`--json` is an **output-formatting** flag, not a fetch flag. The data the command produces must be the **same** in text and JSON modes; only the rendering differs. Concretely:

- Every column / field shown in text mode MUST appear in JSON mode.
- JSON MAY include strictly more fields than text (extra metadata, paths, ids).
- JSON MUST NOT drop fields, collapse a list-of-objects to a list-of-strings, or substitute a different fetch path that returns less data.

**Counter-examples (real bugs fixed in scitex-dev 0.8.2):**

| Command | Bug | Fix |
| --- | --- | --- |
| `ecosystem list --json` | text emitted `name + github_repo`; JSON emitted only `["scitex", ...]` | JSON now `[{"name": ..., "github_repo": ...}, ...]` |
| `docs list --json` | `--json` flag flipped the *fetcher* to `format="json"` (minimal page list) instead of the rich manifest the text path uses | Always fetch the rich manifest when listing; `--json` only changes the renderer |
| `--help-recursive --json` | top-level `--json` ignored; printed plain text help | Walk the click tree to a JSON tree of `{name, help, options, arguments, commands{}}` |

**The pattern to avoid:** branching on `as_json` *inside the data-fetch step* and asking the data layer for a smaller payload. Fetch the rich shape unconditionally; let the renderer decide what to print.

```python
# WRONG — JSON path returns less data
fmt = "json" if as_json else None
result = fetch(format=fmt)            # ← changes WHAT we get
if as_json:
    print(json.dumps(result))
else:
    render_table(result)

# RIGHT — JSON path renders the same data, just differently
result = fetch()                      # ← always the rich shape
if as_json:
    print(json.dumps(result))
else:
    render_table(result)
```

**Audit recipe:**

```bash
# For every <cmd> that supports --json:
diff <(<cmd> | awk '{print $1}' | sort) \
     <(<cmd> --json | jq -r '.[].name // .[]' | sort)
# Anything in the text-only column is a parity gap.
```
