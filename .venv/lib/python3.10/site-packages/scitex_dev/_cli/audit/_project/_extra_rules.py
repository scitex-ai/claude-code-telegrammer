"""Sidecar registry for newly-added audit rules.

`_audit.py` is over the 512-line file cap, so further Rule definitions
land here and are merged at import time. Each entry is the same shape
``_audit.RULES`` expects: ``(code, section, message, severity, slug)``.

Today's contents:

- PS-148 — optional-dep-unguarded-in-src (source-side mirror of PS-210)
- PS-149 — hard-dep-overreach (heavy HARD dep used feature-only; inverse of PS-148)
- PS-165 — workflow-presence (per category)
- PS-166 — readme-badge-label-mismatch
- PS-167 — readme-badge-layout
- PS-168 — workflow-secret-env-prefix-missing
- PS-173 — adr-format (filename + lean-template sections, when docs/adr/ exists)
- PS-180 — runtime-separation (src/<pkg>/runtime/ must be gitignored at the package level)
- PS-PATH-001/002 — config/PATH.yaml shape (outer wrapper / bare-string leaf)
- PS-CLEW-001 — clew.add_claim without self-verify in same module
- PS-AGENT-001 — scripts/agent/*.py with add_claim but no claims.json terminus
- RP-201/202/204/205 — research-project scripts ↔ tests/scripts mirror

When `_audit.py` is split per-rule (see GITIGNORED/REFACTORING.md), this
sidecar can be removed and each rule co-located with its check module.
"""

from __future__ import annotations

from typing import List, Tuple

