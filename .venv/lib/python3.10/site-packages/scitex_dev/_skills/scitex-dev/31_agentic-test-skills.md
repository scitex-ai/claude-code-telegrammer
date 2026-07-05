---
description: |
  [TOPIC] Agentic Test Skills
  [DETAILS] STALE (2026-05-02) — superseded by the standalone newb package. The scitex-agentic-test image and SCITEX_DEV_AGENTIC_DOCKER_IMAGE wiring described below no longer apply. Kept for historical context only; re-author once sac's claude-agent-sdk redesign lands.
tags: [scitex-dev-agentic-test-skills]
---

# 31_agentic-test-skills

> **STALE 2026-05-02** — `scitex-agentic-test` image + `SCITEX_DEV_AGENTIC_DOCKER_IMAGE` retired; moved to [newb](https://github.com/ywatanabe1989/newb).

Layer 2 of agentic testing (see [30_agentic-test-overview.md]). Given a
clean Claude Code instance and exactly one scoped skill catalog, measure
whether a realistic user query causes Claude to view the expected
`SKILL.md`.

## What gets measured — hard vs soft trigger

Per official Claude Code docs (`Extend Claude with skills.md`, 2026-04):

> "In a regular session, skill descriptions are loaded into context so
> Claude knows what's available, but full skill content only loads
> when invoked."

Two distinct trigger signals exist:

- **Hard trigger**: a `tool_use` block with `name ∈ {Read, view}` and a
  path that substring-matches the expected `SKILL.md`. Explicit, easy
  to extract from the JSON envelope.
- **Soft trigger**: no explicit `Read`, but the skill body was
  auto-loaded from description match (standard Claude Code behavior)
  and the response contains skill-specific content. `tool_use` count
  is 0 yet the answer is still correct.

**Measuring only hard triggers underestimates true trigger rate.**
Verified empirically 2026-04-23: with a pushy "ALWAYS invoke this
skill when... Do not answer from training" description on scitex-io's
SKILL.md, Claude returned the correct API (`sio.save(df, ...,
use_caller_path=True)`) with zero `tool_use` — proof that the skill
body was consulted via auto-load.

### Recommended eval JSON additions

Add `"answer_contains": ["use_caller_path=True", "stx.io.save"]` to a case
to enable **soft-trigger** scoring: a run passes if every listed string
appears in `result`, even when no `Read`/`view` tool-use fired. A case
passes if hard-trigger OR soft-trigger passes; the 2-of-3 threshold still
applies. Choose `answer_contains` strings that are authored in the skill
body and unlikely to appear from model training alone (SciTeX-specific
flags like `use_caller_path=True` are strong signals).

## Generic image (pulled from ghcr.io)

`docker pull ghcr.io/ywatanabe1989/scitex-agentic-test:latest` — built
and pushed by `scitex-agent-container/.github/workflows/publish-agentic-test-image.yml`
on every `v*` tag. Harness auto-pulls on first run if missing. Image
holds Node + claude CLI only — no baked skills/credentials. To build
locally (when editing the Dockerfile): `docker build -f scitex-agent-container/containers/Dockerfile.agentic-test
-t scitex-agentic-test:latest scitex-agent-container/containers`,
then `SCITEX_DEV_AGENTIC_DOCKER_IMAGE=scitex-agentic-test:latest`.

## Isolation model — what "newbie" means

**Skills-isolated, identity-shared.** Only the single `_skills/<pkg>/`
and `/tmp/newbie_creds.json` land inside; no other `~/.claude/` files
leak in. But the creds are a copy of YOUR `~/.claude/.credentials.json`
— the agent calls Claude API as your account (your usage / billing).
For true identity isolation, write a separate test token to a different
`/tmp/test_creds.json`. Mount is `:ro` so the container can't write
back. Prep: `install -m 644 ~/.claude/.credentials.json /tmp/newbie_creds.json`

## Two runtime modes (pick by purpose)

### Mode A — dev iteration (direct source mount)

Fastest feedback loop — edit the source `SKILL.md` and the next
`docker run` reflects it instantly. No export, no staging, no rebuild.
Mount each package's skill dir read-only:

```bash
docker run --rm \
  -v ~/proj/scitex-io/src/scitex_io/_skills/scitex-io:/home/agent/.claude/skills/scitex-io:ro \
  -v /tmp/newbie_creds.json:/home/agent/.claude/.credentials.json:ro \
  ghcr.io/ywatanabe1989/scitex-agentic-test:latest \
  -p "<query>" --output-format json --model claude-haiku-4-5 \
  --dangerously-skip-permissions
```

### Mode B — production test (pip install + export, canonical CI target)

Exercises the real install path — what a fresh user gets after
`pip install scitex-<pkg>`. Catches packaging bugs (missing `_skills/`
in the wheel, export script failures). Same `docker run` invocation as
mode A, but mount the *exported* skill dir
(`scitex-<pkg> skills export --dest /tmp/<staging>/.claude/skills --clean`)
instead of the raw source.

Reproducibility anchor for papers: record the generic image tag
(`scitex-agentic-test:<date>`) + either the mode-A source commit SHA
or the mode-B exported skill hash.

## MVP — Phase 1 (synthetic kv-lookup)

Harness-validation skill at
`scitex-agent-container/containers/skills/kv-lookup/SKILL.md`. Pushy
description enumerates trigger words (apple/banana/cherry/date/
elderberry); body has the lookup table. Measured 2026-04-23: **8/8
trigger + answer OK at $0.088 over 54 s** across 4 cases × 2 runs
(banana=12, cherry=42, elderberry=256, fig=neg-refusal).
`tool_uses: []` on some runs is expected — Claude Code auto-loads
small skill bodies from the description match without an explicit
`Read`. Layer-3 compliance still checks the answer content.

## Drop-in pytest per package

```python
# tests/test_skill_trigger.py
from scitex_dev._agentic_testing import make_skill_trigger_tests

test_skill_trigger = make_skill_trigger_tests(
    eval_path="tests/skill_evals/<pkg>.json",
    model="claude-haiku-4-5",
    backend="docker",          # or "host" for quick dev
)
```

Marker applied automatically — run only trigger tests:

```bash
pytest -m skill_trigger
```

## Writing the eval JSON

Copy from `examples/skill_eval_example.json`:

```json
{
  "version": 1,
  "evals": [
    {"id": "substantive-pos", "query": "<multi-step query ~80-200 chars>",
     "expected_skill": "scitex-io/SKILL.md", "complexity": "high"},
    {"id": "adjacent-neg",    "query": "<query near the skill's domain but outside its remit>",
     "expected_skill": null, "complexity": "low"}
  ]
}
```

Rules:

1. **Substantive, multi-step.** Simple one-step queries Claude answers
   from training without consulting any skill.
2. **Don't name the skill in the query.** That's a trivially-passing
   test that measures description quality = 0.
3. **Pair every positive with a near-adjacent negative.** Over-trigger
   is a bug equal in weight to under-trigger.
4. **One expected skill per case.** Multi-skill disambiguation is a
   separate test shape.

## Environment variables

| Var | Meaning | Default |
|---|---|---|
| `SCITEX_DEV_AGENTIC_BACKEND`            | `host` or `docker` | `host` |
| `SCITEX_DEV_AGENTIC_DOCKER_IMAGE`       | image tag | `scitex-agent-container:latest` |
| `SCITEX_DEV_CLAUDE_ACCOUNTS`            | `:`-separated HOME dirs for host rotation | `~` |

Credentials for the docker backend are mounted, not env'd. See the
overview for the mount recipe.

## Threshold, retries, model

- **Threshold: 2 of 3** runs per case must pass.
- **Retries: none** beyond the 3 runs — we measure trigger rate, not
  retry-to-success.
- **Haiku first**; upgrade to opus only if borderline cases need model
  capacity (rare for basic skill dispatch).

## POC / one-shot probe

```bash
python -m scitex_dev._agentic_testing_poc \
  --backend docker --prompt "What is the value of banana?"
```

Prints `duration_ms`, `cost_usd`, `cache_creation_tokens`,
viewed-paths. Good for sanity-checking a new skill before writing a
full eval JSON.

## Next — from MVP to real packages

Current MVP proves the harness works end-to-end on a synthetic skill
with a runtime-mounted catalog. To measure a real package: stage its
`SKILL.md` under `tests/skill_evals/<pkg>_stage/skills/<pkg>/`, author
`tests/skill_evals/<pkg>.json` (3–5 substantive queries + ≥1 adjacent
negative), drop in `tests/test_skill_trigger.py`, then run the trigger
tests for a baseline. MCP-enabled packages may need a derived image
`scitex-agentic-test-<pkg>:latest` with `RUN pip install scitex-<pkg>`
(keep the pip set tight — installing all of scitex takes >1 hour).
