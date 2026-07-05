---
description: |
  [TOPIC] No mocks, no exceptions — the SciTeX testing discipline
  [DETAILS] Adopted 2026-05-14. The SciTeX ecosystem bans `unittest.mock`,
  `pytest-mock`, `monkeypatch`, and every mock symbol (`Mock`, `MagicMock`,
  `AsyncMock`, `patch`, `mock_open`, `PropertyMock`, `create_autospec`,
  `MockerFixture`) without carve-outs. The rule is structural, not stylistic:
  mocks encode the test author's assumption, production talks to the real
  collaborator, and drift between the two stays silent until production
  breaks. Enforced two ways: linter rules STX-NM001 (mock module imports) /
  STX-NM002 (mocker / monkeypatch fixture parameters) / STX-NM003 (mock
  symbols) at severity=error in `scitex-dev lint` and the PostToolUse
  `run_lint.sh` hook, and auditor rule PA-306 in `scitex-dev ecosystem
  audit-python-apis` / `audit-all` which scans `src/`, `tests/`, `examples/`,
  and `scripts/` at the repo root. Includes the replacement menu (inject + fake
  → real collaborator → delete) and a worked example from the scitex-dev
  test-tree cleanup. Read this BEFORE writing or reviewing any test in any
  scitex-* package.
tags: [scitex-general-package-no-mocks]
---

# No mocks, no exceptions

## Why

Tests exist to raise the quality of production code. They have no other
purpose. A test that passes while production is broken has negative
value: it manufactures false confidence, which is worse than no test at
all.

Mocks are the single largest source of false confidence we have measured
in SciTeX test suites. The failure mode is structural, not anecdotal:

1. A mock encodes the test author's *assumption* about how a collaborator
   behaves.
2. Production code talks to the real collaborator, whose actual behaviour
   can drift from the assumption at any time — a library upgrade, a schema
   change, a renamed field, a new error path.
3. The test continues to pass because it is asking the mock, not reality.
   The drift is invisible until production breaks.

This is especially dangerous in agent-assisted development. An LLM asked
to "make the tests pass" will reach for mocks first, because mocks are
the cheapest way to turn red green. The resulting test suite reports
green while exercising nothing real. We have watched this happen often
enough that we are closing the door entirely.

The goal is not test coverage. The goal is tests that actually exercise
production paths, so that a green suite is evidence the system works.

## The rule

No `unittest.mock`. No `pytest-mock`. No `monkeypatch`. No mock symbols.
**No exceptions, no per-line suppressions.** `# stx-allow: STX-NM00*` is
not honoured — the rule has no carve-outs by design.

If code cannot be tested without mocking, that is a design signal: the
production code should be restructured so its collaborators are injected
as arguments, or the test should run against the real collaborator.

## Replacement menu (in preference order)

1. **Inject the collaborator.** Refactor the production function to take
   the collaborator as a keyword argument with a sensible default. Pass
   a hand-rolled fake from the test. This is the canonical pattern.
2. **Use the real thing.** `tmp_path` for filesystem state. A real
   subprocess against a fixture script you write in `tmp_path`. A local
   in-process HTTP server. An in-process SQLite for DB-shaped tests.
3. **Delete the test.** A test that passes only because it `patch`-es
   internals is exercising the mock, not the code. The right answer is
   often to drop it and write an integration test instead, or to delete
   the test outright if the behaviour is already covered.

For env vars specifically, use a `yield`-based fixture:

```python
@pytest.fixture
def fake_token():
    os.environ["GH_TOKEN"] = "test-token"
    try:
        yield
    finally:
        os.environ.pop("GH_TOKEN", None)
```

For module-level callables the test wants to swap, refactor so the call
site looks the callable up via the module (`from . import foo; foo.bar()`
instead of `from .foo import bar`) and have the production function
accept an override parameter:

```python
def my_op(x, *, lookup=None):
    if lookup is None:
        lookup = default_lookup
    ...
```

The fake then comes in via the parameter — no patching, no globals.

## Hand-rolled fakes — sizing

A fake should expose only the methods and attributes the production
code under test actually uses. If the real collaborator has 40 methods
and the code touches 2, the fake has 2. Use `types.SimpleNamespace`,
`@dataclass`, or a plain class. If the test asserts on call arguments,
record them:

```python
class FakeClient:
    def __init__(self):
        self.calls: list[tuple] = []

    def send(self, topic, payload):
        self.calls.append((topic, payload))
        return "ok"
```

This is the pattern `MagicMock` was for. The difference is that the fake
is **honest**: it cannot answer questions the test never thought to ask,
and renaming `send` in production turns the test red, which is exactly
the contract we want.

## Worked example — `scitex_dev._creds._rotate`

The original test patched `_detect_repo_for_package`'s module-level
collaborators (`get_local_path`, `ECOSYSTEM`) via `monkeypatch.setattr`,
and patched `subprocess.check_output` via `unittest.mock.patch`.

**Production refactor** — accept the collaborators as keyword
parameters, default to the module globals:

```python
# src/scitex_dev/_creds/_rotate.py
def _detect_repo_for_package(
    name: str,
    *,
    ecosystem: dict | None = None,
    local_path_lookup=None,
) -> str | None:
    if local_path_lookup is None:
        local_path_lookup = get_local_path
    if ecosystem is None:
        ecosystem = ECOSYSTEM
    local = local_path_lookup(name)
    ...
    info = ecosystem.get(name) or {}
    ...
```

