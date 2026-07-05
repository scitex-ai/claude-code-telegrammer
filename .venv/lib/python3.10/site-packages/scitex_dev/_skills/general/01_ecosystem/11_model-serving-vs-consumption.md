---
description: |
  [TOPIC] Model-serving vs model-consumption — the package responsibility boundary.
  [DETAILS] LLM SERVING (stand up a vLLM+LiteLLM endpoint; the multi-provider client) lives in scitex-genai; agent-runtime CONSUMPTION lives in scitex-agent-container (sac) via ProviderSpec base_url. Contract = an HTTP endpoint (OpenAI/Anthropic-compatible), NEVER a Python import — the two packages stay completely decoupled (neither imports the other).
tags: [scitex-general-ecosystem-model-serving-vs-consumption]
---

# Model-serving vs model-consumption

## The split

- **SERVING → scitex-genai**: the multi-provider LLM client (`llm/`:
  Anthropic / OpenAI / DeepSeek / Google / Groq / Llama / Perplexity +
  `genai_factory` + `cost`), the model-serving recipe / CLI (vLLM on
  HPC), the LiteLLM Anthropic-compat shim config. "How to stand up +
  talk to a model."
- **CONSUMPTION → scitex-agent-container (sac)**: `ProviderSpec` points
  an agent's `ANTHROPIC_BASE_URL` / `base_url` at any compatible
  endpoint. "How an agent uses a model." sac does NOT own serving.
- (There is **no** separate `scitex-ai` package — abandoned
  factor-out; the LLM client lives in `scitex-genai/llm/`.)

## Contract is HTTP, not import

Completely decoupled — neither imports the other. scitex-genai produces
an endpoint URL; sac consumes a `base_url` string.

- No `import scitex_genai` in sac.
- No `import scitex_agent_container` in genai.
- Only the URL + token cross the boundary (runtime config, **not** a
  build dep).

Buys:

- Serving runs anywhere (HPC / local / cloud / 3rd-party).
- No version coupling between the two packages.
- No import cycle.

## Details live elsewhere

The serving recipe's gory details (CUDA / TP / vLLM pitfalls, LiteLLM
shim config) belong in scitex-genai's own `_skills/`, not here. This
leaf is only the **cross-package boundary rule**.

## Worked example (clew / Qwen-on-Spartan)

scitex-genai stands up vLLM (OpenAI-compat backend) behind LiteLLM
(Anthropic-compat front) on a Spartan H100. The runner exports
`ANTHROPIC_BASE_URL=http://127.0.0.1:4000`; sac's `ProviderSpec` gets
only that URL + token.

Topology:

```
capsule / runner  →  LiteLLM (Anthropic-compat front)  →  vLLM (OpenAI-compat backend)
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^      ^^^^^^^^^^^^^^^^^^^^^^^^^^^
                     scitex-genai stands this up.          scitex-genai stands this up.

                     sac sees: base_url=http://127.0.0.1:4000 + token. Nothing else.
```

One `base_url`; neither package imports the other.
