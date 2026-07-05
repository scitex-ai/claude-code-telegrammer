---
description: |
  [TOPIC] Interface Cli Exceptions
  [DETAILS] SciTeX CLI single-token exceptions — `doctor`, `repl`, `shell`. Banned bare leaves (`version`, `completion`). Reserved single-token flags.
tags: [scitex-general-interface-cli-exceptions]
---

# §1b. Exceptions (single-token commands)

- Single-token command, **no object needed** — name is already an intransitive verb.
- Transitive verbs (`list`, `start`, `delete`) can **never** be exceptions.

| Exception        | Why                                   |
|------------------|---------------------------------------|
| `doctor`         | Widely recognized health-check idiom  |
| `repl` / `shell` | Invoking it *is* entering the session |

## Banned single-token commands (do **not** add)

- `version` — use the `--version` / `-V` flag instead (see [08_universal-flags.md](08_universal-flags.md)). A bare `version` subcommand is forbidden.
- `completion` — use `install-shell-completion` / `print-shell-completion` (see "Not exceptions" below).

**Rule of thumb:** if any realistic sibling verb exists, it is **not** an exception — add the verb now.

## Not exceptions (common mistakes)

- `completion` — noun; the action (`install`, `print`) is transitive.
  - Click auto-generates a bare `completion`; it is ecosystem-unfriendly.
  - Use `install-shell-completion [--shell bash]` or `print-shell-completion [--shell bash]`.
- `dashboard`, `server`, `repl-mode` — trailing nouns with transitive actions.
  - Use `start-dashboard` etc.

## Reserved single-token flags (not subcommands — §1 never applied)

- `-h`, `--help`, `--help-recursive`
- `--version`
- `--json`
