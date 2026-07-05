---
description: |
  [TOPIC] Migrate a peer package's test tree to TQ-compliant shape
  [DETAILS] After NM (no-mocks) and TQ (test-quality, AAA + ≥3-word names + 1-assert) landed at error severity in scitex-dev 2026-05-14, every peer package's test tree will surface hundreds-to-thousands of PA-306 / PA-307 violations on `audit-python-apis`. This playbook documents the canonical migration sequence (NM → TQ003 → TQ002 → TQ007) so each peer takes the same shape. Each step is mechanical and amenable to subagent dispatch. Tracking: the playbook itself, the per-peer ordering, the verification gate, and the rollback contract are all here.
tags: [scitex-general-development-tq-migration]
---

# Ecosystem TQ migration playbook

## When to run this

A peer package's `scitex-dev ecosystem audit-python-apis <pkg>` reports
PA-306 or PA-307 violations. Almost every peer will, because the rules
shipped 2026-05-14 at error severity — but no peer has been cleaned yet.

## What "done" looks like

```
$ scitex-dev ecosystem audit-python-apis <pkg>
SUCC: <pkg>: no Python API violations
```

Exit code 0. Audit-all headline `SUCC:` instead of `ERRO:`. The full
test suite still passes (with `pytest-randomly` enabled, since
ordering bugs surface in random order).

## The canonical sequence

Four passes. Each is mechanical; the only judgement is "what does this
test actually verify". Each pass is amenable to subagent dispatch
because the in-place edit is well-defined.

### Pass 1 — NM (no-mocks)

Remove every `unittest.mock` / `mock` / `pytest_mock` import,
`mocker` / `monkeypatch` fixture parameter, and mock symbol use.

For each violation:

- Replace `monkeypatch.setenv(X, Y)` with a `yield`-based fixture that
  sets `os.environ[X]` and pops on teardown.
- Replace `monkeypatch.setattr(mod, attr, val)` with: refactor the
  production function to accept `attr` as a kwarg, default to the
  module global, pass the test value explicitly.
- Replace `patch("mod.X")` with the same pattern.
- Replace `MagicMock()` with a hand-rolled fake class exposing only the
  methods the SUT calls.
- Replace `pytest.importorskip(...)` placeholders with
  `__import__(...)` + a real assertion on the returned module's
  identity / behaviour (or use importorskip + a real assertion).

For subprocess collaborators (`gh`, `ssh`, `git`), write a real shell
shim script into `tmp_path/bin/`, prepend to `$PATH`, drop any
injection. See `scitex_dev._creds._rotate` + its test for the
canonical gh-shim, and `scitex_dev._sync._local` + its test for the
ssh-shim.

Verification: `scitex-linter check-files tests --no-color | grep
STX-NM | wc -l` → 0. Full suite passes.

### Pass 2 — TQ003 (descriptive names)

Rename every test whose name has <3 word-tokens after `test_`.

For each `def test_<short>():`:

- Read the body. The name should describe *what the test asserts*,
  not what the SUT is called.
- Format: `test_<subject>_<condition>_<expected>`.
- Class-grouped tests can lean on class context but each method
  itself still needs ≥3 tokens.

Verification: `scitex-linter check-files tests --no-color | grep
STX-TQ003 | wc -l` → 0.

### Pass 3 — TQ002 (AAA markers)

Insert `# Arrange`, `# Act`, `# Assert` comments into every `test_*`
function body, **at the right phase boundaries**.

The mechanical (`# Arrange / # Act / # Assert` stacked at the top)
passes the rule but defeats its purpose. Place each marker before its
phase:

```python
def test_register_creates_active_user():
    # Arrange
    service = UserService(db=db)
    user_data = {"name": "Alice"}
    # Act
    user = service.register(user_data)
    # Assert
    assert user.is_active is True
```

Empty Arrange / Act sections are fine when the test has none of
that phase.

Verification: `STX-TQ002` → 0.

### Pass 4 — TQ007 (one assert per test)

Split every multi-assert test into N single-assert tests.

For each test with N assertions:

1. If they assert on the result of a single Act, lift the
   Arrange+Act into a `@pytest.fixture` (or a private `_helper`
   method on the class) and have each new test pull from it.
2. If they assert on multiple Acts (workflow test), split per Act.
   That signals a hidden integration test — consider whether the
   split tests belong as unit tests or as `tests/integration/`.

Each split keeps the prior pass's AAA markers and name discipline.
Names get more specific: `test_register_user` becomes
`test_register_sets_user_name_from_input` +
`test_register_marks_returned_user_active`.

Verification: `STX-TQ007` → 0. Test count typically 2–3× the
original.

## Subagent dispatch template

The four passes are amenable to dispatch in this order. Each subagent
prompt should include the explicit CI-hook ack ("ignore the develop
CI failure flag — it's pre-existing and unrelated") to avoid the
subagent pausing on the recurring warning.

```text
Mechanical batch task: [pass description]
Working directory: /home/ywatanabe/proj/<peer>
Goal: scitex-linter check-files tests --no-color | grep <RULE> | wc -l → 0
Constraints: ...
Verification: ...
```

See the scitex-dev session 2026-05-14 for the prompts used; they
landed cleanly across 91 files in scitex-dev.

## Verification gate (per-peer)

After all four passes:

1. `scitex-dev ecosystem audit-python-apis <peer>` → `SUCC:`, exit 0.
2. `python -m pytest tests/ -q -p no:randomly` → all pass.
3. `python -m pytest tests/ -q` (with randomly enabled) → all pass.
   Step 3 is the real gate — ordering bugs only surface in random
   order. The scitex-dev session caught one (`find_matching_files`
   non-deterministic ripgrep output drifting `file_id` between
   preview and execute) only via the random-order suite.

## Common gotchas

- **Importorskip placeholders.** `pytest.importorskip(module_name)` as
  the whole test body counts as empty-assertion under TQ001. Add a
  real assertion on the returned module's `__name__` and `__spec__`.

- **Smoke-import tests.** `def test_module_imports(): importlib.import_module(...)`
  is theater. Replace with assertions on the module's public API
  surface (e.g. `assert callable(mod.expected_fn)`).

- **Watchdog / no-raise tests.** Tests that verify "no exception"
  pass under TQ001 if you add an explicit flag:
  ```python
  completed = False
  with watchdog(2.0):
      completed = True
  assert completed
  ```

- **State-leak across tests.** When TQ007 splits surface flaky
  tests in full-suite order, the culprit is usually module-level
  state in the production code (e.g. `rename_io._sudo_password`,
  ripgrep's non-deterministic output ordering). Fix the production
  state, don't paper over with fixtures.

## Rollback

If a TQ007 split makes a previously-stable test flaky AND the
underlying production state is hard to fix:

1. First: try to fix the production-state bug. The scitex-dev
   `find_matching_files` fix took 3 lines (add `sorted(...)`).
2. If the fix is genuinely out-of-scope, revert the split for that
   one test, leave a `# stx-allow:` comment explaining why, and
   open a tracking issue.
3. **Never** revert the four-pass framework for a whole peer.
   Each rule is independently load-bearing.

## Related skills

- [02_package/12_no-mocks.md](../02_package/12_no-mocks.md) — NM rationale.
- [02_package/13_test-quality.md](../02_package/13_test-quality.md) — TQ
  rationale.
- [02_package/06_project-structure-tests.md](../02_package/06_project-structure-tests.md) —
  Where tests live.
