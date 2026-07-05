---
description: |
  [TOPIC] Skills Registration
  [DETAILS] How a SciTeX package becomes discoverable to `scitex-dev skills export` — the two required `pyproject.toml` entry points (`scitex_dev.docs` + `scitex_dev.skills`), the `pip install -e . --no-deps --force-reinstall` step that refreshes the entry-point cache, and the verification one-liner. Without both entry points the package is silently skipped.
tags: [scitex-general-interface-skills-registration]
---

# Registration

`scitex-dev skills export` discovers a package via two entry points. **Both are required** — `skills` for the leaf files and `docs` for ecosystem-aware doc tooling. Without both, the package is silently skipped (with a warning logged) and `~/.claude/skills/scitex/<pkg>/` never gets populated.

```toml
# pyproject.toml — every standalone scitex-* package needs BOTH:
[project.entry-points."scitex_dev.docs"]
my-package = "my_package"

[project.entry-points."scitex_dev.skills"]
my-package = "my_package"
```

After editing `pyproject.toml`, **re-install** so the entry points hit the metadata. `pip install -e . --no-deps` will not always rebuild the entry-points cache — use `--force-reinstall` to be safe:

```bash
pip install -e . --no-deps --force-reinstall
python -c "from importlib.metadata import entry_points as ep; print([e.name for e in ep(group='scitex_dev.skills')])"
```

## Hatch caveat

Do NOT add `[tool.hatch.build.targets.wheel.force-include]` for `_skills/` — hatch already includes files under `src/<pkg>/` in the wheel. Adding `force-include` causes duplicate-file errors on build.

For setuptools-based packages (e.g., `scitex-cloud`), `_skills/` ships only when declared as package data:

```toml
[tool.setuptools.package-data]
<pkg_name> = ["_skills/**/*.md"]
```

`scitex-cloud/pyproject.toml` is the reference setuptools example — it declares both `_skills/**/*.md` and the legacy `skills/*.md` paths.

After every wheel-publish, verify a fresh `pip install scitex-<pkg>` into a clean venv still sees the skills:

```bash
python -c "from importlib.resources import files; print(list(files('<pkg_name>._skills').iterdir()))"
```

## Cross-references

- [08_editable-installation.md](08_editable-installation.md) — how the loader resolves source vs wheel
- [09_export-commands.md](09_export-commands.md) — running the exporter
- [11_troubleshooting.md](11_troubleshooting.md) — common registration failures
