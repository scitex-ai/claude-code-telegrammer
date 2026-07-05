---
description: |
  [TOPIC] Development Workflow Periodic Audits
  [DETAILS] Run `scitex-dev ecosystem audit-all <pkg>` periodically during development so quality drift is caught the minute it appears, not at release time. Cron / tmux / agent recipes, JSON contract for programmatic consumers, and Claude Code-specific autonomous mechanisms (CronCreate / ScheduleWakeup / Monitor).
tags: [scitex-general-development-periodic-audits]
---

# Periodic audits during development

While editing a scitex-* package, run the auditors *continuously* — not just at release time. Drift caught in 10 minutes is cheap; drift caught three releases later is a refactor.

## The single command

```bash
scitex-dev ecosystem audit-all <distribution>
scitex-dev ecosystem audit-all <distribution> --json --severity error
```

`audit-all` runs every per-package auditor (cli, mcp-tools, skills, python-apis, project) and aggregates exit codes — overall non-zero if any auditor reports a violation. Different from `audit-summary`, which is the **cross-leaf** rollup across the whole ecosystem; `audit-all` is single-leaf, multi-auditor.

For healthy packages the wall-clock is well under 10 seconds total.

## Three portable recipes

### Cron

Runs in the background regardless of whether your editor or shell is open:

```cron
# Every 10 minutes while you're working on <pkg>
*/10 * * * * cd ~/proj/<pkg> && scitex-dev ecosystem audit-all $(basename $PWD) >> ~/.scitex/dev/runtime/audit.log 2>&1
```

Read the log with `tail -f ~/.scitex/dev/runtime/audit.log`.

### tmux / screen background loop

Manual but visible — pane stays open, no log file needed:

```bash
while sleep 300; do
  scitex-dev ecosystem audit-all <pkg> --severity error \
    || say "audit failed"   # or notify-send / scitex-audio speak-text / …
done
```

### Agentic loop (Claude Code)

The `/loop` skill self-paces:

```
/loop 5m scitex-dev ecosystem audit-all <pkg>
```

Or omit the interval to let the agent decide:

```
/loop scitex-dev ecosystem audit-all <pkg>
```

## `--json` for agentic / programmatic consumers

Every auditor accepts `--json`. `audit-all --json` returns a structured aggregate so an agent (or any script) can reason about violations without parsing human text:

```json
{
  "distribution": "scitex-stats",
  "results": {
    "audit-cli":         {"exit": 1, "data": {"package": "...", "violations": [...]}},
    "audit-mcp-tools":   {"exit": 0, "data": {...}},
    "audit-skills":      {"exit": 0, "data": {...}},
    "audit-python-apis": {"exit": 0, "data": {...}},
    "audit-project":     {"exit": 1, "data": {...}}
  }
}
```

Each per-auditor `data.violations` is a list of `{command, rule, message}` objects.

**Agents writing scitex-* packages should:**

1. Run `audit-all <pkg> --json` after every code-shape change (rename, refactor, new command, new submodule).
2. Parse `results[*].data.violations` and self-correct any rule violations before declaring the change done.
3. Track `results[*].exit` — overall non-zero means at least one auditor flagged something.

The JSON contract is stable across packages, so a single agent prompt audits any leaf:

```python
import json, subprocess

r = subprocess.run(
    ["scitex-dev", "ecosystem", "audit-all", pkg, "--json"],
    capture_output=True, text=True,
)
report = json.loads(r.stdout)
all_violations = [
    (auditor, v)
    for auditor, res in report["results"].items()
    for v in res.get("data", {}).get("violations", [])
]
```

The same pattern works for individual auditors (`scitex-dev ecosystem audit-cli <pkg> --json`) when an agent only needs one dimension.

## For Claude Code agents — three autonomous mechanisms

Claude Code exposes three orthogonal scheduling primitives. Pick by work pattern:

| Tool | Purpose | When to use |
|---|---|---|
| **`CronCreate`** | Fixed cron schedule (e.g. `*/10 * * * *`). Fires while the REPL is idle. Auto-expires after 7 days; cancel sooner with `CronDelete`. | "Run `audit-all` every 10 minutes regardless of what I'm doing." |
| **`ScheduleWakeup`** | Self-paced — agent picks the delay each turn based on what it's waiting for (e.g. CI to finish, a long-running test). | "After I push a refactor, wake me when `audit-all` would catch a regression I haven't yet committed." |
| **`Monitor`** | Passive event-stream watcher (good for `tail -f` / poll loops). Surfaces matching lines as notifications without re-running anything. | "Tail `~/.scitex/dev/runtime/audit.log` and surface the line whenever an auditor reports a new violation." |

### Idiomatic usage

```
# Cron — runs in background, regardless of conversation state
CronCreate("*/10 * * * *",
           "scitex-dev ecosystem audit-all $(basename $(pwd)) --json --severity error",
           summary="audit current package every 10 min")

# Self-paced — agent chooses next delay each iteration
ScheduleWakeup(delaySeconds=300,
               reason="check audit-all post-refactor",
               prompt="<<autonomous-loop-dynamic>>")

# Monitor — stream every new auditor warning
Monitor("tail -f ~/.scitex/dev/runtime/audit.log | grep --line-buffered '\\[§\\|\\[PS\\|\\[PA'",
        description="audit violations in current package")
```

### Pairing pattern (recommended)

```
agent commits a change
     │
     ▼
CronCreate   ──writes──▶  ~/.scitex/dev/runtime/audit.log
                                │
                                ▼
                          Monitor  ──notifies──▶  agent reacts
```

The agent never has to remember to re-audit; the harness does it. New violations surface as conversation events that interrupt whatever the agent is working on next.

These three mechanisms are Claude Code-specific — other harnesses won't have the same primitive names. For non-Claude-Code use, the cron + tmux-loop recipes above remain the portable equivalents.

## Why periodic over per-commit

A `pre-commit` hook fails *the commit you just typed* — useful for hard rules like syntax errors, but adds friction during exploratory work. Periodic auditing is gentler:

- **Visibility without blocking.** You can commit a half-finished refactor; the next audit cycle will tell you what regressed without preventing the commit.
- **Catches drift the package itself causes.** A new dep added in `pyproject.toml` may push your `import` time past the §10 (CLI startup speed) threshold without changing any of your own code; per-commit hooks miss it; periodic auditing catches it the next cycle.
- **Free CI dry-run.** What `audit-all` flags locally is what your leaf's CI gate (composite GitHub Action) flags upstream. Same rules, instant feedback.

For hard gates use both: periodic audit during development *plus* `audit-all --severity error` as a CI step before merge.

## Related skills

- [`03_interface/02_cli/07_audit-cli.md`](../03_interface/02_cli/07_audit-cli.md) — what `audit-cli` checks (rule list, severity, dictionary).
- [`03_interface/01_python-api/04_lazy-imports-and-optional-deps.md`](../03_interface/01_python-api/04_lazy-imports-and-optional-deps.md) — PEP 562 `__getattr__` for §10 (CLI startup speed).
- [`02_package/07_github-actions.md`](../02_package/07_github-actions.md) — wiring `audit-all` into per-leaf CI.
- [`05_development/01_version-control.md`](01_version-control.md) — branch model, semver tagging, release gates.
- [`05_development/03_release-automation.md`](03_release-automation.md) — `scitex-dev ecosystem sync` and the dashboard.