**Test refactor** — pass a real fake registry dict and a real
`local_path_lookup` callable; for the subprocess call, write a real
shell shim into `tmp_path/bin/gh` and prepend it to `$PATH`:

```python
def _install_gh_shim(bin_dir: Path, *, remote_sha: str | None = None) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    log = bin_dir / "calls.log"
    log.write_text("")
    sha = remote_sha or ""
    script = f"""#!/usr/bin/env bash
verb="$1 $2"
case "$verb" in
  "variable get") echo "var_get" >> "{log}"; echo "{sha}"; exit 0 ;;
  "secret set")   echo "secret_set" >> "{log}"; exit 0 ;;
  ...
esac
"""
    gh = bin_dir / "gh"
    gh.write_text(script)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return log
```

This is a real subprocess. It exercises the real `subprocess.check_output`
call in production. If we rename the `gh` invocation, the test fails. If
GitHub's `gh` changes its argument shape, an integration test against the
real binary will catch it. The mock-based version caught neither.

The full refactor is visible in commit history under `_creds/_rotate.py`
and `tests/scitex_dev/_creds/test__rotate.py` from 2026-05-14.

## Shared fixtures the campaign produced

The PA-306 conversion campaign distilled two reusable fixtures that
replace the most common mock idioms. Lift them into `conftest.py`
rather than re-implementing per file:

- **`subprocess_shim`** — writes a real fake binary into
  `tmp_path/bin/<name>`, prepends `$PATH`, returns a calls-log path.
  Replaces `unittest.mock.patch("subprocess.check_output")` and the
  whole family of "I just want to assert we called `gh variable get`"
  tests. The shim is a real shell script; it exercises the real
  `subprocess` codepath end-to-end and fails honestly if the
  production call shape changes.
- **`env_save_restore`** — `yield`-based fixture that snapshots and
  restores `os.environ` mutations across a test. Replaces every
  `monkeypatch.setenv(...)` pattern.

## Real production dataclasses, not `SimpleNamespace`-as-config

A `MagicMock`-shaped or `types.SimpleNamespace`-shaped config object
passed to production code is a mock under a different name: it answers
every attribute lookup the test author thought to write, and silently
diverges from the production dataclass schema. **Always instantiate the
real production dataclass** (`AgentConfig(name="...", ...)` etc.). If
the dataclass has many required fields, give them sensible defaults
upstream rather than dodging it with `SimpleNamespace`. The
field-rename-breaks-tests property is what we want.

## Honest delete > dishonest rewrite

For a test file that was pure mock theater — every assertion was
`mock.assert_called_with(...)`, no production-state observation — the
right move is **delete the file** and replace it with a real
integration test that observes outcome state. NOT a line-by-line
rewrite that preserves the original assertions: the original test had
negative value; preserving its shape preserves the negative value.

## Whole-file lint gate: TQ + NM clear *together*

The PostToolUse `run_lint.sh` hook treats TQ002/TQ007 (AAA markers +
single assertion) and NM001–003 (no mocks) as a single gate: a save
is rejected if either set is dirty. Partial cleanups — "I removed the
mocks, the TQ002 markers come next PR" — are blocked by design. A
half-clean file invites drift; clear both at once.

## When the replacement feels too expensive

Three signals that the test isn't worth keeping:

- The only way to set it up is `patch`-ing four module-level globals.
- The assertions are all "was this internal helper called with these
  args" rather than "did the system produce the right output for the
  user".
- The production function is doing so much that no single test can
  cover it without faking half the world.

In all three cases, **delete the test and write a smaller integration
test**, or refactor the production function first. The rule is doing its
job: it surfaced a design problem.

## Enforcement

| Surface | Code | Severity | What it scans |
| :-- | :-- | :-- | :-- |
| Linter (`scitex-dev lint check-files`) | `STX-NM001` | error | `import` / `from` of `unittest.mock`, `mock`, `pytest_mock` |
| Linter | `STX-NM002` | error | `mocker` / `monkeypatch` fixture parameters |
| Linter | `STX-NM003` | error | Calls and decorators using `Mock`, `MagicMock`, `AsyncMock`, `patch`, `mock_open`, `PropertyMock`, `create_autospec`, `MockerFixture` (and imports of those names) |
| `~/.claude/hooks/post-tool-use/run_lint.sh` | (same) | exit 2 | Every `Write`/`Edit` of a `*.py` — blocks Claude Code from writing mocks |
| Auditor (`scitex-dev ecosystem audit-python-apis` / `audit-all`) | `PA-306` | warn | Whole repo: `src/<pkg>/`, `tests/`, `examples/`, `scripts/` |

The linter and the auditor cover the same patterns by design. The linter
catches per-file edits in the inner loop; the auditor catches drift across
the whole package + test tree in CI / scheduled audits.

## Related skills

- [02_package/06_project-structure-tests.md](06_project-structure-tests.md) — Where tests live (the `_real` sibling convention pre-dates this rule and is now redundant — all tests must run against real collaborators).
- [02_package/11_ci-and-codecov.md](11_ci-and-codecov.md) — Coverage wiring; mocks inflate coverage without exercising real paths, so the no-mock rule is what makes the coverage number meaningful.
- [05_development/07_demo-smoke-tests.md](../05_development/07_demo-smoke-tests.md) — Demo smoke tests are the canonical real-integration sibling to unit tests.
- [01_ecosystem/08_linter-plugins.md](../01_ecosystem/08_linter-plugins.md) — How the NM rules are wired into the linter engine.
