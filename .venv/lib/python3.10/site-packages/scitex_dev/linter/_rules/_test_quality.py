"""Category TQ: test-quality rules — guard against post-mock theater.

The no-mock rules (NM001-003) close the door on the largest source of
false confidence, but they don't catch every form of green-bar theater.
The TQ rules guard against the structural anti-patterns that remain
when an AI generates `test_*` shapes that compile and pass but don't
test anything.

Rules (all enforce "tests must break when production code breaks,
and pass only when production code works"):

- **TQ001** — empty assertion (no `assert` and no `pytest.raises` /
  `pytest.warns` / `pytest.fail`). Catches `assert callable(fn)`
  placeholders and "I added a test for coverage" stubs.
- **TQ002** — AAA-marker enforcement: every `test_*` function body
  must contain `# Arrange`, `# Act`, `# Assert` comments, in that
  order. Forces the author to think about — and the reviewer to see —
  the Arrange-Act-Assert structure of each test. Markers are matched
  case-insensitively and may carry descriptive text after the keyword
  (`# Arrange: build the fixture`); only the keyword's presence and
  position matter.
- **TQ007** — exactly one assertion per test function/method. Combined
  with TQ001 (≥1 assert) this enforces "one test, one assertion". When
  the first assert fails, every subsequent assert is silently skipped;
  the only safe contract is one-assertion-per-test. `with
  pytest.raises(...)` / `with pytest.warns(...)` count as one
  assertion; combining them with extra `assert` statements is a
  violation. The fix is always to split into multiple tests.
- **TQ003** — non-descriptive test name (fewer than 3 word-tokens
  after `test_`). `def test_foo()` and `def test_error()` are not
  describing anything.
- **TQ004** — session- or module-scope fixture with state-mutation
  inside its body (`insert`, `write`, `append`, `update`, `set`,
  `open` in write mode). Causes cross-test contamination.
- **TQ005** — fixture acquires an external resource (`open`,
  `connect`, `urlopen`, `Session(`, `socket(`) but uses `return`
  instead of `yield` for cleanup. Resource leak.
- **TQ006** — conditional (`if`/`else`) at the top level of a
  `@pytest.mark.parametrize`-decorated test body. Means two different
  tests are pretending to be one.

TQ002 uses a pragmatic heuristic: after the first `ast.Assert` at
the top level of the test body, any subsequent top-level statement
that contains an `ast.Call` (other than another `ast.Assert`) is
flagged as a second Act. The risk of false positives (post-assert
cleanup calls) is low because cleanup belongs in fixtures, not in
the test body — if a test does need post-assert cleanup, that's the
signal to extract a fixture.

See `_skills/general/02_package/12_no-mocks.md` for the parent
rationale and `~/.claude/skills/ywatanabe/05_testing/00_no-mocks.md`
for the personal directive.
"""

from ._base import Rule

TQ001 = Rule(
    id="STX-TQ001",
    severity="error",
    category="testing",
    message=(
        "Test function has no assertion — running it only proves the import "
        "works, not that the code behaves. A test without an assertion is "
        "green-bar theater: it inflates the test count without exercising "
        "anything."
    ),
    suggestion=(
        "Add an `assert` on the actual return value / state the production "
        "code produces. If the test expects an exception, use "
        "`with pytest.raises(SomeError):`. If the test expects a warning, "
        "use `with pytest.warns(SomeWarning):`. `assert callable(fn)` "
        "after `from mod import fn` is not a real test — delete it or "
        "replace with an assertion on actual behaviour. No `# stx-allow:` "
        "suppression — the rule has no carve-outs."
    ),
)

TQ002 = Rule(
    id="STX-TQ002",
    severity="error",
    category="testing",
    message=(
        "Test function body is missing one or more AAA-structure marker "
        "comments. Each of `# Arrange`, `# Act`, `# Assert` must appear "
        "on its own line in order. Combined forms like "
        "`# Arrange / Act / Assert` or `# Act / Assert` are rejected. "
        "Every test must have all three, in order, so both the author "
        "and the reviewer can see the AAA structure at a glance."
    ),
    suggestion=(
        "Add the three marker comments at the top level of the function "
        "body, in this order:\n"
        "    def test_register_creates_active_user():\n"
        "        # Arrange\n"
        "        user_data = {'name': 'Alice'}\n"
        "        service = UserService(db=db)\n"
        "        # Act\n"
        "        user = service.register(user_data)\n"
        "        # Assert\n"
        "        assert user.is_active is True\n"
        "Descriptive text after the keyword is allowed "
        "(`# Arrange: build the fixture`); the keyword and its position "
        "are what the rule checks. No `# stx-allow:` suppression."
    ),
)

