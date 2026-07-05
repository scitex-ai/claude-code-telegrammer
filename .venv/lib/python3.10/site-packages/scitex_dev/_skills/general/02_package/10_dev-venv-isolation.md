---
description: |
  [TOPIC] Package Dev-Venv Isolation
  [DETAILS] Every SciTeX package must own a real `<pkg-root>/.venv/` for local development. The .venv MUST NOT be a symlink to a shared global venv (e.g. `~/.venv`) — symlinked .venvs silently merge every peer's deps into one bag, defeating the CI-parity invariant. `scitex-dev ecosystem install` defaults to `--venv per-package` and auto-repairs symlinked .venvs.
tags: [scitex-general-package-dev-venv-isolation]
---

# Per-package `.venv/` isolation

Every SciTeX package must keep a **real, isolated** virtual environment
at `<pkg-root>/.venv/`. That isolation is the local mirror of CI: each
peer's `[dev]` / `[all]` extras get exercised against the same versions
of its own deps that CI installs, with no leakage from the other 60+
peers in the ecosystem.

## The symlink anti-pattern

A common developer shortcut is to symlink every peer's `.venv` to a
single shared global venv:

```bash
# ❌ ANTI-PATTERN — every peer ends up writing into ~/.venv/
cd ~/proj/scitex-io && ln -s ~/.venv .venv
cd ~/proj/scitex-stats && ln -s ~/.venv .venv
# ...60 more
```

Looks tidy at first — but every `pip install -e <peer>[dev]` from
inside that peer's directory silently writes into the shared
`~/.venv`. The result:

- **Dep collisions**: peer A pins `numpy<2`, peer B installs `numpy>=2`
  later — A is silently broken, no warning.
- **No CI parity**: CI installs each peer into a fresh venv with only
  that peer's deps; the shared local venv has all 60+ peers' deps
  resolved together, so resolutions that fail in CI may "work"
  locally and vice versa.
- **Cascading "where did `X` come from?"**: a peer can import a module
  it never declared as a dep, because some other peer in the shared
  venv brought it in. Drift goes undetected until release.

## The correct layout

```
~/proj/scitex-io/.venv/                ← real venv, owns its own site-packages/
~/proj/scitex-stats/.venv/             ← real venv, owns its own site-packages/
~/proj/scitex-clew/.venv/              ← real venv, owns its own site-packages/
...
```

Each one is a real `python -m venv` directory:

```bash
$ ls -la ~/proj/scitex-io/.venv
drwxr-xr-x  bin/
drwxr-xr-x  include/
drwxr-xr-x  lib/
-rw-r--r--  pyvenv.cfg
...
```

NOT a symlink (no `lrwxrwxrwx` at the `.venv` line).

## Bootstrap

`scitex-dev ecosystem install` defaults to per-package venvs since the
`per-package`-default change:

```bash
# Per-package install (DEFAULT) — creates <pkg>/.venv/ if missing
# and installs INTO it, with [dev] extras for every peer.
scitex-dev ecosystem install --extras dev --yes -j 8

# Repair existing symlinked .venv → real isolated venv: same command.
# `_ensure_venv` detects a symlink at <pkg>/.venv and replaces it with
# a real venv before installing. Re-running is idempotent.
```

The legacy "everything into one shared venv" mode is still available
as opt-in `--venv current` for the rare case where you actually want
one bag (e.g. quick experimentation across peers; not a real dev
setup).

## Auditing

The expected audit signal is **none**: a symlinked `.venv` is invisible
to `audit-project` because `.venv` is gitignored across the ecosystem.
The check happens at install-time (the `_ensure_venv` repair step), not
at audit-time. If you want a fleet-wide sanity probe:

```bash
for d in ~/proj/scitex-* ~/proj/{crossref,openalex}-local ~/proj/{figrecipe,newb,socialia}; do
    [ -L "$d/.venv" ] && echo "SYMLINKED: $d"
done
```

## Disk-cost note

Per-package venvs cost ~50–500 MB each depending on extras. For ~66
peers the total is roughly 5–15 GB — modest by modern standards and
worth it for CI parity. If a workstation is genuinely disk-constrained,
the right tradeoff is not to symlink, but to (a) skip `[all]` extras
on peers you're not actively developing, or (b) use `uv` (with its
shared package cache) to install — uv hardlinks wheels across venvs,
so the on-disk footprint is dominated by metadata rather than the
wheels themselves.

## Related

- `01_ecosystem/02_dependency-and-version-pinning.md` — why CI parity
  matters for the ecosystem.
- `01_ecosystem/06_dot_scitex_directory.md` — sibling rule that
  `<pkg-root>/.scitex/` is for git-tracked dev state, never for venvs.
- `scitex-dev ecosystem install --help` — the install command itself.
