---
title: CI feedback — decoupled-pollers convention
audience: fleet-agent-authors
status: stable
operator-policy: lead-msg-cd773d41 (2026-06-14), msgs c22c1a3a + 8365876 + 840a7e81 + 192b2528 + 3d465c92 + 04664eed + 8495f58377 + 6cadf82f
---

# CI feedback — decoupled-pollers convention

When a push lands a PR's CI completes, the owning agent should hear
"green → self-merge" or "red → fix-forward" without polling
`gh pr checks` itself (lead-learnings/12: agents misread
pending-vs-failed). Operator's locked design: **three independent
servers, each polls GitHub Actions on its own cadence, each works
STANDALONE**. todo down → sac still delivers verdicts; sac down → todo
still records DONE entries; dev's lane is read-only convention +
observability — no runtime handler.

This skill documents the shared convention all three implementations
code against. Each server is responsible for honouring it in its own
poller; nothing wires the three together at runtime.

## Why decoupled

> どちらも片方でも動作するようにしなくてはならない
> (each must work standalone)
> — operator, lead msg `cd773d41` 2026-06-14

The earlier design (todo polls → emits via `scitex_todo.hooks` →
dev's handler enriches owner → sac's handler delivers) was rejected
as a single point of failure: if the bus broke, neither record nor
delivery would happen. Decoupling removes that risk at the cost of
duplicated GH polls — which is acceptable because the polls are cheap
(`gh` CLI caches 5 min by default + sac can poll at a slower cadence
than todo as a cost mitigation).

