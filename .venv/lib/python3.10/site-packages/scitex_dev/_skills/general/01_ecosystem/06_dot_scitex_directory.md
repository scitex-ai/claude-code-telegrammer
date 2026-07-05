---
description: |
  [TOPIC] Ecosystem Local State Directories
  [DETAILS] Canonical filesystem layout for every scitex-* package's local state — config, logs, caches, PID files, workspace dirs. Two roots (`<project>/.scitex/<pkg-short>/` and `~/.scitex/<pkg-short>/`), project overrides user, always via PathManager.
tags: [scitex-general-ecosystem-local-state-directories]
---

# Local State Directories — Canonical Layout

Every `scitex-*` package that writes anything to disk — config, logs, caches, PID files, databases, workspace dirs — must put it under exactly one of two roots. Same dirname at both scopes, project overrides user, mirrors Claude Code's `~/.claude/` vs `<project>/.claude/`.

## 1. The two roots

Every scope carries two parallel trees — one **tracked** (rules / config the team commits) and one **runtime-only** (outputs / logs / caches that must not enter git):

| Precedence | Scope | Root | Example (`scitex-scholar`) | Tracked by git? |
|---|---|---|---|---|
| higher | **Project (tracked)** | `<project-root>/.scitex/<pkg-short>/` | `./.scitex/scholar/` | Yes — config.yaml, custom dicts, skill bundles |
| higher | **Project (runtime)** | `<project-root>/.scitex/<pkg-short>/runtime/` | `./.scitex/scholar/runtime/` | No — only `.gitkeep` + `README.md` committed |
| lower | **User (tracked)** | `~/.scitex/<pkg-short>/` | `~/.scitex/scholar/` | Yes (inside dotfiles repo, if the user versions their home) |
| lower | **User (runtime)** | `~/.scitex/<pkg-short>/runtime/` | `~/.scitex/scholar/runtime/` | No |

**Project scope always wins.** A package reads project-local state if present and only falls back to the user root when the project file does not exist. CLI flags and env vars override both — see §3.

### The `runtime/` subdirectory

Every `<pkg-short>/` root **MUST** contain a `runtime/` subdirectory. This is where the package writes everything that is re-creatable from config + source: logs, PID files, cached downloads, temporary workspaces, SQLite databases, dashboard state, etc.

`runtime/` is intentionally ignored by git. Each package ships two seed files and nothing else:

```
<pkg-short>/runtime/
├── .gitkeep        # Committed so the directory exists in fresh clones
└── README.md       # Committed, one paragraph explaining what lives here
                    #   and pointing at the local-state-directories skill
```

The package's `.gitignore` contains a single line that excludes everything *except* those two files:

```gitignore
# <project-root>/.gitignore (or a nested one inside the package root)
.scitex/*/runtime/*
!.scitex/*/runtime/.gitkeep
!.scitex/*/runtime/README.md
```

