---
description: |
  [TOPIC] Scitexification Stage 4 — Reproducibility via Clew claims
  [DETAILS] Stage 4 of the 5-stage scitexification arc: final-mile
  assertions (the numbers in the abstract / conclusions / a figure
  caption) become registered scitex-clew claims, each evidence-bound by
  SHA-256 to the file that produced it; the results/output JSON is
  composed by iterating registered claims through `list_claims()` +
  `verify_claim()` and filtering on `source_verified`, never hand-written.
  A validity gate runs INSIDE the final stage so a broken evidence chain
  fails loud at its origin. Builds directly on the DAG made visible in
  stages 1–3.
tags: [scitexification, scitexification-clew]
---

# Stage 4 — Reproducibility via Clew claims

The evidence step. Every number the project *claims about the world* — an
accuracy, an effect size, a p-value, a figure's headline count — becomes
a **registered clew claim**, hash-bound to the file that produced it. The
DAG made visible in Stages 1–3 is what each claim walks back along; Stage
4 turns "trust me" into a verifiable `claim → output → … → source` chain.

> **What changes**: how final results are recorded (registered claims,
> not a hand-typed JSON).
> **What stays the same**: what you are claiming; your numbers.

## Stage 4.0 — reproduce the environment first (you can't ground what you didn't run)

A claim is only verifiable if a **real** output file backs it. When the
source ships a **pinned environment** that does not run in your default
interpreter — a `Dockerfile`, a saved model needing an old TensorFlow/CUDA,
a conda lock — the honest move is to **reproduce that environment and run
the real code**. Do **not** "estimate from the paper" or hand-code numbers:
that is the fabrication failure mode, and the validity gate /
`clew verify --strict` will reject it (no real `@stx.session` lineage).

If you run inside the SciTeX agent container with `nested_build` enabled
(quick check: `apptainer --version` works), reproduce the env *from your
workdir*:

```bash
export APPTAINER_TMPDIR=/tmp APPTAINER_CACHEDIR=/tmp/.apptainer-cache
# (a) PULL a pre-built published image — preferred when the source provides one
#     (e.g. a CodeOcean compute capsule names one in REPRODUCING.md, anonymously pullable):
apptainer build env.sif docker://<registry>/<published-image>:<tag>
# (b) OR BUILD the source's Dockerfile — convert it to a def (`Bootstrap: docker`
#     + a `%post` carrying the RUN/apt/conda/pip lines); %post runs as root:
apptainer build env.sif env.def
# then run the REAL code and read REAL outputs:
apptainer exec --bind data:/data --bind code:/code --bind "$PWD/results":/results \
  env.sif bash -lc 'cd /code && bash run'
```

What you **cannot** do: run **Docker**. There is no Docker daemon inside the
unprivileged container (and none is grantable). Use the apptainer path above
— `apptainer build docker://…` pulls the same OCI layers with no daemon, and
a Dockerfile-derived def builds under apptainer's rootless fakeroot.

If after honest effort you **cannot** reproduce it, **abstain** (the honest
null below) — a calibrated "I could not run this" is correct science, scored
as such, never as a wrong answer. Never substitute an estimate. Full
mechanism + limits: the `scitex-agent-container` skill (nested-apptainer
builds).

## Register, don't hand-write

The anti-pattern Stage 4 exists to kill: hand-writing
`results.json` / `claims.json`. A hand-written file drifts from the
evidence the data actually carries. Instead, **register** each claim and
**compose** the output by iterating the store:

```python
import scitex_clew as clew

# in the final stage, once per value-grounded claim:
clew.add_claim(
    file_path=str(claims_json),     # the DAG terminus (a real file)
    claim_type="value",
    line_number=i + 1,
    claim_value=str(answer),
    source_file=str(metrics_csv),   # the file the value came from
)

# compose the result by iterating + filtering — never by hand:
rows = [c for c in clew.list_claims(file_path=str(claims_json))
        if clew.verify_claim(c.claim_id).get("source_verified")]
```

`source_verified` means the `source_file`'s SHA-256 still matches what was
recorded at `add_claim` time. `chain_verified` (full mode only) additionally
means every intermediate hop was registered via `stx.io` — see "modes" below.

## The validity gate (run it INSIDE the final stage)

Fail loud, fail early — the gate lives in the agent's own final stage, not
in a launcher that checks afterwards:

```python
import scitex_clew as clew
listed = clew.list_claims(file_path=str(claims_json))
if len(listed) != len(registered):
    raise RuntimeError(f"clew DB has {len(listed)} claims, expected {len(registered)}")
bad = [(c.claim_id, c.source_file) for c in registered
       if clew.verify_claim(c.claim_id).get("source_verified") is not True]
if bad:
    raise RuntimeError(f"validity-gate failures — evidence chain broken: {bad}")
```

If grounding a value's `source_file` still fails after 3 attempts,
**downgrade that claim to honest null** (see below) rather than loop or
fake a path — inventing a hash-matching path is provenance fraud.

## Honest grounding (no silent omission)

The integrity contract from `00_playbook.md`, enforced in the schema:
every expected question/goal appears in the output as **one** of —

1. **value-grounded**: `{value, source}` — passes the gate above; or
2. **honest null**: `{value: null, reason: "<one-sentence proximal cause>"}`
   — *not* SHA-checked (no source to hash).

`len(claims) == n_expected` is the invariant. Silent omission is the bug:
a dropped question is indistinguishable from "tried, failed, and hid it".

## Two modes (mirror Stage 1)

- **Full mode**: `stx.io.save(..., symlink_to=...)` auto-registers each
  file node, so `clew.chain(source_file)` returns a non-empty run list and
  claims report `chain_verified: True`.
- **Minimal mode** (no `libgthread`): stdlib I/O + explicit
  `clew.add_claim(source_file=...)`; claims report `source_verified: True`
  but `chain_verified: False`. Both pass the gate; only full mode gives a
  chain-verified DAG. `scitex-clew` itself is zero-dep (stdlib + sqlite3),
  so minimal mode works on stripped containers.

## Worked example

```python
# BEFORE                                  # AFTER (stage 4)
results = {"accuracy": 0.91}              clew.add_claim(file_path=claims_json,
json.dump(results, open("out.json","w"))      claim_type="value", line_number=1,
                                              claim_value="0.91",
                                              source_file=metrics_csv)
                                          # then verify_claim gate + compose out.json
                                          # from list_claims — not by hand.
```

## Follow-up

- Full scitex-clew primitive surface (`add_claim`, `list_claims`,
  `verify_claim`, `chain`, `render_dag`/`generate_mermaid_dag`, validity
  semantics) → **`scitex-clew`'s own SKILL.md**.
- Clew-tracked / experiment-specific specialisations (evaluator-blind
  scoring, output/results schemas, completion signalling) →
  [`../04_clew_02_translation-playbook.md`](../04_clew_02_translation-playbook.md)
  and the `../04_clew_*` siblings. Read those after this chapter when
  working in a clew-tracked flow.
- Stages 1–3 are the precondition: the file nodes those stages created are
  the leaves each claim walks back to.

See also: [`00_playbook.md`](00_playbook.md) (honest-grounding norm),
[`SKILL.md`](SKILL.md),
[`../04_clew_01_dag-as-map-and-evidence.md`](../04_clew_01_dag-as-map-and-evidence.md).
