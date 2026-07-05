---
description: |
  [TOPIC] Interface Http Api A2A Pattern
  [DETAILS] A2A (Agent-to-Agent) JSON-RPC protocol — used only by scitex-agent-container. Agent-protocol-specific by design (tasks, streaming replies, AgentCard discovery); not generalizable to functional services like audio playback or paper fetching. Documented here so contributors recognize the pattern but do NOT replicate it for non-agent packages.
tags: [scitex-general-interface-http-api-a2a-pattern]
---

# A2A — Specialty Pattern for Agent Packages

> **Important: this pattern is one-off, not ecosystem-wide.** It exists because scitex-agent-container is an agent-host, and A2A is the open protocol agent hosts speak to each other. Don't replicate A2A in functional services (scitex-audio, scitex-cloud, scitex-scholar) — wrong fit, would over-engineer.

## What A2A is

**A2A (Agent-to-Agent)** is an open JSON-RPC 2.0 protocol for agent communication. Not SciTeX-specific — defined by an external SDK. scitex-agent-container implements it natively.

Spec primitives:

| Concept | What it is |
|---|---|
| **AgentCard** | Metadata document at `/.well-known/agent.json` describing the agent's capabilities |
| **SendMessage** | Synchronous request/response — caller sends a message, receives a reply |
| **SendStreamingMessage** | SSE (Server-Sent Events) stream — caller sends a message, receives chunked replies |
| **GetTask** / **CancelTask** | Long-running task lifecycle — submit → poll → reply / cancel |
| **Task state machine** | `SUBMITTED → WORKING → COMPLETED` (or `FAILED`, `CANCELED`) |

## Endpoints (current scitex-agent-container)

```
GET  /.well-known/agent.json           # fleet AgentCard
GET  /v1/agents/                        # list agents
GET  /v1/agents/<name>/.well-known/agent.json  # per-agent card
POST /v1/agents/<name>                  # JSON-RPC dispatch (SendMessage, SendStreamingMessage, GetTask, CancelTask)
GET  /v1/agents/<name>/_active          # task snapshot (SAC observability — not in A2A spec)
```

## Request shape (JSON-RPC 2.0)

```json
{
  "jsonrpc": "2.0",
  "id": "request-1",
  "method": "SendMessage",
  "params": {
    "message": {
      "message_id": "m1",
      "role": "ROLE_USER",
      "parts": [{"text": "hello"}]
    }
  }
}
```

Response: protobuf-serialized Task with `status.message.parts[0].text` carrying the reply.

## Why this is NOT for general SciTeX HTTP packages

A2A's mental model is **agent as a long-lived stateful conversation partner** — there are tasks with lifecycles, role-based message arrays, streaming chunked replies, AgentCard discovery, capability negotiation.

Functional services (scitex-audio's TTS, scitex-cloud's paper lookup) have a fundamentally different model: **stateless RPC**. Caller asks "convert this text to speech" → server replies with audio + metadata. There's no task to poll, no role-based dialogue, no capability negotiation.

Trying to retrofit A2A onto a functional service:

- Wraps every call in `Task` lifecycle ceremony (submit → poll → result) — overhead with no benefit.
- Forces the AgentCard projection (capabilities, model name, role) onto endpoints that just want "give me citations for DOI X".
- Replaces FastAPI's auto-OpenAPI with hand-rolled A2A discovery — losing developer DX.
- Locks the package to a single SDK that's still evolving.

REST + OpenAPI is the right shape for functional services. A2A is the right shape for **agents talking to agents.**

## Implementation reference

scitex-agent-container is the canonical implementation:

- **Server file**: `~/proj/scitex-agent-container/src/scitex_agent_container/a2a/_server.py`
- **Framework**: Starlette (forced — A2A SDK requires it)
- **Launch**: `sac a2a serve <agent-yamls> --host <host> --port <port>` (the SAC-specific CLI subcommand, not the canonical `<cli> http start`)
- **Per-agent config**: YAML files declare handler type (echo / claude_cli / exec) + model + capabilities

## When this leaf will grow into a directory

If/when more SciTeX packages expose agent-protocol surfaces, this leaf gets promoted:

- A future `scitex-orchestra` or similar agent-coordination package.
- A SciTeX-side wrapper exposing a research project's session as an agent.

In that case, `08_a2a-pattern.md` becomes `08_a2a/` with multiple files (overview, AgentCard format, task lifecycle, integration with `<cli> a2a serve`). Today, one leaf is enough.

## What contributors should take away

1. **A2A exists in scitex-agent-container.** Recognize it when you see `/.well-known/agent.json` or `JSON-RPC` in a SciTeX package — it's not a typo, it's A2A.
2. **Don't add A2A to other packages.** If you want "agentic" exposure of, say, scholar's paper-fetching capabilities, prefer MCP tools (`scholar_fetch_papers`) — that's exactly what MCP solves.
3. **REST is the default**, and FastAPI is the default REST framework. A2A is a specialty, not a starting point.

## See also

- [02_framework-choice.md](02_framework-choice.md) — why Starlette is allowed only when an SDK forces it (A2A is the named exception)
- [03_interface/03_mcp/](../03_mcp/) — for "expose package capabilities to AI agents" the answer is usually MCP, not A2A
