---
description: |
  [TOPIC] Interface Cli Required Introspection
  [DETAILS] SciTeX CLI required introspection commands — `list-python-apis` and `mcp list-tools` with `-v|-vv|-vvv` verbosity levels. Mandatory on every package CLI for parity with sibling packages.
tags: [scitex-general-interface-cli-required-introspection-commands]
---

# §1a. Required introspection commands

Every `scitex-*` package CLI **must** expose two introspection commands so that humans and agents can discover the package's surface without reading source.

## Commands

| Command              | Lists                                       | Section anchor                                                         |
|----------------------|---------------------------------------------|------------------------------------------------------------------------|
| `list-python-apis`   | Public Python API (`__all__`)               | this file + [03_interface/01_python-api/SKILL.md](SKILL.md) |
| `mcp list-tools`     | MCP tools registered by the package         | this file + [03_interface/03_mcp/SKILL.md](SKILL.md)        |
| `skills {list, get, install}` | Bundled agent-facing skills (markdown leaves under `_skills/<pkg>/`) | this file + [03_interface/04_skills/SKILL.md](SKILL.md) |
| `install-shell-completion` / `print-shell-completion` | Wires up bash/zsh/fish tab-completion. **Required** — without it, every scitex-* CLI ships without working `<TAB>` completion (the 2026-05-06 scitex-hpc symptom). `install-shell-completion --shell bash` must source the click-generated completion into the user's shell rc; `print-shell-completion --shell bash` prints it for piping. | §1b [04_exceptions.md](04_exceptions.md) |

Both follow the §1 noun-verb grammar:

- `list-python-apis` — verb-noun compound leaf at top level (object: `python-apis`).
- `mcp list-tools` — `mcp` noun group, `list-tools` compound-leaf verb. (`tool` is a noun in the §1d catalog; `list-tools` bakes in the object.)

## Verbosity convention — `-v` / `-vv` / `-vvv`

Both commands accept the same `-v` ladder. Each level **adds** information; it does not replace prior levels. `--verbose` is the long-form alias (consistent with §2 universal flags).

| Level     | `list-python-apis`                | `mcp list-tools`                                            |
|-----------|-----------------------------------|-------------------------------------------------------------|
| (default) | names only                        | tool names only                                             |
| `-v`      | + signatures                      | + signature (arg names + types)                             |
| `-vv`     | + docstrings (one-line summary)   | + docstring (one-line summary)                              |
| `-vvv`    | + full docstring + source path    | + full docstring + source module path + JSON-schema arg spec |

### Examples

```bash
$ scitex-io list-python-apis
save
load
load_configs
register_saver
…

$ scitex-io list-python-apis -v
save(obj, path: str | Path, **kwargs) -> Path
load(path: str | Path, **kwargs) -> Any
…

$ scitex-io list-python-apis -vv
save(obj, path: str | Path, **kwargs) -> Path
    Save any object to disk; format inferred from extension.
…

$ scitex-io mcp list-tools
io_save
io_load
io_list_formats
io_skills_list
io_skills_get

$ scitex-io mcp list-tools -v
io_save(obj: Any, path: str) -> dict
io_load(path: str) -> dict
…

$ scitex-io mcp list-tools -vv
io_save(obj: Any, path: str) -> dict
    Save any object via scitex-io.save(); returns {path, format, bytes}.
…
```

## Required flags on these commands

In addition to the verbosity ladder, both must accept (per §2 [08_universal-flags.md](08_universal-flags.md)):

- `--json` — machine-readable output. Replaces the human format with a JSON array of objects whose fields scale with the same `-v` ladder.
- `-h`, `--help` — usage with at least one example.

## Why these are mandatory

- **Discoverability without source dives** — agents and humans can list the surface in one command per concern (Python or MCP).
- **Parity check** — `list-python-apis -v` and `mcp list-tools -v` together let the auditor (§1e [07_audit-cli.md](07_audit-cli.md)) confirm CLI ↔ MCP ↔ Python parity (§7 [13_mcp-parity.md](13_mcp-parity.md)).
- **Stable contract** — verbosity ladder is the same across all `scitex-*` packages so users don't relearn flags.

## Audit hooks

The §1e auditor should verify:

