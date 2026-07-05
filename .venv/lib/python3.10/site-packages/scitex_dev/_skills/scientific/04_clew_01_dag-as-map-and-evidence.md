---
description: |
  [TOPIC] Clew DAG — two modes of the same data structure
  [DETAILS] Conceptual framing for using `scitex-clew` in a research project. The same SHA-256-linked DAG is exposed in two modes — *map* (live, read-write, agents and authors navigate by it during build/exploration) and *evidence* (post-hoc, read-only, reviewers verify the minimal source-to-claim chain). Read this first when adopting Clew on any new project; the procedural playbook is in `04_clew_02_translation-playbook.md`. Use when explaining to collaborators what Clew "is", or when deciding which APIs to call (`add_claim`/`chain` vs `dag`/`rerun`).
tags: [scitex-scientific-clew-dag-as-map-and-evidence]
---

# Clew DAG — map (build) and evidence (publish)

`scitex-clew` exposes one SHA-256-linked DAG in two complementary modes.
The DAG itself is the same object on disk; the *use* differs by phase.

## The duality

| Mode | Audience | Direction | Phase | Operation |
|---|---|---|---|---|
| **Clew-DAG-as-map** | agents, authors | live, read-write | during build / exploration / debugging | forward execution **spins** hash-linked nodes; queries answer *what exists*, *what's verified*, *where it broke* |
| **Clew-DAG-as-evidence** | reviewers, regulators | post-hoc, read-only | at publication / audit | backward resolution **follows** parent-hash pointers from a claim to its sources, pruning exploratory branches → minimal evidence chain |

The evidence DAG is the **minimal sub-graph** of the map that
back-resolves from a published claim to its source files. The map is the
substrate; evidence is what you extract from the map for publication.

## Theseus metaphor

A clew is a ball of thread, the navigation aid Theseus used in the
Cretan labyrinth. The thread plays both roles:

- While **exploring** the labyrinth, the thread *maps* every chamber the
  explorer has visited and every passage they have hash-verified — this
  is the live DAG-as-map.
- On the way **out**, the thread *leads* from any conclusion back to the
  entrance through the shortest sequence of confirmed steps — this is
  the DAG-as-evidence.

> *A clew helps one escape the labyrinth; it does not abolish the labyrinth.*

The metaphor is not decorative — it is the operational shape of the API.

## Operational mapping to scitex-clew APIs

| Mode | Primary APIs | What they answer |
|---|---|---|
| **Map** | `@stx.session` (auto), `clew.add_claim`, `clew.list_runs`, `clew.status`, `clew.mermaid` | "What have I done?" "What inputs feed claim X?" "Which downstream nodes does this change invalidate?" |
| **Evidence** | `clew.chain`, `clew.dag`, `clew.verify_claim`, `clew.rerun_dag` | "Does this claim back-resolve to a source file?" "Is the recorded hash chain still consistent end-to-end?" "Re-execute the minimal chain and compare." |

Pre-publication: agents and authors use the **map** mode to assemble the
analysis. Pre-submission: a single `clew.dag(strict=True)` produces the
**evidence** mode — the manuscript's claim-bearing nodes either resolve
to sources or fail the validity gate.

## When to invoke each mode

- **Adopting Clew on an existing project**: start in *map* mode. Wrap
  scripts with `@stx.session`, route I/O through `stx.io`, register
  intermediate claims as you go. The DAG accumulates by side effect.
- **Reviewing a finished pipeline**: switch to *evidence* mode. Run
  `clew.chain(<claim_value>)` from each manuscript number and confirm
  the chain ends at a source file.
- **Debugging a hash mismatch**: use *map* mode introspectively —
  `clew.dag(strict=True)` returns the failing node + invalidated claims
  + still-valid claims. Fix upstream inputs; downstream claims
  re-verify automatically.
- **Demonstrating reproducibility to a reviewer**: hand them the
  *evidence* mode output (the rendered Mermaid DAG + the
  `clew.verify_claim` reports) — no code re-execution needed.

## Why this framing matters

A common confusion is treating Clew as a *post-hoc audit tool* — run it
once at submission, get a pass/fail, ship the paper. That misses the
point. The map mode is what makes the substrate productive *during*
research: the agent or author can ask the DAG what's missing, what's
inconsistent, what would change if a particular input updated, without
mentally re-tracing the analysis.

The evidence mode is what makes the same substrate *useful at submission*
— but it's free, because the map has already been built.

## Related

- [04_clew_02_translation-playbook.md](04_clew_02_translation-playbook.md) — universal agent prompt that operationalises both modes
- [04_clew_03_translation-template.md](04_clew_03_translation-template.md) — per-project translation template
- [04_clew_04_translation-notebook-delta.md](04_clew_04_translation-notebook-delta.md) — notebook-cohort delta (BixBench-style)
- [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md) — `@stx.session` and the `CONFIG` object
- `scitex-clew/_skills/scitex-clew/` — package-specific API and CLI references
