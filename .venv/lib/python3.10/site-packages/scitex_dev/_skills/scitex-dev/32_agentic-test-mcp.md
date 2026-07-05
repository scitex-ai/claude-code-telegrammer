---
description: |
  [TOPIC] Agentic Test Mcp
  [DETAILS] STALE (2026-05-02) — superseded by the standalone newb package. The scitex-agentic-test base image referenced here was retired from scitex-agent-container. Kept as a draft sketch; re-author once sac's claude-agent-sdk redesign lands.
tags: [scitex-dev-agentic-test-mcp]
---

> **⚠ STALE — 2026-05-02.** The `scitex-agentic-test` base image
> referenced below was removed from scitex-agent-container. MCP
> evaluation will be reframed against [newb](https://github.com/ywatanabe1989/newb)
> and the upcoming claude-agent-sdk-based sac redesign. Do not implement
> this draft as written.

# 32_agentic-test-mcp

Layer 2+3 for MCP servers. **Draft design** — the harness is wired for
skill trigger tests (see [31_agentic-test-skills.md]) but not yet for
MCP evaluation. This leaf records the planned architecture so the next
implementation pass has a spec.

## Four-layer mapping for MCP

| Layer | Skill version | MCP version |
|-------|---------------|-------------|
| 1. Unit        | checklist §1–§4 | FastMCP + pytest — call the tool in-memory, assert return |
| 2. Trigger     | did Claude view SKILL.md? | did Claude call the expected MCP tool? |
| 3. Compliance  | LLM-as-judge on output | did Claude call it with correct args, in correct sequence? |
| 4. Outcome     | user goal achieved | MCP-side state is what the user asked for |

## Shared with skills — the substrate

Same `scitex-agentic-test:latest` newbie-docker image used in Layer 2
for skills. Same `claude -p` invocation. Same `.credentials.json`
mount. The parse step on the JSON envelope differs: instead of
collecting `Read`/`view` paths, collect `tool_use` blocks whose `name`
matches an MCP tool name (e.g. `mcp__scitex__io_load`).

## Planned data shapes (draft)

```python
@dataclass
class McpEvalCase:
    id: str
    query: str
    expected_tools: list[str]      # sequence of expected tool names
    expected_args_match: dict | None  # optional arg-predicate per step
    forbidden_tools: list[str] = field(default_factory=list)
    complexity: str = "high"

@dataclass
class McpTriggerResult:
    case: McpEvalCase
    tool_calls_per_run: list[list[ToolCall]]
    sequence_ok_per_run: list[bool]    # did order match?
    args_ok_per_run: list[bool]        # did args match predicate?
```

## Planned pytest surface

```python
# tests/test_mcp_trigger.py  (not yet implemented)
from scitex_dev._agentic_testing import make_mcp_trigger_tests

test_mcp_trigger = make_mcp_trigger_tests(
    eval_path="tests/mcp_evals/<pkg>.json",
    mcp_server="scitex-<pkg>-mcp",    # resolved into container config
    model="claude-haiku-4-5",
)
```

Marker: `@pytest.mark.mcp_trigger` (paired with `skill_trigger` so
`pytest -m "skill_trigger or mcp_trigger"` runs all agentic tests).

## MCP server in the container

Unlike skills (files only), MCP needs a running server accessible to
the in-container Claude process. Two plausible shapes:

- **Bundled**: the MCP server binary is inside the image, started via
  `uv run <pkg>-mcp-server` as a sidecar; Claude's `mcp_servers`
  config points at `stdio`-launching that command. Self-contained.
- **Host-side**: MCP runs on the host; container joins via
  `--network host` and Claude points at the host socket. Breaks the
  clean-slate property — avoid unless truly necessary.

Prefer bundled. Publish one image per MCP server under test
(`scitex-agentic-test-<pkg>-mcp:latest`), same `FROM` base, with
`pip install scitex-<pkg>` and the MCP server auto-registered via a
baked `~/.claude/.claude.json` fragment or `--mcp-config` flag.

## Related upstream frameworks

`mcp-eval` (PyPI: `pytest-mcp`) is the reference point. Same goal —
task-based agent evaluation with built-in metrics (latency, token
usage, cost, tool-call sequence checks, plan-efficiency via
LLM-as-judge). Once the SciTeX version is implemented, we should try
to stay API-compatible so their eval sets can feed ours.

## Honest status

- **Not implemented yet.** Above is spec, not code.
- Hooking the parse logic onto the existing `_agentic_testing` runner
  is the natural next step — same JSON, different walker.
- The per-package author interface (`make_mcp_trigger_tests(...)`)
  should mirror the skills version so per-package test files look
  near-identical.

## References

- [Anthropic MCP spec](https://modelcontextprotocol.io/)
- `mcp-eval` upstream (AgentOps) for API shape
- `scitex-agent-container/config/templates/newbie-docker.yaml` — reference
  newbie agent config re-used for the MCP variant
