---
description: |
  [TOPIC] Interface Cli Checklist
  [DETAILS] SciTeX CLI manual audit checklist — covers all sections. Run before shipping a CLI. Items marked (A) are auto-checked by `scitex-dev ecosystem audit-cli`; the rest are manual.
tags: [scitex-general-interface-cli-audit-checklist]
---

# §9. Audit checklist

Run through this list before shipping a CLI. Items marked **(A)** are covered by the auditor `scitex-dev ecosystem audit-cli` ([07_audit-cli.md](07_audit-cli.md)); the rest are still manual until the auditor is extended ([TODO.md](TODO.md)).

## Subcommand grammar

- [ ] **(A)** Noun-verb structure (or exception from §1b [04_exceptions.md](04_exceptions.md)).
- [ ] **(A)** No bare transitive verbs at top level (`<cli> list` ✗ → `list-<noun>` ✓).
- [ ] **(A)** No trailing nouns without a verb (`<cli> dashboard` ✗ → `start-dashboard` ✓).
- [ ] **(A)** Group (non-leaf) tokens are nouns, never verbs.
- [ ] No banned bare leaves: `version`, `completion` are forbidden (§1b).
- [ ] Compound verbs are hyphenated, never split (`send-heartbeat` ✓, `send heartbeat` ✗).
- [ ] Synonyms picked from the catalog "Prefer" column — no `ls`, `rm`, `display`, … (§1d [06_noun-verb-catalog.md](06_noun-verb-catalog.md)).
- [ ] Pass-through entry points (§1c [05_pass-through.md](05_pass-through.md)) explicitly declared and noted in `--help`.

## Required commands

- [ ] `list-python-apis` exists with `-v|-vv|-vvv` and `--json` (§1a [03_required-introspection-commands.md](03_required-introspection-commands.md)).
- [ ] `mcp list-tools` exists with `-v|-vv|-vvv` and `--json`.
- [ ] Verbosity ladder is **additive** — each level strictly extends the previous one.
- [ ] `mcp` group includes `start`, `doctor`, `list-tools`, `show-installation`.
- [ ] `doctor` (or equivalent) self-diagnoses install/environment.

## Universal flags (§2 [08_universal-flags.md](08_universal-flags.md))

- [ ] `-h` / `--help` on every command.
- [ ] `--help-recursive` at top level.
- [ ] `--version` / `-V` at top level prints `pkg/X.Y.Z`.
- [ ] `--json` on every data-reading command (introspection, list, show, get, search, …).
- [ ] **JSON content parity** (§2 [08_universal-flags.md](08_universal-flags.md)): every field shown in text mode appears in `--json` mode. No fetch-path forking on `as_json` that drops data. `--help-recursive --json` produces a structured tree, not plain text.
- [ ] `--dry-run` on every mutating command.
- [ ] `--yes` / `-y` on every mutating command that would otherwise prompt.
- [ ] `--verbose` / `-v` accepts the count style (`-v` / `-vv` / `-vvv`) where applicable.
- [ ] No interactive prompts: missing input → exit 2 + clear stderr (never `input()` / `read` / sudo).

## Exit codes (§3 [09_exit-codes.md](09_exit-codes.md))

- [ ] `0` only on success.
- [ ] `2` on every usage error (bad flag, missing arg, precondition unmet, deprecated name).
- [ ] Domain-specific codes (`3-9`) documented in `--help`.

## Help format (§4 [10_help-format.md](10_help-format.md))

- [ ] One-line description present.
- [ ] Usage synopsis matches `<cli> <noun> <verb> [OPTIONS] ARG`.
- [ ] At least one concrete example.
- [ ] Flag list with descriptions.
- [ ] Exit-code summary if any code outside `0/1/2` is used.

## Deprecation (§5 [11_deprecation.md](11_deprecation.md))

- [ ] Renamed commands hard-error (exit 2) with a `Re-run with: …` redirect.
- [ ] Parameter-level deprecation (`--foo` → `--bar`) warns once per shell session, not every call.

## Config + env (§6 [12_config-and-env.md](12_config-and-env.md))

- [ ] All scitex-owned env vars use `SCITEX_<PKG>_*`.
- [ ] No bare package-name prefixes (e.g. `IO_*`).
- [ ] Config file precedence (`--config` → `$SCITEX_<PKG>_CONFIG` → project → user) documented in `--help`.
- [ ] Canonical filename is `config.yaml` (never `<pkg>_config.yaml`).

## MCP parity (§7 [13_mcp-parity.md](13_mcp-parity.md))

- [ ] CLI subcommand and MCP tool share the same logical name.
- [ ] Argument names and types match.
- [ ] JSON output shape matches between `<cli> --json` and the MCP tool result.
- [ ] Parity documented in the package's `SKILL.md`.

## Streams (§8 [14_stdout-stderr.md](14_stdout-stderr.md))

- [ ] stdout carries only data / JSON / parseable output.
- [ ] stderr carries logs, progress, warnings, errors.
- [ ] `cmd --json | jq ...` works with zero log contamination on stdout.

## Reference parity

- [ ] CLI matches the canonical shape in [16_example.md](16_example.md): noun groups + compound leaves; no bare transitive top-level verbs.
