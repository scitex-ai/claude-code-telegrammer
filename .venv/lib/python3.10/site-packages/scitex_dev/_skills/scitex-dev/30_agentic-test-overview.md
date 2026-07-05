---
description: |
  [TOPIC] Agentic Test Overview
  [DETAILS] STALE (2026-05-02) — superseded by the standalone newb package. The scitex-agentic-test image and its publish workflow were removed from scitex-agent-container; sac itself is being redesigned around claude-agent-sdk. Kept for historical context only; do not follow the workflow as written. Re-author once sac's new design lands.
tags: [scitex-dev-agentic-test-overview]
---

> **⚠ STALE — 2026-05-02.** The `scitex-agentic-test` image referenced
> below has been removed from scitex-agent-container. Skill and MCP
> evaluation moved to the standalone [newb](https://github.com/ywatanabe1989/newb)
> package. scitex-agent-container is being redesigned around
> claude-agent-sdk; this skill will be re-authored once that lands.
> Do not follow the workflow described here.

# 30_agentic-test-overview

Umbrella for SciTeX's **agentic testing** family — evaluations that run
inside a clean Claude Code instance to measure whether skills and MCP
servers behave as intended end-to-end.

See the split leaves:

- [31_agentic-test-skills.md](31_agentic-test-skills.md) — skill
  trigger-rate (Layer 2): does Claude view the expected `SKILL.md`?
- [32_agentic-test-mcp.md](32_agentic-test-mcp.md) — MCP evaluation
  (Layer 2+3): does Claude call the expected tool(s) with the right
  arguments and follow through?

## Why agentic tests exist

Structural tests (see `_skills_quality_pytest`, enforced per package via
`tests/test_skills_quality.py`) prove a skill *looks* right — prefix
numbering, index consistency, no monoliths. Agentic tests prove it
*fires* and *helps* — a perfect-looking skill that Claude never consults
is dead weight.

## The four layers

Adapted from Anthropic's `skill-creator` methodology:

| Layer | Question | Measured by |
|-------|----------|-------------|
| 1. Structure  | Does the skill look right?                | `_skills_quality_pytest` (§1–§4 checklist) |
| 2. Trigger    | Does Claude view the skill for the query? | `_agentic_testing_pytest` — tool-use log |
| 3. Compliance | Does the output follow the skill?         | LLM-as-judge over output + skill body |
| 4. Outcome    | Does the end-user goal succeed?           | E2E (file produced, MCP tool succeeded) |

This leaf is the entry point. The two siblings (17, 18) specialise
Layers 2-4 for skills and MCP respectively.

## Shared substrate — newbie-docker (generic image + runtime mounts)

All agentic tests (skill + MCP) share the same isolation primitive:

- **Generic clean container** — `scitex-agentic-test:latest`, built from
  `scitex-agent-container:latest`. Node + claude CLI only. **No skills
  or credentials baked in.** Rebuild only on base-image changes; never
  on skill edits.
- **Host `$HOME/.claude/` stays pristine.** Tests never write there.
  Production conversation history, user CLAUDE.md, and real skill
  catalog are left alone.
- **Per-run staging dir** — e.g. `/tmp/evalrun_<id>/` containing just
  the skills under test and (if desired) an empty `projects/` for
  in-container history. Teardown = `rm -rf`.
- **Credentials, not API key** — mount *only*
  `~/.claude/.credentials.json` (copied to a world-readable tmp first
  because container uid ≠ host uid). Claude Code runs under your Max
  plan quota → **$0 real cost** regardless of the `total_cost_usd`
  reported in the JSON envelope.
- **Skills mounted read-only from the staging dir** — change a skill
  and re-run immediately, no image rebuild, no tag churn, no
  combinatorial image explosion.

Rationale for runtime mount (recorded 2026-04-23):

1. Skill bodies change often; `docker build` on every edit kills
   iteration speed.
2. For N skills there are 2ⁿ possible scopes to evaluate; one image
   per scope = combinatorial explosion. One generic image + different
   mounts = linear.
3. Production parity: `pip install scitex-<pkg>` places `SKILL.md` on
   the filesystem at install time; mount-time injection mimics that.

### Minimal one-shot invocation

```bash
# 1. One-time: writable credentials copy (uid mismatch makes 0600 unreadable)
install -m 644 ~/.claude/.credentials.json /tmp/newbie_creds.json

# 2. Stage a per-run HOME with just the skills under test
mkdir -p /tmp/evalrun-$$/skills/<pkg>
cp -rf <source>/SKILL.md /tmp/evalrun-$$/skills/<pkg>/SKILL.md

# 3. Run
docker run --rm \
  -v /tmp/evalrun-$$/skills:/home/agent/.claude/skills:ro \
  -v /tmp/newbie_creds.json:/home/agent/.claude/.credentials.json \
  scitex-agentic-test:latest \
  -p "<query>" --output-format json --model claude-haiku-4-5 \
  --dangerously-skip-permissions
```

This is the base primitive. Layers 2-4 parse the returned JSON differently.

### Per-project conversation history (optional)

For iterative debugging, mount `<project-root>/.claude/` (not host
`$HOME/.claude/`) as the container HOME. Conversation history for that
project accumulates under `<project-root>/.claude/projects/` while the
skills mount overlays a clean catalog on top:

```bash
docker run --rm \
  -v <project-root>/.claude:/home/agent/.claude \
  -v /tmp/evalrun-$$/skills:/home/agent/.claude/skills:ro \
  -v /tmp/newbie_creds.json:/home/agent/.claude/.credentials.json \
  scitex-agentic-test:latest -p "<query>" ...
```

`<project-root>/.claude/` should be git-ignored.

## Why `claude -p`, not the Anthropic API

- **Plan quota covers it**, reported `total_cost_usd` is informational.
- Same tool-use semantics as an interactive Claude Code session — skills
  are discovered the way they are in production.
- No API key plumbing, no billing surprises, no rate-limit config.
- Drawback: non-deterministic across runs (plan quota ≠ API raw) — we
  mitigate with 3 runs and a 2-of-3 threshold.

## Honest caveats

- Non-determinism → 2/3 threshold, not 3/3.
- Substantive multi-step queries are required; one-step queries rarely
  trigger a skill even with a perfect description (Claude Code auto-
  loads skill bodies and answers from them directly).
- Over-triggering is a real failure mode — every positive eval should
  have at least one adjacent negative case.
- Single-container-per-process → not yet safe for `pytest-xdist` worker
  parallelism.
- Image must be rebuilt when the baked skill body changes; tag the
  image with the date to get a reproducibility anchor for papers.

## File map

```
scitex-agent-container/containers/
├── Dockerfile                       # base image (Node + claude CLI)
└── Dockerfile.agentic-test          # generic test image (FROM base); no bake

scitex-dev/src/scitex_dev/
├── _agentic_testing/
│   ├── _core.py                     # HostRunner, NewbieDockerRunner
│   ├── _pytest.py                   # make_skill_trigger_tests(...)
│   └── _poc.py                      # CLI: one-shot prompt
└── _skills/scitex-dev/
    ├── 30_agentic-test-overview.md  # this file
    ├── 31_agentic-test-skills.md    # skill-trigger specifics
    └── 32_agentic-test-mcp.md       # MCP-eval specifics
```
