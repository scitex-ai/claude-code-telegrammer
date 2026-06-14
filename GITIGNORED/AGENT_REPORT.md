<!-- hook-bypass: branch-guard -->
# proj-claude-code-telegrammer — task report 2026-06-05

## TASK: inbound forwarded-message handling enhancement

### STATUS: PR open, ready for lead review

PR: https://github.com/ywatanabe1989/claude-code-telegrammer/pull/20
Branch: `feat/inbound-forwarded-messages` off `develop`
Worktree: `/home/ywatanabe/proj/claude-code-telegrammer/.worktrees/feat-forwarded-messages`

Commits (2):
- `954329d` feat(poller): capture forwarded-message provenance + harden media+caption
- `b76b09c` chore(dist): rebuild bundle with forwarded-message provenance

Source files touched:
- `ts/lib/forward.ts` (new) — parseForward + buildInboundText + forwardBanner
- `ts/lib/poller.ts` — uses helpers, populates meta + forward_json
- `ts/lib/store.ts` — forward_json TEXT column + idempotent ensureColumn migration

Tests added (real Telegram update-JSON fixtures, no mocks):
- `ts/test/forward.test.ts`
- `ts/test/forward-pipeline.test.ts`
- `ts/test/store-migration.test.ts`
- `ts/test/store.test.ts` (extended)

Test suite: **142 pass / 0 fail / 295 expect calls**.
Bundle rebuild: `bun build --target=node` → `ts/dist/telegram-server.js` (232 modules, 0.53 MB). Verified `forward_origin` + `forward_json` references shipped.

### BLOCKER: a2a send to `lead` denied

`mcp__sac__a2a_send(target='lead', ...)` returned:

```
status: 403
ACL deny: cross-group send: sender 'proj-claude-code-telegrammer'
(group=['proj-claude-code-telegrammer']) may not address 'lead'
without an explicit ACL grant.
Add a grant with `grant_send(sender='proj-claude-code-telegrammer',
target='lead')` in state.db.
```

`a2a_peers` shows no `lead` entry — only cohort capsules, handyman-*,
proj-* (including this agent), and cred-refresher-*. No "lead" peer
is currently registered/visible to me.

### NUMBERED OPTIONS for operator

1. **Operator runs the ACL grant** — `grant_send(sender='proj-claude-code-telegrammer', target='lead')` in sac state.db, then I retry the a2a_send with the PR URL + summary. Preferred — restores the "report to lead" protocol the briefing specified.

2. **Different target name** — operator confirms the actual lead-agent name (e.g. `handyman`, a `proj-*`, or a peer I'm missing) and I retry a2a_send to that name.

3. **No a2a, PR-channel only** — operator monitors the PR (#20) directly; this report stands as the deliverable. PR is review-ready right now.

Recommend option 1 (grant) so future tasks don't re-hit this.

### Discipline checklist
- [x] worktree + branch created off `origin/develop` (not `/work` develop)
- [x] source commit landed BEFORE bundle rebuild
- [x] bundle rebuilt + committed separately
- [x] no `--no-verify`, no force-push, no Co-Authored-By trailer
- [x] full test suite green pre-push
- [x] one task → one PR
