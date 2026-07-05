---
description: |
  [TOPIC] Research Project Root
  [DETAILS] Repo-root rules for a SciTeX *research project* (analysis pipelines, experiments) — what's allowed at the root (README, LICENSE, pyproject.toml even though research projects aren't shippable, Makefile thin dispatcher, .gitignore), forbidden top-level dirs (`mgmt`, `project_management`, `references`, `htmlcov`, top-level `assets`, `.playground`), the hidden directories `./.dev/` (scratch) and `./.old/` (hidden archive) and `./.scitex/<pkg-short>/` (project-scope scitex state — see [01_ecosystem/06_dot_scitex_directory.md](../general/01_ecosystem/06_dot_scitex_directory.md)), the production-ready-always invariant, anti-patterns, and a project-handoff checklist.
tags: [scitex-scientific-research-project-project-structure-root]
---

# Repo Root — Research Project

The repo root contains exactly the files that **must** be there. Everything else lives in a subdirectory.

> Building a *pip-installable package* instead of a research project? See [`../general/02_package/01_project-structure-root.md`](../general/02_package/01_project-structure-root.md).
>
> Sub-leaves of this section: [`./scripts`](02_research-project_02_project-structure-scripts.md) · [`./config + ./data`](02_research-project_03_project-structure-config-and-data.md) · [`./scripts/makefile`](02_research-project_04_project-structure-makefile.md) · [`./examples`](02_research-project_05_project-structure-examples.md) · [`./tests`](02_research-project_06_project-structure-tests.md)

## What's allowed at the repo root

| File | Purpose |
| :--- | :--- |
| `README.md` | Primary entry point |
| `LICENSE` | License text |
| `pyproject.toml` | Even research projects use `pyproject.toml` for dev-deps + Makefile-driven tooling (no `setup.py`, `requirements.txt`) |
| `Makefile` | Thin dispatcher; logic in `./scripts/makefile/` (see [02_research-project_04_project-structure-makefile.md](02_research-project_04_project-structure-makefile.md)) |
| `.gitignore`, `.gitattributes` | VCS hygiene |
| `CLAUDE.md` (optional) | AI-agent context for this repo |

Everything else belongs in a subdirectory. **Do not create new top-level directories** without strong reason.

## Forbidden top-level dirs

