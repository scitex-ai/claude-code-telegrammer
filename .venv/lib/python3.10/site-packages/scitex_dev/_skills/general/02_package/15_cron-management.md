---
description: |
  [TOPIC] Ecosystem-wide cron management lives in scitex-dev.
  [DETAILS] Cross-package scheduled tasks are consolidated under `scitex-dev cron`
  (verbs: `list`, `install <name>`, `remove <name>`, `status`, plus the
  cron-invoked `exec <name>`). Each managed crontab line is tagged with the
  marker comment `# scitex-dev cron: <name>` so install / remove operations
  target only the named line and leave every unrelated entry verbatim. Jobs are
  declared in `scitex_dev._cli.cron._jobs.JOB_REGISTRY` (name → schedule +
  command + description); first registered job is `ci-watch` (10-minute poll of
  each sac agent's owned repo for CI red on develop → A2A fix-forward turn via
  `sac agents send`). Single ownership: don't add scheduled jobs under
  individual scitex-* packages — register them here.
tags: [scitex-general-package-cron-management]
---

# Ecosystem-wide cron management

## Why scitex-dev owns this

Scheduled cross-package work is *ecosystem-wide* infrastructure: the
ci-watch loop polls every sac agent's repo, the future rotate-all loop
pushes credentials to every package, the future audit-sweep loop runs
auditors across the whole tree. None of these belong inside a single
scitex-* package because none of them are *about* a single package.

Putting them in scitex-dev gives one canonical place to look ("is the
loop installed? what's its schedule? when did it last run?"), one
predictable layout (the same four verbs across every job), and one
operator-facing surface (`scitex-dev cron …` instead of N package
CLIs).

## The four verbs

```bash
scitex-dev cron list                  # registry + currently-installed lines
scitex-dev cron install <name>        # materialise the registered job
scitex-dev cron remove <name>         # strip the named line
scitex-dev cron status                # last-run / next-run hints
scitex-dev cron exec <name>           # execute the job's body (cron itself uses this)
```

The `exec` verb is used rather than `run` because the CLI audit (§1c)
intentionally treats `run` as a noun-only token.

`install` and `remove` both honour `--dry-run`; `install` and `remove`
require `-y` / `--yes` to actually mutate the crontab.

## The marker convention

Every managed crontab line ends with the sentinel comment

```
# scitex-dev cron: <name>
```

`<name>` is the registry key (`ci-watch`, future `rotate-all`, etc.).
The marker is what `list` / `remove` use to identify managed lines —
without it, the parser would have to match on schedule + command,
which drifts the moment a job updates its schedule.

Every other line in the user's crontab (including blank lines, comments,
and other people's jobs) is preserved verbatim. Install is idempotent:
re-running it replaces the same-named line in place rather than
appending.

## Adding a new job

1. **Implement the body.** Add a module under
   `src/scitex_dev/_cli/cron/_<job>.py` exposing a single
   `run_once(...)` entry point.
2. **Register it.** Add an entry to `JOB_REGISTRY` in
   `src/scitex_dev/_cli/cron/_jobs.py`:
   ```python
   "rotate-all": JobSpec(
       name="rotate-all",
       schedule="0 * * * *",
       command="scitex-dev cron exec rotate-all >> ~/.scitex/dev/logs/cron-rotate-all.log 2>&1",
       description="Rotate CLAUDE_CODE_CREDENTIALS_JSON across the ecosystem.",
   ),
   ```
3. **Wire the exec-body.** Add a dispatch branch in
   `src/scitex_dev/_cli/cron/run.py` so `scitex-dev cron exec rotate-all`
   actually invokes your `run_once`.
4. **Pin it.** Add a test that asserts the registry entry exists with
   the expected schedule + command — see
   `tests/scitex_dev/_cli/cron/test__jobs.py` for the pattern.

That's the whole diff. The CLI verbs (`list`, `install`, `remove`,
`status`) automatically pick up the new entry — no per-job wiring on
the operator surface.

## ci-watch — the first registered job

`ci-watch` is the canonical example. It:

  1. Iterates the agent → repo map in
     `scitex_dev._cli.cron._ci_watch.AGENTS_TO_REPOS`.
  2. For each repo, asks `gh run list --branch develop --limit 12` for
     the latest run per workflow.
  3. For each workflow whose latest run is `failure`, dispatches a
     fix-forward A2A turn to the responsible agent via
     `sac agents send <agent> <prompt>`.

The dispatched prompt is a verbatim port of the bash prototype's
template; the agent investigates the failure, opens a PR against
develop, and merges after CI confirms green. If the failure is out of
the agent's scope (e.g. credentials missing on the runner), the agent
replies `BLOCKED <reason>`.

Verify the loop without firing A2A turns:

```bash
scitex-dev cron exec ci-watch --dry-run
```

This prints the would-be prompt and skips the `sac agents send` call.

## worktree-gc — the second registered cleanup-style job

`worktree-gc` is the second cleanup-style example (after `ci-watch`'s
poll-style example). It:

  1. Walks the user's home (configurable via
     `SCITEX_WORKTREE_GC_ROOTS`) finding every repo with a
     `.claude/worktrees/` directory.
  2. For each repo, runs `git worktree list --porcelain` and filters
     the output through `_is_managed_path` — only worktrees under
     `.claude/worktrees/` survive the filter; the operator's own
     `.worktrees/` is dropped here before any removal logic sees it.
  3. For each managed worktree, checks `mtime`. Older than
     `SCITEX_WORKTREE_GC_MAX_AGE_DAYS` (default 3) → candidate.
  4. `git worktree remove <path>` then `git worktree prune`. Git
     refuses dirty / locked / in-use worktrees → result records
     `skipped-refused`; nothing is force-removed.

The single highest-stakes invariant is "only paths under
`.claude/worktrees/` are ever touched." It is pinned by
`_is_managed_path`, by the per-worktree `_gc_one_worktree` boundary
check, by `os.walk`'s explicit skip of `.worktrees`, and by an
end-to-end test that hands the body a fake `git` runner returning both
a managed and a protected path and asserts `git worktree remove` is
called only for the managed one.

Verify the loop without touching anything:

```bash
scitex-dev cron exec worktree-gc --dry-run
```

This prints the would-be-removed worktrees and the reasoning per path
(fresh / stale / refused / errored) without invoking `git worktree
remove`.

Coordination: proj-scitex-agent-container owns the RELOCATION half —
stopping `.claude/worktrees/` from being created in the first place
(the canonical path will move to `.worktrees/` at the repo root).
Until that lands, this GC is the continuous cleanup loop.

## Related skills

- [01_ecosystem/06_dot_scitex_directory.md](../01_ecosystem/06_dot_scitex_directory.md)
  — Where each managed job logs (`~/.scitex/dev/logs/cron-<name>.log`).
- [02_package/07_github-actions.md](07_github-actions.md) —
  CI workflows referenced by `ci-watch` for green-vs-red detection.
- [02_package/12_no-mocks.md](12_no-mocks.md) — Why
  `_crontab.read_crontab` / `_ci_watch.red_workflows_for` /
  `_worktree_gc._gc_one_worktree` expose callable seams instead of
  being patched in tests.
