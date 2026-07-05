---
description: |
  [TOPIC] Development Skills Self Explain
  [DETAILS] .
tags: [scitex-general-development-skills-self-explain]
---

<!-- ---
!-- Tags: scitex-general, scitex-package, skills, self-explain, docs
!-- ---->

# Skills Self-Explain

## Concept

Skills are the single source of truth for what a SciTeX package does. The
README, the docs, the agent's "what is this for?" answer — they should all
derive from the same `_skills/<pkg>/` tree.

`scitex-dev skills self-explain <pkg>` mounts ONLY that package's skill
directory into a fresh Claude Code container (no other skills, no project
context, no auth baggage) and asks the agent three canonical questions.
The answers serve **two** purposes:

1. **Quality measure for the skills.** If a fresh agent — given nothing
   but the skills — can't say what the package is for, the skills need
   work. Vague answers are evidence of vague skills.
2. **Auto-generated README content.** Once the answers are good, they
   can be dropped straight into the README's "what does this package
   do?" / "Problem-Solution" / "Quick Start" sections, eliminating the
   "did we update the README too?" sync gap.

## The three canonical prompts

| # | Prompt name      | Question                                              |
|---|------------------|-------------------------------------------------------|
| 1 | `_PROMPT_WHAT_FOR`    | "What is this package for?" — one sentence.      |
| 2 | `_PROMPT_PROBLEMS`    | "What 3-5 problems does it solve?" — markdown table. |
| 3 | `_PROMPT_QUICK_START` | "Show the canonical Quick Start." — Python code block. |

The prompts live as module constants in
`scitex_dev._cli.skills._self_explain` so they are greppable and can be
overridden by callers if needed.

## Output schema

```json
{
  "package": "scitex-io",
  "what_for": "<one sentence>",
  "problems_solved": "| # | Problem | Solution |\n|---|---------|----------|\n| 1 | ... | ... |",
  "quick_start": "```python\nimport scitex.io as sio\n...\n```"
}
```

## How to invoke

```bash
# Default: 1 run per prompt, claude-haiku-4-5, JSON output
scitex-dev skills self-explain scitex-io

# Take the median of 3 runs per prompt (more robust, 3x cost)
scitex-dev skills self-explain scitex-stats --runs 3

# Use a stronger model
scitex-dev skills self-explain scitex-writer --model claude-sonnet-4-5
```

## When to re-run

- After editing any skill under `_skills/<pkg>/`
- Before tagging a release (catch skill drift early)
- When auditing a package whose README feels stale

## Cost considerations

Each invocation spends real Claude API credits on **your account**. The
container is configured with `ANTHROPIC_API_KEY`, not Claude Code plan
quota. Cost = `N_prompts × runs_per_prompt` API calls.

Order-of-magnitude (Haiku 4.5, single run per prompt):

| Runs | Calls | Approx cost (Haiku) |
|------|-------|---------------------|
| 1    | 3     | ~$0.01-0.03         |
| 3    | 9     | ~$0.05-0.10         |

Use `--runs 1` for routine drift checks; `--runs 3` only when the
content will be committed (e.g. README regeneration).

## Implementation

`self_explain` reuses `scitex_dev._agentic_testing._core.NewbieDockerRunner`
with `skills_mount` pointing at a temp directory shaped as
`<tmp>/.claude/skills/<pkg>/`. The mount is read-only, so the agent
genuinely sees only the curated skill files.

## Follow-ups (not in MVP)

- `scitex-dev readme regen <pkg>` — splice the answers into README
  region markers (e.g. `<!-- self-explain:what_for -->`).
- Cache the answers in `~/.scitex/dev/self_explain/<pkg>.json` so the
  README regen doesn't re-spend credits when nothing changed.
- A "median wins" reducer for `--runs > 1` (currently the multi-run
  path returns all answers; the caller picks).

<!-- EOF -->
