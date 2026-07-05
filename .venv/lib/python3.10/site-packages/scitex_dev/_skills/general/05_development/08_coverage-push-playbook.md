---
description: |
  [TOPIC] Coverage push playbook — getting a package from 30% to 90%+ without `omit` shortcuts
  [DETAILS] Adopted 2026-05 after scitex-stats went 32% → ~90% in one session. The playbook is: (1) wire subprocess coverage (leaf 06), (2) add the demo smoke test (leaf 07), (3) use the Codecov tree API as the feedback loop (faster than re-running CI), (4) fix real bugs found along the way — never xfail / skip / omit, (5) refactor 900-LOC files into core + sibling demos to fit the 512-LOC project budget, (6) for the long tail, write direct unit tests for `_cli/`, `_mcp/_handlers/`, and `_plot_*` helpers. Lessons codified so the next package doesn't rediscover them.
tags: [scitex-general-package-coverage-push]
---

# Coverage push playbook

For taking a SciTeX peer from ~30% to ≥90% Codecov in one focused
session. Sequence matters — each step unlocks the next.

## Sequence

### 1. Wire subprocess coverage FIRST

See `05_development/06_subprocess-coverage.md`.

Without this, the rest of the playbook is invisible to Codecov. This
single step is typically +10 to +20 points once demos start running.

### 2. Add the demo smoke test

See `05_development/07_demo-smoke-tests.md`.

In scitex-stats this picked up 27 modules × ~50-200 LOC = ~1500 LOC of
previously-zero-coverage demos in one parametrised test.

### 3. Use the Codecov tree API, not CI re-runs

Don't push a commit and wait 7 minutes to see if the number moved. The
Codecov v2 tree API returns per-file coverage as JSON:

```bash
curl -s "https://codecov.io/api/v2/github/<owner>/repos/<repo>/report/tree?branch=develop&path=src/<pkg>" \
  | jq '.[] | {name, coverage: .coverage, hits: .hits, misses: .misses}' \
  | sort -k 2 -n
```

That gives an ordered list of the next biggest gaps. Pick the worst,
write tests for it locally, run `pytest --cov` to confirm, commit.

For per-file detail:

```bash
curl -s "https://codecov.io/api/v2/github/<owner>/repos/<repo>/report/tree?branch=develop&path=src/<pkg>/<subdir>/_file.py" \
  | jq '.files[].line_coverage' | head
```

This is much faster than the CI-wait loop.

### 4. Fix real bugs — never xfail / skip / omit

Every smoke-test failure you find IS a real bug. Fix it at root:

- `NameError: stx` → function-scope `import scitex as stx` (PA-304).
- `AttributeError: applymap` → migrate to pandas 2.2 `Styler.map`.
- `ValueError: return_as="excel"` → switch to `df.to_excel` directly.
- Stale `xfail` markers on tests that pass → remove the markers.

If you find yourself reaching for `@pytest.mark.xfail`, `@pytest.mark.skip`,
or `omit` entries in `codecov.yml` to hit the number, **stop**.
Coverage gamed this way rots: the next refactor masks a regression.

The only legitimate `omit` entries are the ones already in the canonical
`codecov.yml` (`_sphinx_html/`, `_skills/`, `_completion.py`, etc.) —
these are non-executable surfaces, not "code I don't want to test".

### 5. Refactor over budget files into core + sibling demos

The 512-LOC file budget exists. Files like `_normalizers.py` at 927 LOC
or `_correct_fdr.py` at ~600 LOC (with 250 lines of embedded demo) trip
the audit. The clean refactor:

- **Big util file** → split into focused modules + thin re-exporting
  orchestrator. scitex-stats split `_normalizers.py` (927 LOC) into
  `_normalize_core.py` + `_export_files.py` + `_export_reports.py`,
  keeping `_normalizers.py` as a 58-LOC re-export shim. Public API
  unchanged.
- **Core + embedded demo** → move the demo into a sibling `_demo_*.py`.
  `_correct_fdr.py` with its 250-line demo becomes `_correct_fdr.py`
  (core, fits budget) + `_demo_correct_fdr.py` (the demo). The smoke
  test picks up the sibling.

Both moves are pure — no behaviour change — and they leave the package
cleaner than they found it. Resist the temptation to skip this step
just because the budget is "only a warning".

### 6. Long-tail direct unit tests

After the smoke test and refactors, the remaining gaps are usually:

- `_cli/*` click commands — drive via `click.testing.CliRunner`.
  One test per subcommand, covering each flag's branch. See
  `tests/<pkg>/_cli/test___init__.py` in scitex-stats for the
  reference shape.
- `_mcp/_handlers/*` — async handlers; drive via
  `asyncio.run(handler(request))`. One test per handler, covering
  happy path + at least one error branch.
- `_plot_*` helpers — usually called only via `func(plot=True)`.
  Write a direct unit test that calls them with a small synthetic
  result dict and asserts the returned Figure has the expected
  number of axes.
- Numpy-path tests for `_real.py` / `_nan.py` / `_circular.py`
  modules whose torch path is `pytest.importorskip`-guarded — the
  numpy path should run unconditionally.

Aim for one test file per source module (mirror via PS-204), each with
3-5 small tests covering distinct branches.

## Acceptance gate

When the Codecov tree API says ≥90% AND the audit is clean, bump
version, write CHANGELOG entry, tag, ship. See
`05_development/03_release-automation.md` for release mechanics.

## Anti-patterns

- **"It's hard to test, so add to `omit`."** This is technical debt
  masquerading as cleanup. The only entries that belong in `omit` are
  non-executable surfaces.
- **"The CI is slow, so push commits and watch the number."** Use the
  Codecov tree API instead — it's instant and tells you exactly which
  file to attack next.
- **"It's a generated file, no point testing."** If it's executable
  Python that ships to users, it needs at least a smoke test. If it's
  truly generated boilerplate (e.g. `_completion.py` for shell tab
  completion), that goes in `omit` — but check first that it's actually
  static.
- **"Just one xfail to unblock the release."** xfail today is a real
  failure tomorrow. Fix the underlying issue.

## Time budget

scitex-stats: 32% → ~90% in one focused session (~6h of attention).
Per-step ballpark:

- Subprocess wiring: 30 min (small change, easy to get wrong; the
  `setdefault`-vs-force-set bug eats time if you don't know it).
- Demo smoke test: 1h (assembling the module list + fixing the bugs
  it surfaces).
- Refactor over-budget files: 1-2h (mechanical splits + import fixups).
- Long-tail unit tests: 2-3h (depends on package surface area).

For a smaller / simpler package, halve these estimates. For a package
with no demos and a clean core, you can usually skip steps 1-2 and go
straight to the long-tail.

## Related skills

- `05_development/06_subprocess-coverage.md` — step 1.
- `05_development/07_demo-smoke-tests.md` — step 2.
- `02_package/11_ci-and-codecov.md` — overall CI / codecov.yml setup.
- `02_package/08_quality.md` — the 512-LOC file budget and other
  audit rules referenced in step 5.
- `09_quality/01_failure-playbook.md` — no-cut-corners principle that
  underpins steps 4 and "anti-patterns" above.