Rationale: the dir must exist on first clone (so `PathManager` doesn't have to `mkdir` and accidentally expose permission bugs), but its *contents* must never leak — they are per-host, per-run, often large, and sometimes sensitive. Seeing `runtime/` appear in a `git status` is an immediate signal that something wrote where it shouldn't, or that `.gitignore` was not set up.

### `.scitex/dev/config.yaml` — tracked, not gitignored

The audit-tool config (`<repo>/.scitex/dev/config.yaml` — root
whitelist for `audit-project`) MUST travel with the repo, otherwise CI
applies a different whitelist than local and audit results diverge
mysteriously. Use file-level exclusion under `.scitex/` so the
negation rule applies (a `.scitex/` dir-level exclusion blocks
negation):

```gitignore
# <project-root>/.gitignore
.scitex/*
!.scitex/dev/
.scitex/dev/*
!.scitex/dev/config.yaml
```

Incident 2026-05-11: a scitex-io codecov.yml PS-103 violation kept
firing in CI even after local whitelist was added, because the entire
`.scitex/` directory was gitignored and the negation never reached the
config file.

## 2. `<pkg-short>` — prefix-stripping rule

`<pkg-short>` is the package name with the `scitex-` prefix removed. Packages that don't carry the prefix use their name as-is.

| Package (pip name) | `<pkg-short>` | Local root |
|---|---|---|
| `scitex-dev` | `dev` | `~/.scitex/dev/` |
| `scitex-scholar` | `scholar` | `~/.scitex/scholar/` |
| `scitex-orochi` | `orochi` | `~/.scitex/orochi/` |
| `scitex-clew` | `clew` | `~/.scitex/clew/` |
| `scitex-cloud` | `cloud` | `~/.scitex/cloud/` |
| `scitex-writer` | `writer` | `~/.scitex/writer/` |
| `scitex-linter` | `linter` | `~/.scitex/linter/` |
| `figrecipe` | `figrecipe` | `~/.scitex/figrecipe/` |
| `crossref-local` | `crossref-local` | `~/.scitex/crossref-local/` |
| `openalex-local` | `openalex-local` | `~/.scitex/openalex-local/` |

## 3. Precedence chain (highest first)

Applies uniformly to config file resolution; packages may extend it to state files when user overrides are sensible.

| # | Source | Example |
|---|---|---|
| 1 | CLI flag | `--config <path>` |
| 2 | Env var | `$SCITEX_<PKG>_CONFIG` |
| 3 | Project scope | `<project>/.scitex/<pkg-short>/config.yaml` |
| 4 | User scope | `~/.scitex/<pkg-short>/config.yaml` |

**Note on `$SCITEX_DIR`.** `SCITEX_DIR` is *not* a step in this chain — it **transforms the meaning of the user-scope root** (step 4). Setting `SCITEX_DIR=/mnt/fast-ssd/scitex` makes `~/.scitex/<pkg-short>/` resolve to `/mnt/fast-ssd/scitex/<pkg-short>/` everywhere. See §6.

## 3.5. Auto-creation: lazy mkdir, never via pip-install hooks

`pip install <pkg>` must **not** create `~/.scitex/<pkg-short>/` or any
of its sub-directories. Reasons:

1. Modern Python packaging (`pyproject.toml` + hatchling/setuptools)
   has no clean post-install hook; using setuptools `cmdclass` to
   bolt one on is fragile and breaks `pip install --user` /
   wheel-only installs.
2. CI runners and container builds run `pip install` in fresh
   environments; touching `~/.scitex/` there is unwanted side-effect
   pollution. Wheels should be inert.
3. `$SCITEX_DIR` relocation (§6) breaks if the package hardcodes
   `~/.scitex/...` at install time instead of resolving at runtime.

**Required pattern**: every code path that writes inside
`~/.scitex/<pkg-short>/` calls `mkdir(parents=True, exist_ok=True)`
on the immediate parent before writing. `PathManager` (§7) bakes this
in. A separate `<pkg> init` command may exist for users who want an
explicit "seed everything now" step, but it is never the ONLY way to
populate the directory.

```python
# YES — lazy, $SCITEX_DIR-aware, idempotent
def _ensure_cache_dir() -> Path:
    p = path_manager.get_cache_dir()  # resolves SCITEX_DIR / scope chain
    p.mkdir(parents=True, exist_ok=True)
    return p

# NO — install-time side effect, no $SCITEX_DIR awareness
# in setup.py / pyproject.toml [tool.hatch.build.hooks]
def post_install():
    Path("~/.scitex/scholar/cache").expanduser().mkdir(parents=True, exist_ok=True)
```

The `runtime/.gitkeep` and `runtime/README.md` seed files (§4b) ship
inside the **wheel** under `src/<import>/templates/runtime/` and are
materialised by `PathManager` on first use, not by an install hook.

**Audit — `PS-146 local-state-pip-install-side-effect`**: parses
`pyproject.toml` for hatch `[tool.hatch.build.hooks.<name>]` entries
whose hook script contains a `Path.home() / .scitex/...` mkdir, and
flags setuptools `cmdclass` overriding `install`/`develop`. Severity
`E` (hard fail) — the rule is unambiguous and the fix is mechanical.

## 4. What goes where

The package root splits into **tracked** (top-level) and **runtime** (under `runtime/`). The split is the same at both project and user scope.

### 4a. Tracked at the root (`<pkg-short>/`)

Intent: declarative inputs — things the team commits and reviews.

| File / subdir | Purpose |
|---|---|
| `config.yaml` | Primary config (canonical name — always `config.yaml`, never `<pkg>_config.yaml`) |
| `cli-audit-dict.yaml` | Per-scope linter custom dict (see `03_interface/02_cli/07_audit-cli.md` §1d) |
| `shared/skills/<pkg>-private/` | Private skill bundle (see `03_interface/04_skills/06_public-vs-private.md`) |
| `runtime/.gitkeep` | Marker so the runtime dir exists in fresh clones |
| `runtime/README.md` | One-paragraph notice explaining why `runtime/` is empty |

### 4b. Runtime-only (`<pkg-short>/runtime/`)

Intent: regenerable outputs — things each host / each run writes for itself, never to be committed.

| File / subdir | Purpose |
|---|---|
| `dashboard.log`, `*.log` | Logs |
| `dashboard.pid`, `*.pid` | PID files for background services |
| `cache/` | Derived / regenerable data |
| `workspace/` | Long-lived package-specific scratch (browser profiles, build outputs) |
| `*.db`, `*.sqlite` | Small embedded DBs (larger ones may relocate with `SCITEX_DIR`) |
| `export/` | Outputs of `scitex-dev skills export` and similar one-shot generators |
| `containers/` | Per-package container images (`*.sif`, `*.tar`). Large, per-host, regenerable from the `*.def` source under §4a. Never peer-rsync'd; gitignored under `runtime/`. |
| `bin/` | Host-specific built wrappers / launcher scripts (e.g. ones that hardcode the resolved overlay path). The **shipped, tracked** wrapper sources live at `<pkg-short>/bin/` under §4a — see the footnote below. |

Subdirectory layout within `runtime/` is up to each package, but **no per-package state may live outside its own root**.

> **`containers/` + `bin/` — `~/.scitex/<pkg>/{containers,bin}` ecosystem convention.** Per the cross-package agreement (Task #29 on the lead board): every package that ships an Apptainer / Singularity image standardises on `<pkg-short>/containers/*.sif` (under `runtime/`, this row) for the *built* image, and `<pkg-short>/bin/<verb>_<noun>.sh` for the *source* wrappers (tracked, see §4a). The split makes peer-rsync of `~/.scitex/` carry exactly the bin scripts (small, version-controllable) without dragging the multi-gigabyte container blobs (rebuildable from the `*.def`). See §4d for a worked example of what this looks like under a dotfiles-tracked `~/.scitex/`.

### 4c. Interactive REPL output cache (`runtime/cache/`)

Packages that auto-route user file output based on caller context (the
canonical example is `scitex_io.save()`) hit a special case when the
caller is an interactive REPL, IPython kernel, or `python -i` — there
is no script file to anchor a sibling `_out/` directory to. The
convention adopted 2026-05 is to write to:

```
$SCITEX_DIR/<pkg-short>/runtime/cache/<path>
```

defaulting to `~/.scitex/<pkg-short>/runtime/cache/<path>` when
`$SCITEX_DIR` is unset.

**Why under `runtime/cache/`** — these writes are regenerable, not
configuration, and they pollute fast (every interactive `save()`
produces a file). `cache/` is the explicit ephemeral bucket per §4b.

**Why honour `$SCITEX_DIR`** — interactive output volume can be large;
relocating the whole user-scope tree with `SCITEX_DIR=/mnt/fast-ssd/scitex`
must also relocate the REPL cache.

**Required pattern** in source code:

```python
import os as _os

def _interactive_cache_dir(pkg_short: str) -> str:
    base = _os.environ.get(
        "SCITEX_DIR",
        _os.path.join(_os.path.expanduser("~"), ".scitex"),
    )
    sdir = _os.path.join(base, pkg_short, "runtime", "cache")
    _os.makedirs(sdir, exist_ok=True)   # lazy mkdir per §3.5
    return sdir
```

**Reference implementation:** `scitex_io._save.save()` (the IPython /
`<stdin>` / `env_type in {"ipython", "interactive"}` branch). Pattern
applies to any future package that auto-routes outputs based on caller
context — e.g., a hypothetical `scitex_plt.save_fig()` should follow
the same rule and write to `~/.scitex/plt/runtime/cache/` when called
interactively.

This is distinct from `~/.scitex/<pkg-short>/cache/` (without `runtime/`),
which §5 forbids — the canonical bucket is always under `runtime/`.

### 4d. Worked example — dotfiles-tracked `~/.scitex/`

The split is most visible (and most easily understood) when the user
puts their **home directory under `git`** and tracks a curated subset
of `~/.scitex/` inside that dotfiles repo. The tracked subset is the
**CONFIG** layer (shared across that user's machines); everything
under `runtime/` (per §4b) stays gitignored and is regenerated on each
host. This subsection shows what the split looks like on a real
dotfiles-tracked `~/.scitex/`.

#### What's tracked (CONFIG — committed into the dotfiles repo)

Each row below is a real example from a maintainer's `~/.dotfiles/src/.scitex/`:

| Path | Why tracked |
|---|---|
| `agents/*.yaml` | Agent specifications — the same agent should boot the same way on every machine the user owns. |
| `account.json`, `usage.json` | Per-user account metadata (which org, which usage profile). Same across the user's machines. |
| `secrets/bot-token` *(the path, not the value)* | The **location pointer** for the token; the *value* is per-host (see runtime side). Tracking the path keeps every machine looking in the same place. |
| `dev/config.yaml`, `dev/cli-audit-dict.yaml` | scitex-dev's own per-scope config (§4a). |
| `scholar-config/`, `todo/`, `writer/`, ... | Per-package config trees that are conceptually "the user's choices" rather than "this run's output". |
| `*.def` | Apptainer / Singularity image **definitions** — text recipes, small, peer-versionable. The **built** `*.sif` blobs go under `runtime/containers/` per §4b. |
| `<pkg-short>/bin/<verb>_<noun>.sh` | Source wrappers per the §4b footnote — verb-form names per the project-template convention. |

#### What's gitignored (RUNTIME — per-machine, regenerated locally)

| Path | Why **not** tracked |
|---|---|
| `<pkg-short>/runtime/` and every `*.log`, `*.pid`, `cache/`, `workspace/`, `*.db` underneath | Per §4b — regenerable, often large, sometimes sensitive (PID files give away process structure). |
| `<pkg-short>/runtime/containers/*.sif` | Per the §4b footnote — large blobs, rebuild from the `.def` source instead of peer-rsyncing. |
| `overlays/`, `venvs/`, `<pkg-short>/runtime/bin/` (the *built* wrapper variants) | Per-host filesystem reality (Python prefix, container overlay path, etc.) baked in at build time. |
| `.credentials.json` and its `.credentials.json.bak.*` rotations | Secrets. The *path* may be tracked at the parent (a `secrets/` pointer file), but the values are not. |
| `accounts/*/projects/` | Per-account project working state — large, churn-y, host-local. |
| `runtime/cache/` (per §4c REPL-output cache) and any package-specific subcache | Regenerable on demand. |
| `session-transcripts/`, agent runtime logs | High volume, low long-term value, often sensitive. |
| `verification.db` (clew / verifier local DB) | Per-machine session state; regenerable from inputs + pipeline rerun. |

#### Mechanical enforcement — the `.gitignore` shape on the dotfiles side

The pattern the user's dotfiles repo carries (rooted at the home-directory level so it owns `.scitex/`):

```gitignore
# In the dotfiles repo's root .gitignore (covers ~/.scitex/* by symlink or stow):

# Block every runtime/ subtree under any package
.scitex/*/runtime/
!.scitex/*/runtime/.gitkeep
!.scitex/*/runtime/README.md

# Block the secret-bearing files at the user root, keep the directory shape
.scitex/.credentials.json
.scitex/.credentials.json.bak.*
.scitex/secrets/*
!.scitex/secrets/.gitkeep
!.scitex/secrets/README.md

# Per-account project state — host-local
.scitex/accounts/*/projects/
```

The negation lines (`!`) follow the same file-level rule as §1 (the
`.scitex/dev/config.yaml` example): once a parent is excluded, only
file-level re-includes work — never a re-included subdir.

#### Why this matters for peer-sync (`stow` / `chezmoi` / `rsync -a ~/.scitex`)

The dotfiles repo is what the user fans out across machines. The
RUNTIME / CONFIG split is **how `git status` keeps the fan-out honest**:

- A new tracked file shows up → it propagates to every paired machine on next pull. Intentional.
- A `runtime/*.sif`, `*.db`, `*.log` shows up → `git status` ignores it. Stays on the host that built it.
- A `.credentials.json` regression — say a package accidentally writes it tracked-side — appears in `git status` immediately. Fail-loud.

Without the runtime/ subtree convention, every package would have to
ship its own per-host exclude rules, and a single missing rule leaks
session state, container blobs, or secrets into the dotfiles repo.
With it, `runtime/` is **the one rule** and the rest is mechanical.

#### Anchor for cross-linking

Per-host READMEs (e.g. `~/.dotfiles/README.md`, the per-machine notes
in `~/.dotfiles/src/.scitex/README.md`) link **here** rather than
duplicating the rationale: this skill is the single source of truth
for the CONFIG-vs-RUNTIME contract. The host README's job is to
enumerate **which paths this user tracks on this host** — concrete,
local, narrow. The contract that makes the enumeration mean anything
is this section.

## 5. Forbidden locations

Do **not** write to any of these — they fragment the layout and break `SCITEX_DIR` relocation:

- `~/.cache/scitex/…` — use `~/.scitex/<pkg-short>/cache/` instead
- `~/.config/scitex/…` — use `~/.scitex/<pkg-short>/config.yaml` instead
- `~/.<pkg>/` (tool's own dotdir at home) — always under `~/.scitex/`
- `./.scitex/<pkg>.yaml` — bare file in project root; use `<project>/.scitex/<pkg-short>/config.yaml` (the project scope is always a directory, never a single file)
- `/tmp/scitex-<pkg>-*` — use `~/.scitex/<pkg-short>/cache/` for transient state that must survive a reboot; `tempfile.TemporaryDirectory()` for ephemeral

## 6. `SCITEX_DIR` — ecosystem-wide relocation

`$SCITEX_DIR` (default `~/.scitex`) is the **single lever** that relocates the user scope atomically. Honouring this is the entire reason we use one shared root instead of per-package dotdirs.

```bash
export SCITEX_DIR=/mnt/fast-ssd/scitex
# Everything under ~/.scitex/* now lives at /mnt/fast-ssd/scitex/*
```

Project scope (`<project>/.scitex/`) is intentionally *not* affected by `SCITEX_DIR` — project state lives with the project.

## 7. Always via `PathManager`, never hardcode

```python
# NO
screenshot_dir = Path.home() / ".scitex/scholar/workspace/screenshots"

# YES
screenshot_dir = (
    ScholarConfig().path_manager.get_cache_engine_dir() / "workspace" / "screenshots"
)
```

Hardcoded paths break when users set `SCITEX_DIR` or the package moves to project scope. `PathManager` consults both scopes in precedence order and returns the resolved path. Child packages should **not** import an upstream package's config to find their own dirs — inject the path as a constructor argument instead (see `01_ecosystem/03_modules-and-standalone-packages.md` §5).

## 8. Migration from legacy layouts

If a package already ships a different layout (`~/.scitex/<pkg>_config.yaml`, `~/.cache/scitex/<pkg>/…`, etc.), migrate once:

1. Add the new location to `PathManager` as primary.
2. On first startup, `mv` old → new and emit a one-time deprecation warning to stderr.
3. Keep the fallback read-path for one minor version, then remove.

Do not keep permanent back-compat shims — legacy locations silently defeat `SCITEX_DIR`.

## 9. Cross-package SoC — each package owns a domain

The `.scitex/<pkg-short>/` layout is also the canonical place each package stores config that **other packages then consume**. Rule of thumb:

> If a question has one obviously-correct answer that should be the same everywhere ("what is this machine called?", "what is the SLURM cluster?", "where is the scholar cache?"), exactly one scitex-* package owns it. Every other package imports its API.

Anti-pattern: each package re-deriving the answer (e.g. `socket.gethostname()` in five places, getting different results because of FQDN drift, login-node aliasing, container hostnames). When the answer drifts between packages, the user sees inconsistency on dashboards, in logs, in cron entries.

### Worked example — machine identity (owner: `scitex-resource`)

`scitex-resource` owns "what machine am I?" because resource detection is its domain. Config lives at `~/.scitex/resource/config.yaml`:

```yaml
machine:
  canonical_name: mba
  aliases:
    - Yusukes-MacBook-Air
    - Yusukes-MacBook-Air.local
  role: head
  hpc:                                  # optional
    cluster: spartan
    login_only: true
```

API (resolution: `$SCITEX_RESOURCE_MACHINE` → project config → user config → short hostname):

```python
from scitex_resource import get_machine_name, get_machine_config

name = get_machine_name()              # always returns the same string everywhere
cfg  = get_machine_config()            # full block with aliases / role / hpc
```

Consumers — `scitex-orochi`, `scitex-hpc`, `scitex-agent-container` — call `get_machine_name()` instead of rolling their own hostname logic. The user sets the canonical name once per host; every package agrees.

### When to make a new package the owner

Tempted to add config to `~/.scitex/<your-pkg>/config.yaml` for a fact other packages will also need? Ask:

1. **Is the fact about `<your-pkg>`'s domain?** If yes, you own it. Expose a public function. Done.
2. **Is the fact about a domain another scitex-* package already owns?** Consume their API. Don't duplicate the config.
3. **Is the fact ecosystem-wide and no package owns it yet?** Decide who *should* own it (whose name fits best), put the config there, expose the API there. **Do not** create a "scitex-shared" or "scitex-common" — that's anti-pattern (everyone depends on it, no one feels responsible for it).

The `runtime/` directory follows the same rule: `<pkg-short>/runtime/` is exclusively for *that* package's regenerable state. Never write into another package's `runtime/`.

### 9.5. Plugin-port pattern — never hardcode another package's tree

Even READS of another package's user-state directory are forbidden.
Concretely, a package X must NOT contain code like:

```python
# ❌ X knows about Y's tree.
extra = Path.home() / ".scitex" / "<other-pkg-short>" / "shared" / "agents"
if extra.is_dir():
    search_dirs.append(extra)
```

If X needs to give downstream consumers (Y) a way to extend its
behaviour, it exposes a **plugin port** — a colon-separated env var
that Y populates from Y's own tree:

```python
# ✓ X reads only from its own tree + an env-var slot.
SEARCH_DIRS = [
    Path.home() / ".scitex" / "<x-pkg-short>" / "agents",
    *[Path(p).expanduser()
      for p in os.environ.get("SCITEX_<X>_YAML_DIRS", "").split(":") if p.strip()],
]
```

Y then wires the plugin port from its own startup script:

```bash
# In Y's startup (Y's responsibility, not X's)
export SCITEX_<X>_YAML_DIRS=\
    ~/.scitex/<y-pkg-short>/agents:\
    ~/.scitex/<y-pkg-short>/runtime/extra-agents
```

Why this matters:
- X stays standalone; tests don't break when Y is uninstalled.
- Removing or renaming Y doesn't ripple into X's source tree.
- The dependency direction is explicit (Y depends on X, never the
  reverse) and documented in env vars, not hidden in path literals.

The same rule applies to **env vars**: X must not read
`SCITEX_<Y>_*` (e.g. `SCITEX_OROCHI_HOSTNAME` from a non-orochi
package). If X needs the same fact, it owns its own
`SCITEX_<X>_*` var or — better — calls the owning package's API
(see "Worked example — machine identity" above).

**Audit — `PS-145 local-state-cross-package-read`**: greps every
`*.py` under `src/` for `~/.scitex/<other-pkg>/` literals and
`SCITEX_<OTHER>_*` env-var reads (only when surrounded by
`os.environ` / `os.getenv` context — bare module constants like
`SCITEX_LOGGING_AVAILABLE = True` set by `try/except ImportError`
do not trip). Skips docstrings and `#` comments. Implementation
in `scitex_dev._cli.audit._project._check_local_state`,
severity `W` during bake-in.

## 10. Related

- `03_interface/02_cli/12_config-and-env.md` §6b — config-file resolution uses this layout.
- `01_ecosystem/03_modules-and-standalone-packages.md` §5–§6 — `PathManager` dependency-injection pattern.
- `01_ecosystem/04_environment-variables.md` — `SCITEX_DIR` and per-package `SCITEX_<PKG>_CONFIG`.
- `03_interface/04_skills/06_public-vs-private.md` — private skills live under `<pkg-short>/shared/skills/`.
- `scitex-resource` `_machine.py` — reference implementation of cross-package SoC (machine identity).

## 11. Quick Checklist (local-state directories)

- [ ] Every disk write goes under `<project>/.scitex/<pkg-short>/` or `~/.scitex/<pkg-short>/` — nowhere else.
- [ ] `<pkg-short>` is the pip name with the `scitex-` prefix stripped (e.g. `scitex-dev` → `dev`); non-prefixed packages use their bare name.
- [ ] Primary config file is named `config.yaml`; never `<pkg>_config.yaml`, never `<pkg>.yaml`.
- [ ] `<pkg-short>/runtime/` exists with `.gitkeep` + `README.md` committed; everything else under it gitignored.
- [ ] `.gitignore` exempts `.gitkeep` and `README.md` inside `runtime/` (`!.scitex/*/runtime/.gitkeep`, `!.scitex/*/runtime/README.md`).
- [ ] All paths resolve through `PathManager` — no `Path.home() / ".scitex/..."` literals in source.
- [ ] No writes to forbidden locations (`~/.cache/scitex/`, `~/.config/scitex/`, `~/.<pkg>/`, `./.scitex/<pkg>.yaml`, `/tmp/scitex-<pkg>-*`).
- [ ] **`pip install <pkg>` does not create `~/.scitex/<pkg-short>/`** (no post-install hooks, no setuptools cmdclass mkdir). Directory is created lazily on first write — see §3.5.
- [ ] **No writes or reads outside the package's own tree** — `~/.scitex/<other-pkg>/...` literals and `SCITEX_<OTHER>_*` env-var reads are forbidden in source. Use the plugin-port pattern (§9.5) for downstream extensibility.
- [ ] Setting `SCITEX_DIR=/some/other/path` relocates *every* user-scope read/write — verified by smoke test.
- [ ] Project scope is always a directory (`<project>/.scitex/<pkg-short>/`), never a single file at `<project>/.scitex/<pkg>.yaml`.
- [ ] If the package consumes another package's domain fact (machine name, SLURM cluster, …), it imports that package's API rather than re-deriving the answer.
- [ ] Migration shims from legacy paths are time-boxed (one minor version) — no permanent back-compat read paths.
- [ ] **Shell-completion install** writes a cache file under `~/.scitex/<pkg-short>/runtime/completion/<binary>` and a source line in the user's rc — never an `eval "$(_<PKG>_COMPLETE=...)"` line that re-invokes the binary on every shell start. See `03_interface/02_cli/03_required-introspection-commands.md`.