TQ003 = Rule(
    id="STX-TQ003",
    severity="error",
    category="testing",
    message=(
        "Test name has fewer than 3 word-tokens after `test_` — the name "
        "doesn't describe what is being tested. `test_foo`, `test_error`, "
        "`test_returns_dict` are ambiguous when they fail in CI."
    ),
    suggestion=(
        "Rename to `test_<subject>_<condition>_<expected>`. "
        "Bad: `def test_register(): ...` / `def test_error(): ...`. "
        "Good: `def test_register_user_with_valid_email_creates_active_user`. "
        "The test name should read like a one-line specification: "
        "reviewers can tell from the failure line alone what behaviour "
        "broke. No `# stx-allow:` suppression."
    ),
)

TQ004 = Rule(
    id="STX-TQ004",
    severity="warning",
    category="testing",
    message=(
        'Fixture is `scope="session"` or `scope="module"` AND mutates '
        "state inside its body (`insert` / `write` / `append` / `update` / "
        "`set` / writable `open`). Cross-test contamination — tests start "
        "depending on execution order."
    ),
    suggestion=(
        'Change to `scope="function"` (the pytest default — usually drop '
        "the `scope=` argument entirely). If the setup is expensive, "
        "split: a session-scope fixture builds the read-only template "
        "(e.g. an immutable artefact in `tmp_path`), a function-scope "
        "fixture copies it per test for mutations. No `# stx-allow:` "
        "suppression."
    ),
)

TQ005 = Rule(
    id="STX-TQ005",
    severity="warning",
    category="testing",
    message=(
        "Fixture acquires an external resource (`open(...)` / `connect(...)` "
        "/ `urlopen(...)` / `Session(...)` / `socket(...)`) but returns it "
        "via `return`, not `yield`. Resource leak — the close/cleanup step "
        "is missing."
    ),
    suggestion=(
        "Convert `return resource` to `yield resource` followed by an "
        "explicit cleanup (`resource.close()`, `resource.__exit__(...)`, "
        "etc.). The pytest fixture machinery runs the post-yield code as "
        "teardown even when the test raises. Without `yield`, file "
        "handles / DB connections / sockets stay open until the GC sweep, "
        "which is timing-dependent and CI-flaky. No `# stx-allow:` "
        "suppression."
    ),
)

TQ007 = Rule(
    id="STX-TQ007",
    severity="error",
    category="testing",
    message=(
        "Test function has more than one assertion (counts `assert` "
        "statements plus `with pytest.raises(...)` / "
        "`with pytest.warns(...)` blocks). When the first assert fails, "
        "every subsequent assert is silently skipped — half the contract "
        "goes untested. The combination of TQ003 (descriptive name) + "
        "TQ007 (one assert) means a single failing line in CI tells you "
        "exactly what behaviour broke."
    ),
    suggestion=(
        "Split into multiple test functions, one assertion each. Name "
        "each one for the specific behaviour it verifies "
        "(`test_register_creates_user_with_correct_name`, "
        "`test_register_marks_new_user_active`). If the asserts share "
        "setup, lift it into a fixture. `with pytest.raises(SomeError):` "
        "counts as one assertion on its own — don't combine it with "
        "extra `assert` statements. No `# stx-allow:` suppression."
    ),
)

TQ006 = Rule(
    id="STX-TQ006",
    severity="warning",
    category="testing",
    message=(
        "Test decorated with `@pytest.mark.parametrize(...)` has a top-"
        "level `if`/`else` in its body. Two different test intents are "
        "wearing one function's clothes — the if-branch and else-branch "
        "are really different tests."
    ),
    suggestion=(
        "Split into two test functions: one for the normal-case "
        "parametrization and one for the exception-case (e.g. wrapped "
        "in `with pytest.raises(...)`). Mixing them via a `should_raise` "
        "flag column hides the contract: reviewers can't tell from the "
        "parameter table which row is testing what. No `# stx-allow:` "
        "suppression."
    ),
)