- [ ] `<cli> list-python-apis` exists and exits 0.
- [ ] `<cli> list-python-apis -v|-vv|-vvv` produce monotonically more output (each level ⊇ previous).
- [ ] `<cli> mcp list-tools` exists and exits 0.
- [ ] `<cli> mcp list-tools -v|-vv|-vvv` follow the same monotonic ladder.
- [ ] Both commands honor `--json`.
- [ ] If the package ships `_skills/<pkg>/`, `<cli> skills` exists as a
      group with `list`, `get`, and `install` subcommands. Self-contained
      (no scitex-dev runtime dep) so users can introspect bundled skills
      without discovering the ecosystem-wide tooling first. `list` and
      `get` accept `--json`; `install` defaults to symlinking
      `_skills/<pkg>/` → `~/.scitex/dev/skills/<pkg>/` and accepts
      `--claude-symlink` to also expose at `~/.claude/skills/scitex/`.
- [ ] `<cli> install-shell-completion` and `<cli> print-shell-completion` exist; both accept `--shell {bash,zsh,fish}`. `install-shell-completion` writes the click-generated completion to the appropriate shell rc (or `~/.config/<shell>/completions/<cli>`) and prints a one-line "open a new shell" message. `print-shell-completion` prints the snippet without modifying the filesystem (useful for `eval "$(<cli> print-shell-completion --shell bash)"`).

## How `install-shell-completion` writes the rc line

**Required pattern: cache file + `source` line (NOT eval-the-binary).**

The naive form
```bash
eval "$(_FOO_COMPLETE=bash_source foo)"        # ❌ slow
```
re-invokes the python CLI on every shell start (~0.4 s per binary).
A user with N scitex-* CLIs pays N × 0.4 s of `source ~/.bashrc` latency
forever. The eval-form is a footgun.

**Correct form**: pre-generate the static completion script once and
source it from the canonical user-state location:

```
~/.scitex/<pkg-short>/runtime/completion/<binary>          ← primary, sac-owned
~/.local/share/bash-completion/<pkg>/<binary> -> primary    ← XDG symlink for auto-discovery
```

`~/.bashrc` (or `~/.zshrc`) gets:
```bash
[ -f ~/.scitex/<pkg-short>/runtime/completion/<binary> ] && \
    source ~/.scitex/<pkg-short>/runtime/completion/<binary>  # <pkg>-completion: <binary>
```

Sourcing a 30-line static script is microseconds. Per-binary marker
(`# <pkg>-completion: <binary>`) makes the line idempotent — a second
`install-shell-completion` invocation is a no-op.

### Why backgrounding the eval doesn't help

```bash
eval "$(_FOO_COMPLETE=bash_source foo)" &      # ❌ broken, not just slow
```

The `&` backgrounds the entire `eval`, which means the
`complete -F _foo_completion foo` line and the function definition
inside the eval execute **in a forked subshell**. They never affect
the parent shell's environment, so completion is silently broken in
the user's interactive session.

### When the package ships TWO console-scripts

Click keys the completion environment variable on `argv[0]`, so a
package shipping both `<long-name>` and `<short-alias>` (e.g.,
`scitex-agent-container` + `sac`) needs **two** cache files and two
source lines — one per binary name. A single `install-shell-completion`
invocation should write all of them.

### Audit — `PS-147 local-state-eval-completion`

- [ ] `<pkg>` source must not contain `eval "$(_<PKG>_COMPLETE=bash_source ...)"` lines that get appended to rc files via `install-shell-completion`. Use the cache pattern above.

The auditor lives at
`scitex_dev._cli.audit._project._check_local_state.check_ps147_eval_form_completion`.
It greps every `*.py` under `src/` for the eval-form pattern, skipping
docstrings and `#` comments. Findings surface under
`scitex-dev ecosystem audit-project <pkg>` (rule code `PS-147`,
severity `W` during bake-in).

The upstream helper `scitex_dev._cli._completion.attach_shell_completion`
already implements the cache pattern — every CLI that uses
`attach_shell_completion(group, prog_name=...)` inherits it for free.
Packages still tripping `PS-147` are the ones that ship their own
`install-shell-completion` body; the fix is to delete the local
implementation and call `attach_shell_completion` instead.

`scitex-dev ecosystem install --with-completions` (default on) wires
all 66 packages' completions in one shot after a fresh pip install.
