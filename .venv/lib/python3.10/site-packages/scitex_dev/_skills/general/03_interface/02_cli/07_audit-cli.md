---
description: |
  [TOPIC] Interface Cli Audit
  [DETAILS] SciTeX CLI automated audit — `scitex-dev ecosystem audit-cli`. Token classification, what it flags, custom dict format.
tags: [scitex-general-interface-cli-audit-cli]
---

# §1e. Automated check — `scitex-dev ecosystem audit-cli`

- Opt-in linter that walks a package's Click command tree.
- Warns (never errors) on §1 / §1d violations.
- Behind the `cli-audit` extra so ordinary consumers don't pull dictionary data.

```bash
pip install 'scitex-dev[cli-audit]'
scitex-dev ecosystem audit-cli <package-name>
scitex-dev ecosystem audit-cli <package-name> --behavioral   # also run subprocess checks (slow)
```

## Token classification (first hit wins)

1. `<project-root>/.scitex/dev/cli-audit-dict.yaml` — project-local dict.
2. `~/.scitex/dev/cli-audit-dict.yaml` — user dict.
3. Bundled catalog from [06_noun-verb-catalog.md](06_noun-verb-catalog.md).
4. Moby POS dictionary (~130k English words, vendored ~900 KB gzipped).
5. Otherwise → warning to extend the custom dict.

## What it flags (warn-only)

- §1 leaf token is a noun without a verb (`<cli> dashboard` → suggests `start-dashboard`).
- §1 bare transitive verb at top level (`<cli> list` → demands `list-<object>`). **Exception:** if the verb declares a required positional argument (`<cli> install <pkg>`), the object is right there; the warning is suppressed.
- §1 group (non-leaf) token is a verb (groups must be nouns).
- §1a missing introspection commands (`list-python-apis`, `mcp list-tools`, `install-shell-completion`, `print-shell-completion`) and their `--json` flag. Tab completion is a §1a baseline requirement — without `install-shell-completion`, users typing `<cli> <TAB>` get nothing (the 2026-05-06 scitex-hpc symptom).
- §1b banned bare leaves (`version`, `completion`).
- §1d tokens not in catalog/dict/Moby.
- §2 missing universal flags at top: `--version`/`-V`, `--help-recursive`, **`--json`** (so `<cli> --json` parses without crashing); on read verbs: `--json`; on mutating verbs: `--dry-run` and `--yes`/`-y`.
- §4 missing concrete example in command help/epilog (Click guarantees the Usage line).
- §10 CLI startup speed — `import <top-level-module>` cold-start exceeds 500ms.
- §11 CLI framework conformance — entry-point module or sibling `_cli/` imports `argparse`. Migrate to Click (canonical). argparse adds drift (doubled subparser metavar in --help, no shared CategorizedGroup, manual `--json` wiring per parser, no `--help-recursive` plumbing, **no `click.shell_completion` so tab completion does not exist**). Click runs the program once per Tab press; slow import = unusable tab-completion. Remediation: PEP 562 lazy `__getattr__` in `__init__.py` (see python-api skill 04 "PEP 562 module __getattr__" section). Known holdouts as of 2026-05-06: scitex-scholar (argparse-based; ships all 4 mcp subcommands but cannot expose tab completion until migrated to click).
- §5b umbrella drift — for any package present in both the umbrella (`scitex/cli/<short>.py`) and the standalone (`scitex_<pkg>._cli` / branded `<brand>._cli`):
  - Flag the umbrella file if it defines a `click.command` that calls `subprocess.run`/`subprocess.call` with the standalone CLI as argv[0]. The canonical shape re-exports the standalone's `click.Group` and only sets `.name`.
  - Flag the umbrella file if it hand-types a help body that duplicates standalone subcommand names (heuristic: any standalone leaf token literal appearing inside the umbrella file). The umbrella owns only the namespace name.
  - Flag standalone help/epilog/docstring bodies that contain a hardcoded brand literal (`scitex-<pkg>` or the entry from `ECOSYSTEM["<pkg>"].pypi_name` for branded packages). Suggest `{prog}` (formatted from `ctx.find_root().info_name`) or `<cli>` placeholder.

## Coverage matrix