# (code, section, message, severity, slug)
EXTRA_RULES: List[Tuple[str, str, str, str, str]] = [
    (
        "PS-165",
        "§2",
        (
            "missing required GitHub Actions workflow for the package's "
            "category. Every SciTeX package must ship a baseline set of "
            "workflows (cla, pytest matrix, import-smoke, pypi publish, "
            "scitex-dev quality audit, sync-main-to-release-tag; plus "
            "rtd-sphinx-build if docs/ ships, plus runtime CLI smoke for "
            'category = "cli-tool"). Declare the category in '
            'pyproject.toml under `[tool.scitex_dev] category = "..."` '
            "(defaults to `library`). Severity W during adoption — see "
            "_skills/general/02_package/07b_workflow-presence.md."
        ),
        "W",
        "workflow-presence-missing",
    ),
    (
        "PS-166",
        "§1",
        (
            "README shields.io badge uses a non-standard label. The "
            "ecosystem standardizes on short labels: pypi, python, docs, "
            "tests, install-check, quality, cov. Add `?label=<short>` to "
            "each shields.io badge URL. Reference: scitex-agent-container "
            "README badge block. Severity W during adoption — see "
            "_skills/general/02_package/12_workflows-naming.md "
            "§Standardized badge labels."
        ),
        "W",
        "readme-badge-label-mismatch",
    ),
    (
        "PS-167",
        "§1",
        (
            "README badge block does not match the canonical SAC "
            "layout. Every SciTeX package README MUST wrap its badges "
            "in `<!-- scitex-badges:start -->...<!-- scitex-badges:end "
            '-->` markers containing exactly TWO `<p align="center">` '
            "rows: row 1 = package-metadata badges "
            "(pypi/python/docs), row 2 = CI/health badges "
            "(tests/install-check/quality/cov). All badge images must "
            "be served from `img.shields.io/...` so they carry "
            "explicit `?label=<short>` labels (see PS-166). Reference: "
            "scitex-agent-container/README.md. Severity W during "
            "adoption — see _skills/general/04_docs/01_readme.md and "
            "_skills/general/04_docs/01_readme_template.md."
        ),
        "W",
        "readme-badge-layout",
    ),
    (
        "PS-168",
        "§1",
        (
            "GitHub Actions workflow references a `${{ secrets.<NAME> }}` "
            "or `${{ env.<NAME> }}` whose <NAME> is per-project but does "
            "not carry the package's `<PKG>_` prefix (and is not in the "
            "cross-cutting exception list — CLAUDE_CODE_CREDENTIALS_JSON, "
            "GH_TOKEN, CODECOV_TOKEN, GHCR_PAT, GITHUB_TOKEN, NPM_TOKEN, "
            "PYPI_API_TOKEN, ACTIONS_*_DEBUG). Without the prefix, "
            "`scitex-dev creds rotate-all` cannot distinguish the secret "
            "from the ecosystem-wide rotate target and silently skips it. "
            "Rename via `gh secret set <PKG>_<NAME>` + workflow `sed`. See "
            "_skills/general/02_package/14_workflow-secret-env-prefix.md."
        ),
        "E",
        "secret-env-prefix-missing",
    ),
    (
        "PS-148",
        "§3",
        (
            "a lib declared under `[project.optional-dependencies]` is "
            "imported UNGUARDED at module top of `src/`. A fresh "
            "`pip install <peer>` (no extras) then `import <peer>` would "
            "raise ModuleNotFoundError even though the package builds and "
            "its own test suite passes (the dev venv has the extra). Guard "
            "each import with `try_import_optional(..., extra=<extra>, "
            "pkg=<peer>)` (canonical) or a `try/except ImportError` block. "
            "Source-side mirror of the test-side PS-210. Severity W during "
            "ecosystem adoption (22 peers / ~1000 sites flagged at launch; "
            "promote to E once the heavy-dep leaks are guarded). See "
            "_skills/general/03_interface/01_python-api/"
            "04_lazy-imports-and-optional-deps.md and "
            "01_ecosystem/02_dependency-and-version-pinning.md."
        ),
        "W",
        "optional-dep-unguarded-in-src",
    ),
    (
        "PS-149",
        "§3",
        (
            "a heavy/niche lib (torch, tensorflow, figrecipe, scitex-app, "
            "…) is declared HARD via `[project.dependencies]` but imported "
            "ONLY in a feature / non-core part of `src/` — never the public "
            "`__init__` surface, the CLI entry, or the MCP-server entry. "
            "Every minimal `pip install <peer>` over-pulls it; container & "
            "sandbox builds bloat; the ecosystem graph gets denser than it "
            "needs to be. Move the dep to `[project.optional-dependencies]` "
            "(two-bucket: bare = minimal, `[all]` = batteries-included) and "
            "guard each import with `try_import_optional(..., pkg=<peer>)`. "
            "Framework/foundational deps the public surface needs (click, "
            "fastmcp, mcp, fastapi, scitex-dev, scitex-config) are NEVER "
            "flagged. Inverse of PS-148. Severity W during adoption — see "
            "_skills/general/"
            "01_ecosystem/02_dependency-and-version-pinning.md and "
            "03_interface/01_python-api/"
            "04_lazy-imports-and-optional-deps.md."
        ),
        "W",
        "hard-dep-overreach",
    ),
    (
        "PS-173",
        "§1",
        (
            "Architecture Decision Record (ADR) format. ADRs are a "
            "recommended (not mandated) ecosystem convention; a repo with "
            "NO `docs/adr/` gets no finding. But once `docs/adr/` exists, "
            "every `*.md` must be named `NNNN-<kebab-slug>.md` (4-digit "
            "zero-padded sequential prefix) and follow the LEAN template — "
            "a title (H1) plus `## Status` / `## Context` / `## Decision` / "
            "`## Consequences`. Section detection is tolerant of the proven "
            "scitex-agent-container exemplar shapes: `**Status:**` bold-line "
            "counts as Status, `## Problem` as Context, `## Decisions` as "
            "Decision. Scope = all project kinds (package / research / grant "
            "/ draft). Severity W during adoption — see "
            "_skills/general/02_package/01_project-structure-root.md "
            "§'Architecture Decision Records (ADRs)'."
        ),
        "W",
        "adr-format",
    ),
    (
        "PS-180",
        "§1",
        (
            "ecosystem runtime/ separation discipline: a package's "
            "`src/<pkg>/runtime/` directory exists on disk but no "
            "`.gitignore` entry covers it. Runtime artefacts (logs, "
            "caches, shell-completion outputs, generated state) are "
            "user-state, not source code — they MUST NOT be tracked "
            "by git. Add `runtime/` to `src/<pkg>/.gitignore` "
            "(package-local, preferred), or `src/<pkg>/runtime/` to "
            "the repo-root `.gitignore`, or `**/runtime/` (catch-all). "
            "Per the 2026-05-17 directive: default-track everything "
            "EXCEPT `<pkg>/runtime/`; exceptions belong in the "
            "package's own `.gitignore`, not a global rule. See "
            "`docs/needs-check-scitex-pkg-runtime-separation.md` and "
            "`_skills/general/02_package/02_project-structure-src.md`."
        ),
        "W",
        "ecosystem-runtime-separation",
    ),
    (
        "PS-213",
        "§3",
        (
            "console-script-deps-must-be-core: a dep imported at "
            "module-load on the reachability chain of any "
            "`[project.scripts]` entry-point MUST appear in "
            "`[project.dependencies]`. Currently the dep is satisfied "
            "only via `[project.optional-dependencies]`, so bare "
            "`pip install <peer>` followed by `<cli> --help` fails. "
            "Move the dep to `[project.dependencies]` (and drop any "
            "`try/except ImportError` graceful fallback — failing the "
            "import is the correct CI signal, not a runtime hint). "
            "Companion rule: PS-213i (info) emits LAZY-EXTRA-PATTERN-OK "
            "for the permitted opposite case (function-scope import + "
            "install hint referencing a real extra). See "
            "_skills/general/01_ecosystem/"
            "02_dependency-and-version-pinning.md "
            "§console-script-deps-must-be-core."
        ),
        "E",
        "core-cli-dep-missing",
    ),
    (
        "PS-213i",
        "§3",
        (
            "LAZY-EXTRA-PATTERN-OK: a dep declared only in "
            "`[project.optional-dependencies].<extra>` is "
            "lazy-imported inside a function body whose body also "
            "raises with a `pip install <pkg>[<extra>]` install hint. "
            "This is the canonical permitted pattern for "
            "optional-subcommand deps; PS-213i reports it as an "
            "info-severity signal so the operator can audit coverage "
            "of every optional subcommand without grepping by hand. "
            "Not a violation — info-only."
        ),
        "I",
        "lazy-extra-pattern-ok",
    ),
    # ── RP-2xx: research-project mirror (scripts ↔ tests/scripts) ──
    # Research projects (project-type: research) have no src/<pkg>/ — their
    # primary code lives in ./scripts/, mirrored by tests/scripts/. These
    # are the research-flavoured siblings of PS-201/202/204/205. The
    # auditor only fires them when `research` is in the project-types
    # (applies() routes RP -> research; see _config/_loader.py). Severity W
    # during ecosystem adoption (matches the PS-211/212 warn-first
    # precedent). See _skills/general/01_ecosystem/10_research-project-type.md and
    # _skills/scientific/02_research-project_06_project-structure-tests.md.
    (
        "RP-201",
        "§2",
        "missing `tests/scripts/` parent — mandatory mirror of ./scripts/",
        "W",
        "research-tests-scripts-parent-missing",
    ),
    (
        "RP-202",
        "§2",
        "scripts/<sub>/ has .py files but no matching tests/scripts/<sub>/",
        "W",
        "research-scripts-subdir-no-mirror",
    ),
    (
        "RP-204",
        "§2",
        "orphan test under tests/scripts/ — no scripts/ counterpart",
        "W",
        "research-orphan-test",
    ),
    (
        "RP-205",
        "§2",
        "public/private test-name prefix mismatch under tests/scripts/",
        "W",
        "research-test-prefix-mismatch",
    ),
    # ── PS-PATH / PS-CLEW / PS-AGENT — paper-scitex-clew MVP lint set ──
    # See PR #97 and operator directive 2026-06-01: skill page + lint rules
    # both anchored on the same "template must always work" north star.
    (
        "PS-PATH-001",
        "§1",
        (
            "config/PATH.yaml wraps its contents in an outer `PATH:` "
            "key. @stx.session exposes the file's top-level keys "
            "directly under `CONFIG.PATH.<KEY>`; the wrapper produces "
            "`CONFIG.PATH.PATH.<KEY>` and crashes 100% of "
            "`eval(CONFIG.PATH.<KEY>)` access sites with "
            "AttributeError. Remove the outer `PATH:` line and dedent "
            "its children one level. See "
            "_skills/scientific/"
            "02_research-project_03_project-structure-config-and-data.md "
            "§`PATH.yaml` and PR #97."
        ),
        "E",
        "path-yaml-outer-wrapper",
    ),
    (
        "PS-PATH-002",
        "§1",
        (
            "config/PATH.yaml has at least one leaf scalar value that "
            "is not an f-string literal. Scripts always do "
            '`eval(CONFIG.PATH.<KEY>)`; a bare `"./data/foo"` is '
            "parsed as the Python expression `./data/foo` and "
            "SyntaxErrors. Prefix every value with `f`, e.g. "
            '`KEY: f"./your/path"`, even for static paths. See '
            "_skills/scientific/"
            "02_research-project_03_project-structure-config-and-data.md "
            "§`PATH.yaml`."
        ),
        "E",
        "path-yaml-bare-string-leaf",
    ),
    (
        "PS-CLEW-001",
        "§3",
        (
            "a .py file calls `clew.add_claim(...)` but never calls "
            "`clew.verify_claim(...)` or `clew.list_claims(...)` in "
            "the same module. Without a post-loop self-verify the "
            "agent declares SUCCESS even when the chain of evidence "
            "(source_file SHA-256) is silently broken. Add a "
            "self-verify block after the registration loop: "
            "`for c in registered: result = "
            "clew.verify_claim(c.claim_id); assert "
            "result['source_verified']`. Canonical pattern: "
            "paper-scitex-clew commit 87a0f7b "
            "(`scripts/cohorts/_shared/prompts/examples/"
            "cohort_a_capsule_01_minimal/scripts/agent/"
            "03_register_claims.py`). Operator directive 2026-06-01."
        ),
        "W",
        "clew-add-claim-without-self-verify",
    ),
    (
        "PS-AGENT-001",
        "§3",
        (
            "a `scripts/agent/*.py` file calls `clew.add_claim(...)` "
            "but no module-level or function-level call writes a real "
            "`data/results/claims.json` file (neither "
            "`Path(...).write_text(...)` nor "
            "`stx.io.save(..., '...claims.json')`). The DAG terminus "
            "MUST be a real file — the launcher's verifier reads "
            "`data/results/claims.json` to score the run. After all "
            "`add_claim()` calls, persist the canonical claims.json, "
            "e.g. `Path(eval(CONFIG.PATH.CLAIMS_JSON))"
            ".write_text(json.dumps(payload, indent=2))`."
        ),
        "E",
        "agent-script-no-claims-json-terminus",
    ),
]