Same set as packages — see [`../general/02_package/01_project-structure-root.md`](../general/02_package/01_project-structure-root.md#forbidden-top-level-dirs):
`./mgmt/`, `./project_management/`, `./references/`, `./htmlcov/`, top-level `./assets/`, `./.playground/` (collapsed into `.dev/`).

## `./docs` — human-facing documentation

- README is the entry point; deeper docs go here (`./docs/installation.md`, `./docs/methods/<topic>.md`).
- `./docs/_build/` — generated docs; gitignored.
- `./docs/assets/` — figures, screenshots, diagrams referenced from README.
- `./docs/to_claude/` — agent context files. **Must be gitignored** — local-machine artifacts, not part of the shipped repo.
- `./GITIGNORED/` — catch-all file-based scratch channel.

## Hidden / scratch directories

| Dir | Use |
| :--- | :--- |
| `./.dev/` | Single scratch space — sandbox tests, parking-lot ideas, half-baked experiments. Gitignored. Organize by category subdir (`./.dev/<category>/`). **Promote** valuable code out (`→ scripts/`, `examples/`) or **prune** periodically. |
| `./.old/` | **Hide, don't delete** — keeps git history clean while removing visual noise. Acceptable to clear in a dedicated cleanup commit once nothing references it. |
| `./.scitex/<pkg-short>/` | **Project-scope SciTeX state.** Each scitex-* package gets its own subdir for project-scoped runtime (e.g. `./.scitex/dev/runtime/` for scitex-dev's per-project state, `./.scitex/io/cache/` for scitex-io's project cache). Resolution chain and full layout are documented in [`../general/01_ecosystem/06_dot_scitex_directory.md`](../general/01_ecosystem/06_dot_scitex_directory.md). Gitignored by default; some packages may track config files inside it. |
| `./.venv/` | **Project-scope Python virtualenv** (created by `python -m venv` or `uv venv`). Always gitignored. Sourced by `.envrc` (or manual `source .venv/bin/activate`). One venv per project — never share across projects. |
| `./.envrc` | **direnv-managed per-project environment.** Loaded automatically when `cd` into the project (after `direnv allow`). Typical contents: `source .venv/bin/activate`, `export PROJECT_ROOT=$PWD`, project-local `PATH` additions. Tracked under git (no secrets); local overrides go in `.envrc.local` (gitignored). |
| `./.env` | **App-runtime env file** (`KEY=VALUE` lines, no shell). Read by frameworks like Docker Compose, dotenv libraries, MCP servers. Distinct from `.envrc` (which is shell). Default: gitignored if it ever holds secrets; safe to track if literal-only. |

## Discoverable top-level symlinks

`.scitex/<pkg>/` directories are conventionally hidden but they often contain the artefacts a user/reviewer wants first. **Surface each one via a one-word top-level symlink** so users don't need to know the `.scitex/` plumbing.

| Symlink | Target | What it surfaces |
|---|---|---|
| `./paper` | `./.scitex/writer/` | manuscript build tree (latex sources, claims, figures) |
| `./clew` | `./.scitex/clew/` | verification DB + claim chain |
| `./agents` | `./.scitex/agent-container/agents/` | project-local sac agent yamls |

Rules:

- **Symlink, don't copy** — `.scitex/<pkg>/` remains canonical; `./<word>` is the discoverable entry.
- **One-word names** — keep the top-level dir count small (`paper`, not `manuscript_build`).
- **Tracked under git** — symlinks are tiny; tracking ensures fresh clones get the same discoverability.

## Top-level dirs for runtime / deployment

For research projects that ship a container or run on HPC, separate the *build artefacts* from the *cluster submission scripts*:

| Dir | Contents | Examples |
|---|---|---|
| `./containers/` | Container build (one image, used by any cluster) | `clew.def` (Apptainer), `Dockerfile`, `build.sh`, `constraints.txt` |
| `./runtime/<cluster>/` | Cluster-specific submission | sbatch wrappers, sac/airflow yamls, pre-agent shims |
| `./scripts/` | Pure code — no cluster knowledge | clew_demos, scitex_packages, cohorts |

Rules:

- **One image, many clusters** — `./containers/` is generic; cluster-specific things go to `./runtime/<cluster>/`.
- **Cluster name in path, not filename** — `runtime/spartan/exp_01_overhead_sbatch.sh`, not `runtime/exp_01_overhead_spartan_sbatch.sh`.
- **`./scripts/` knows nothing about cluster** — keep `@stx.session` scripts portable; cluster wrappers in `runtime/` invoke them with the right env.

## Production-ready always

The main branch must be runnable **today**:

- Half-finished experiments live on a `feature/<verb>-<object>` branch.
- Obsolete files hidden under `.old/`, not littering visible paths.
- `./examples/` runs cleanly start-to-finish.
- Tests pass on `main`.
- README accurately describes current state, not aspirational state.

## Anti-patterns

- **Hardcoded parameters in scripts** — bypasses the `direct → CONFIG → env → default` chain (see [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md)). Same value gets re-defined in three places, drifts.
- **Run outputs committed under `./data/`** — pollutes inputs with derived artefacts. Use `SDIR_OUT/` instead (see [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md)).
- **`./scripts/` that doesn't mirror `./tests/scripts/`** — coverage analysis becomes manual; renames break test discoverability.
- **Examples without `_out/`** — readers can't see what the demo produces.
- **`.dev/` with no categorization** — devolves into a junk drawer.
- **`.old/` that grows forever** — prune archives older than two release cycles.
- **Tracking `./.scitex/<pkg>/runtime/` artefacts** — those are session-unique; they belong gitignored.

## Pre-release / project-handoff checklist

- [ ] Every `scripts/.../*.py` has a corresponding `tests/scripts/.../test_*.py`
- [ ] Every example has a tracked `_out/` and `tests/examples/test_*.py`
- [ ] `./config/*.yaml` covers every parameter consumed by `./scripts/`
- [ ] `./data/` symlinks point at canonical sources; large files gitignored
- [ ] `./.scitex/` entries match the per-package conventions in `01_ecosystem/06_dot_scitex_directory.md`
- [ ] No half-finished work outside a `feature/*` branch
- [ ] No top-level files outside the allowed-at-root list
- [ ] `.dev/` has only categorized subdirs; nothing rotted >1 quarter
- [ ] `.old/` doesn't dominate any directory listing
- [ ] README reflects current behavior, not aspirational
- [ ] `make ci-local` (or equivalent) passes from a clean clone