The `scitex_todo.hooks` entry-point bus stays alive but is reserved
for the **board-card-message** channel (todo emits card comments →
sac fans-out to owner + collaborators). The bus is the right shape
when there is naturally one source of truth (todo's card store) and
multiple subscribers. CI verdicts have multiple independent sources
(GitHub Actions, polled separately by each consumer), so a bus is
the wrong shape there.

## Lane responsibilities

| Server | Lane | Job | Dedupe state |
|--------|------|-----|--------------|
| **todo** | RECORD | Update CI pills on the board + record a DONE-entry when merge completes. Default-branch HEAD only. | `~/.scitex/todo/ci-state.json`, outer-keyed by `repo`, inner `(head_sha, overall)`. |
| **sac** | DELIVER | Resolve owner + a2a-push verdict to owner + walk `state.db:lineage` up to lead. Open PRs scope (per-PR fan-out). | `state.db:ci_delivered` table, key = `(repo, pr_number, head_sha, conclusion)`. |
| **dev** | CONVENTION + OBSERVABILITY | Maintains this skill leaf + a read-only `scitex-dev ci feedback dry-run --pr=N` CLI that reads sac's state.db + todo's ci-state.json. NO runtime handler. | — |

scitex-dev has no listen server — it cannot own a runtime handler
without standing up one (which the operator explicitly avoided).
Documenting the spec is the right slice for the dev lane.

## Shared convention — data formats only

These shapes are the only contract across the three servers. Each
implements them in its own code; nothing is exchanged at runtime.

### Owner resolution order

1. **Primary** — scan `tasks.yaml` for tasks whose `repo: <owner/repo>`
   matches the verdict's repo. The matching task's `agent: <name>` is
   the owner. Declarative + registry-managed — matches the operator's
   "static mechanism" principle.
2. **Fallback** — grep the PR body for an `Owner: <a2a-target>` line.
   Regex `Owner:\s*([A-Za-z0-9_-]+)`. For PRs that aren't tied to a
   tasks.yaml entry.
3. **Last-resort** — `lead`. Sac's delivery handler logs LOUD when
   this path fires, so the gap is visible.

Both pollers read `tasks.yaml` FRESH each tick (mtime check) so an
operator update is picked up within one cadence. Don't cache.

### Event-kind taxonomy

Five kinds, computed by each poller from its own state-diff against
the previous tick. The names form a stable enum; downstream consumers
discriminate on `event["kind"]`.

* `ci-newly-green` — was red, now green → owner action: self-merge.
* `ci-newly-red` — was green, now red → owner action: fix-forward.
* `ci-still-red` — N hours stuck red → lead help-forward / escalate-persistent.
* `ci-still-green-not-merged` — green AND mergeable, no merge in M hours → lead help-merge.
* `ci-completed` — generic completion (observability; optional).

### Dedupe-key shape

The canonical key is the 4-tuple `(repo, pr_number, head_sha, conclusion)`.
- sac (per-PR scope, DELIVER lane) uses the full 4-tuple.
- todo (default-branch scope, RECORD lane) uses the 2-tuple subset
  `(head_sha, overall)` since `pr_number` doesn't apply to its
  default-branch HEAD poll AND its state-file is already outer-keyed
  by `repo`. Effective shape `(repo, head_sha, overall)` after the
  outer key — collisions can't cross repos.

The divergence is intentional. Documented here so future readers
don't try to reconcile.

### `dev-flow.yaml: ci_feedback` config block

```yaml
# ~/.scitex/agent-container/dev-flow.yaml   (SAC owns canonical shape)
schema_version: 1
ci_feedback:
  red_priority: high            # enum: high | normal | low
  green_priority: normal
  extra_recipients: []          # appended after lineage walk
  retry_backoff_s: [1, 2, 4]    # escalate-to-lead after exhaust
  poll_interval_s: 300          # operator-tunable per server
```

`schema_version` stays at 1 across additive sibling keys (rename /
remove / type-change bumps).

## Holes flagged (intentional trade-offs)

1. **Dual polling cost.** Two servers polling GH CI independently
   doubles API call volume. Mitigations: gh CLI's 5-min cache, and
   sac polling at a slower cadence than todo (delivery-latency
   tolerance is higher than dashboard-refresh latency). If
   per-account rate-limit becomes binding, the next move is NOT
   adding a relay (would reintroduce the single-point-of-failure
   the operator killed); instead, both servers tighten path filters
   on which workflows they poll.
2. **sac-before-todo race.** If sac sees green first AND delivers
   before todo's poll records the DONE entry, the owning agent
   receives the verdict BEFORE the board reflects merge. Fine in
   practice — verdict drives action, record drives observability;
   the operator's mental model accepts the small lag.
3. **tasks.yaml read consistency.** Both pollers read tasks.yaml
   independently. If the operator updates tasks.yaml mid-flight,
   sac and todo may see different snapshots momentarily. Each
   poller does a fresh mtime-check + re-read every tick to bound
   the inconsistency to one cadence.

## Diagnostic marker — runner_name=""

The 2026-06-13 fleet-wide silent-no-steps incident (3-way convergent
diagnosis: dev's CI-health subagent + dev's PyPI investigation
subagent + todo's independent investigation) pinned a useful
signature: `runner_name="" + steps=0 + total_ms=0 + BlobNotFound on
logs API + 5-13s wall-clock`. When the FAILURE mode appears with all
five of those markers, the workflow YAML never assigned a runner —
it's a platform/billing/queue-state issue, NOT a real test failure
or a YAML regression. Worth pinning here so the next investigator
recognises the shape quickly.

If a poller observes a workflow conclusion that matches this
signature on a repo's first failing run in a window, the diagnostic
flag belongs on the verdict payload (something like
`event["diagnostic_class"] = "no-runner-allocation"`); SAC's
delivery handler can priority-bump those to lead immediately.

## Observability — `scitex-dev ci feedback dry-run --pr=N`

(Planned dev-side CLI.) Reads sac's `state.db:ci_delivered` + todo's
`ci-state.json` (both READ-ONLY), reconstructs the projected delivery
chain via `scitex_agent_container._state.lineage.walk_chain(owner)`,
prints:

```
ci feedback dry-run for PR #N on owner/repo:
  Resolved owner: <agent>
  Lineage chain: <agent> → <parent> → ... → lead
  Recipients:    <chain> + <extra_recipients>
  Priority:      <red|green>_priority
  Last sac-state-db entry:  <conclusion> @ <ts>
  Last todo-state entry:    <overall> @ <ts>
```

Useful for "why didn't I get this verdict?" investigations. Strict
read-only against both servers' state files; no runtime call to
either server's listen endpoint.

## See also

- lead msgs: `c22c1a3a` (reconcile-3-way), `8365876` (pure pub/sub),
  `840a7e81` (lineage fan-out), `192b2528` (event-driven not polling),
  `3d465c92` (consolidated principle), `04664eed` (sac's lineage walk),
  `cd773d41` (decoupled-pollers operator override).
- todo msgs: `b14b8f67` (record contract), `5c454ec4` (key-shape),
  `90c62b51` (bus mechanics), `0f2a013125` (v0.7.25 ci-watch shipped).
- sac msgs: `c4cced7b` (contract confirmation), `c638dcc312` (lineage
  schema), `78495aacaac24eb7` (per-PR + 5-min cadence), `df9758458d`
  (lineage walk_chain API + dev-flow.yaml schema).
- 2026-06-14 silent-no-steps convergent diagnosis: scitex-dev #194
  (PyPI investigation doc), scitex-dev #19 (CI-health sweep).

<!-- EOF -->