Auditor coverage of each rule (`yes` = enforced statically; `partial` = best-effort heuristic; `no` = not yet auditable):

| Rule | Topic                                        | Coverage  | Notes                                                                |
|------|----------------------------------------------|-----------|----------------------------------------------------------------------|
| §1   | Noun-verb subcommand structure               | yes       | Click tree walk, token classification.                               |
| §1a  | Required introspection commands              | yes       | Presence + `--json` static; `-v|-vv|-vvv` monotonic ladder behavioral (`--behavioral`). |
| §1b  | Banned bare leaves (`version`, `completion`) | yes       | Hard-coded denylist at any depth.                                    |
| §1c  | Pass-through entry points                    | no        | Auditor cannot statically detect verbatim-forward entries.           |
| §1d  | Vocabulary in catalog/dict/Moby              | yes       | Layered lookup; warns on `unknown`.                                  |
| §1e  | (this section — the auditor itself)          | n/a       |                                                                      |
| §2   | Universal flag presence                      | yes       | Root: `--version`/`-V`, `--help-recursive`, `--json` (parseable). Leaves: `--json` on read verbs; `--dry-run` and `--yes`/`-y` on mutating verbs. |
| §3   | Exit code conformance                        | partial   | Top-level bogus-flag returns 2 (behavioral; `--behavioral`).         |
| §4   | Help format                                  | partial   | Heuristic: looks for "example", "$ ", or "e.g." in help/epilog.      |
| §5   | Deprecation hard-error redirect              | no        | Renamed commands are typically `hidden=True`; auditor skips them.    |
| §5b  | Umbrella subcommand passthrough              | TODO      | Diff `scitex <short> --help` vs standalone `--help` (modulo prog-name); flag hand-typed wrappers + `subprocess.call(["scitex-<pkg>", ...])` shapes; flag hardcoded brand strings (`scitex-<pkg>`, `socialia`, …) in help bodies that will be rendered under the umbrella. See [05a_umbrella-passthrough.md](05a_umbrella-passthrough.md). |
| §6a  | Env var prefix `SCITEX_<PKG>_*`              | partial   | Static source scan flags bare-pkg prefix; cross-pkg `SCITEX_*` allowed. |
| §6b  | Config path fallback documented in `--help`  | yes       | Greps root help/epilog for `config.yaml`, `$SCITEX_<PKG>_CONFIG`, or `~/.scitex/`. |
| §7   | CLI ↔ MCP parity                             | no        | Could compare `list-python-apis` and `mcp list-tools` output (TODO). |
| §8   | stdout/stderr discipline                     | partial   | `list-python-apis --json` parsed as JSON (behavioral; `--behavioral`). |
| §10  | CLI startup speed (`import <pkg>` < 500ms)   | yes       | Cold-start measurement in fresh subprocess. Threshold: 500ms (Click runs program once per Tab press). Remediation: PEP 562 lazy `__getattr__` in `__init__.py`. |
| §11  | CLI framework conformance (Click canonical)  | yes       | Static scan of entry-point module + sibling `_cli/` dir for `import argparse` / `from argparse`. Click is canonical for every scitex-* CLI; argparse causes drift (doubled subparser metavar, manual `--json` wiring per parser, no shared CategorizedGroup). |

## Periodic auditing during development

For how to run `audit-all` continuously while editing a package — cron / tmux / agent recipes, the JSON contract for programmatic consumers, and Claude Code-specific autonomous mechanisms — see [`05_development/02_periodic-audits.md`](../../05_development/02_periodic-audits.md).

This file (`07_audit-cli.md`) is about *what* `audit-cli` checks; the periodic-audits skill is about *when* and *how* to invoke it during development.

## Custom dict format

```yaml
# cli-audit-dict.yaml
nouns:
  - bibentry
  - openurl
transitive_verbs:
  - enrich
  - deduplicate
intransitive_verbs:
  - vacuum
```

## Operational notes

- Run in CI for every `scitex-*` repo.
- Never fails the build, but drift becomes visible.
- Custom dicts are **additive**: they extend the catalog with package-specific tokens, never reclassify or override existing ones. A token already classified by the canonical catalog keeps its class even if also listed in a dict.
