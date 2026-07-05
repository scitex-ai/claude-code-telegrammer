---
description: |
  [TOPIC] Interface Cli Noun Verb
  [DETAILS] SciTeX CLI subcommand grammar — chain shape `<cli> <noun> [<noun> …] <verb>`, transitive vs intransitive verbs, tree vs compound-leaf, ambiguous tokens.
tags: [scitex-general-interface-cli-subcommand-structure-noun-verb]
---

# §1. Subcommand structure — noun-verb

Chain shape:

```
<cli> <noun> [<noun> …] <verb> [OPTIONS] [ARGS]
```

## Noun

- Domain category — resource type, config surface, dataset, machine.
- Every subcommand **except the last** is a noun.
- Hyphenate compounds: `remote-host`, `pypi-account`.

## Verb

- The action. The **last subcommand is always a verb**.
- Two grammatical classes:

### Transitive (needs an object)

- Examples: `list`, `show`, `create`, `delete`, `update`, `start`, `stop`, `publish`, `validate`.
- Must carry the object — either tree (`<noun> <verb>`) or compound (`<verb>-<noun>`).
- Bare transitive at top level is **forbidden**:
  - `<cli> list` ✗
  - `<cli> list-python-apis` ✓
  - `<cli> python-api list` ✓

### Intransitive (complete without an object)

- Examples: `doctor`, `sync`, `repl`, `shell`.
- May stand alone as **exceptions** — see [04_exceptions.md](04_exceptions.md).

## Tree vs compound leaf (transitive only)

- **Tree** `<noun> <verb>` — when the noun has 3+ sibling verbs to group.
  - e.g. `job list`, `job send`, `job cancel`.
- **Compound leaf** `<verb>-<noun>` — when the noun has 1–2 leaf actions.
  - e.g. `start-dashboard`, `list-python-apis`.
  - Preferred default for one-off leaves.
- **Never split** a compound verb across tokens:
  - `send heartbeat` ✗
  - `send-heartbeat` ✓

## Object resolution

| Chain             | Validity | Why                                    | Notes                          |
|-------------------|----------|----------------------------------------|--------------------------------|
| `<cli> job list`  | ✓        | implicit object = preceding noun `job` | prefer when 3+ sibling verbs   |
| `<cli> list-jobs` | ✓        | object baked into the verb             | prefer when 1–2 leaf actions   |
| `<cli> list`      | ✗        | no object anywhere                     | **never**                      |
| `<cli> job`       | ✗        | trailing noun, no action               | **never** (unless exception)   |

## Polysemous "show-me-X" leaves under a noun group

A small set of tokens (`status`, `logs`, `log`, `info`, `health`,
`summary`, `report`) are technically nouns but read as
intransitive-verb shorthand for "report this thing's status / logs /
…". They are allowed as **leaf tokens under a noun group**:

```
<cli> agent status                   # ok — noun group + polysemous leaf
<cli> job logs                       # ok — same shape
```

They are still **forbidden as bare top-level leaves** — `<cli> status`
fails §1 (no object). The catalog labels them as `{noun, verb-i}`; the
auditor's polysemous-escape lets them through specifically when nested.

This avoids both the `show-status`/`list-logs` compound clutter and the
audit's strict "leaf must be verb" complaint.

## Ambiguous tokens (noun+verb in English)

- Words like `list`, `start`, `run`, `package`, `host`, `job`, `shell`, `doctor` are grammatically both.
- Pick **one role per token per package**. Don't overload.

Frequently-overloaded tokens — canonical fixed roles (apply to the whole catalog, not just these examples):

- **Verbs only:** `list`, `start`, `stop`, `show`, `update`, `tag`.
- **Nouns only:** `package`, `host`, `job`, `run`, `log`, `release`.
  - Use `deploy-package`, `start-host`, `submit-job`, `start-run`, `show-log`, `cut-release` for the verb action.
- **Intransitive exceptions:** `shell`, `doctor` (see [04_exceptions.md](04_exceptions.md)).
- **When in doubt:** prefer noun + invented verb.
  - `package deploy` beats overloading `package`.
- All other transitive verbs in [06_noun-verb-catalog.md](06_noun-verb-catalog.md) (`create`, `delete`, `publish`, …) follow the same rule: never bare at top level, always with an object.

The `scitex-dev ecosystem audit-cli` linter ([07_audit-cli.md](07_audit-cli.md)) enforces the catalog.

## Examples (placeholders, not a real command set)

```
<cli> start-dashboard                   # compound leaf
<cli> list-python-apis                  # compound leaf
<cli> job list                          # noun → verb
<cli> job send --id <id>
<cli> job cancel --id <id>
<cli> ecosystem package list            # noun → noun → verb
<cli> machine send-heartbeat --host h1  # noun → compound verb
```

## Anti-patterns

```
<cli> list                              # bare transitive verb (no object)
<cli> dashboard                         # trailing noun (use start-dashboard)
<cli> create resource <name>            # verb before noun
<cli> resource send heartbeat           # compound verb split
```

## Exception — verb with required positional object

A bare transitive verb at the top level is **acceptable** when it
takes its object as a required positional argument:

```
<cli> install <pkg>                     # ok — object is the positional
<cli> commit -m "..."                   # ok — same shape
<cli> verify <SOURCE>                   # ok — SOURCE is the object
```

Compare `pip install <pkg>`, `git commit`, `pytest <path>` — ergonomic,
unambiguous, no `<verb>-<noun>` clutter. The auditor's §1 rule has a
matching exception (`_has_required_positional`): if the leaf declares
at least one required positional argument, the warning is suppressed.

This means the design choice between
`<cli> verify-package <SOURCE>` (hyphenated compound) and
`<cli> verify <SOURCE>` (verb + positional) is up to taste. **Both pass
the audit.** Pick the one that reads better to your users — for action
verbs whose object is *the* positional, the second form is almost
always cleaner.

Pure pytest-style — `<cli> <SOURCE>` with no verb at all (positional
on the group itself) — is also fine and even more concise; pick this
when there's a single dominant action and verbs would just be noise.

## Rationale

- Nouns align with the user's mental objects.
- Enables tab-completion and `<cli> <noun> --help` audit ("what can I do with X?").
- Often aliased so bare `<cli> <noun>` shows help.
