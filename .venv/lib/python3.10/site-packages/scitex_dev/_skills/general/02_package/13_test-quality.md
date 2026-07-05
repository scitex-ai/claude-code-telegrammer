---
description: |
  [TOPIC] Test-quality rules — the TQ family that guards against post-no-mock theater
  [DETAILS] Adopted 2026-05-14, sibling to the no-mocks rule. The no-mock rules (NM001-003) close the door on false confidence from mocks; the TQ rules close the residual theater patterns that survive: empty-assertion stubs (TQ001), AAA-marker enforcement (TQ002), descriptive-name requirement (TQ003), session-scope-with-mutation fixtures (TQ004), fixture-without-yield resource leaks (TQ005), parametrize-body conditionals (TQ006), and multi-assert-per-test (TQ007). Every test must satisfy: descriptive name (≥3 word-tokens after `test_`) + AAA marker comments (`# Arrange` / `# Act` / `# Assert` in order) + exactly one assertion. Together with no-mocks this guarantees: a failing CI line names exactly what behaviour broke. Enforced via linter rules `STX-TQ001-007` at error/warning severity, hooked into PostToolUse via `~/.claude/hooks/post-tool-use/run_lint.sh`. Read this BEFORE writing or reviewing any test in any scitex-* package.
tags: [scitex-general-package-test-quality]
---

# Test quality — TQ family

## Why

The no-mock rules (NM001-003) remove the largest source of false
confidence — but they don't catch every form of green-bar theater.
An AI asked to "make the tests pass" without mocks will still
generate `assert callable(fn)` placeholders, multi-Act tests where
the first failure masks the rest, and ambiguous names like
`def test_error()` that say nothing in CI output.

TQ closes those doors. The canonical contract:

- **TQ001** ensures every test has a real assertion.
- **TQ002** ensures every test's structure is visible (AAA markers).
- **TQ003** ensures the name says what's being tested.
- **TQ004/TQ005** ensure fixtures don't leak state or resources.
- **TQ006** ensures parametrize is one-intent-per-row.
- **TQ007** ensures one failing line in CI names exactly one
  behaviour.

## The rules

| Rule | Severity | What it catches |
| :-- | :-- | :-- |
| `STX-TQ001` | error | `test_*` function with no assertion (no `assert`, no `pytest.raises`, no `pytest.warns`, no `pytest.fail`) |
| `STX-TQ002` | error | Missing or out-of-order `# Arrange` / `# Act` / `# Assert` marker comments in the test body |
| `STX-TQ003` | error | Test name with <3 word-tokens after `test_` (e.g. `def test_foo()`, `def test_error()`) |
| `STX-TQ004` | warning | `@pytest.fixture(scope="session"/"module"/"package")` with state-mutation in body (`insert`/`write`/`append`/`update`/`set`/writable `open`) |
| `STX-TQ005` | warning | Fixture acquires a resource (`open`/`connect`/`urlopen`/`Session(`/`socket(`) but uses `return` instead of `yield` |
| `STX-TQ006` | warning | Top-level `if`/`else` inside a `@pytest.mark.parametrize`-decorated test (hides multi-intent) |
| `STX-TQ007` | error | More than one assertion in a single test function (`assert` statements + `with pytest.raises(...)` blocks combined) |

## TQ002 marker format — three separate comment lines

The TQ002 parser is strict by design: it requires **three separate
single-line comments** spelled exactly `# Arrange`, `# Act`,
`# Assert`, in that order, each on its own line. Combined forms are
silently rejected because the rule's purpose is structural visibility:

```python
# BAD — silently rejected (TQ002 fires):
# Arrange / Act / Assert
result = fn(x)
assert result == 42

# BAD — silently rejected:
# Act / Assert
with pytest.raises(ValueError):
    fn(bad_input)

# GOOD:
# Arrange
x = 1
# Act
result = fn(x)
# Assert
assert result == 42
```

### `pytest.raises` and the `# Act` / `# Assert` split

`pytest.raises` is the one shape where Act and Assert appear to merge.
Resolve it by binding the context manager under `# Act` and entering
it under `# Assert`:

```python
def test_validate_raises_typeerror_for_non_string_input():
    # Arrange
    bad_input = 42
    # Act
    ctx = pytest.raises(TypeError)
    # Assert
    with ctx:
        validate(bad_input)
```

The same shape applies to `pytest.warns`.

## The canonical shape

```python
def test_register_creates_user_with_correct_name():
    # Arrange
    user_data = {"name": "Alice"}
    service = UserService(db=db)
    # Act
    user = service.register(user_data)
    # Assert
    assert user.name == "Alice"


def test_register_marks_new_user_active():
    # Arrange
    user_data = {"name": "Alice"}
    service = UserService(db=db)
    # Act
    user = service.register(user_data)
    # Assert
    assert user.is_active is True
```

Two separate tests for the two assertions. Shared setup goes into a
fixture; the AAA markers stay in each test body.

## Replacement patterns

### Multi-assert → split

```python
# BAD (TQ007)
def test_register_user():
    # Arrange / Act
    user = service.register(user_data)
    # Assert
    assert user.name == "Alice"
    assert user.is_active is True

# GOOD
def test_register_returns_user_with_supplied_name(): ...
def test_register_marks_returned_user_active(): ...
```

### Multi-Act → split

```python
# BAD (TQ007; also the article's "Act が複数")
def test_user_workflow():
    user = service.register(...)
    assert user.is_active is True
    service.deactivate(user.id)
    assert user.is_active is False

# GOOD: one Act per test, named for what each verifies.
def test_register_creates_active_user(): ...
def test_deactivate_sets_is_active_false(): ...
```

### Parametrize-body conditional → split

```python
# BAD (TQ006)
@pytest.mark.parametrize("v, e, raises", [
    ("a@b.c", True, False), (None, None, True),
])
def test_validate_email(v, e, raises):
    if raises:
        with pytest.raises(TypeError):
            validate_email(v)
    else:
        assert validate_email(v) == e

# GOOD: two parametrized tests, one intent each.
@pytest.mark.parametrize("v, e", [("a@b.c", True), ("x@y", False)])
def test_validate_email_returns_expected_for_valid_input(v, e): ...

@pytest.mark.parametrize("v", [None, 42, []])
def test_validate_email_raises_typeerror_for_non_string_input(v): ...
```

### Session-scope-with-mutation → function-scope or split

```python
# BAD (TQ004)
@pytest.fixture(scope="session")
def db():
    d = create_db()
    d.insert({"id": 1, "name": "Alice"})  # mutation!
    yield d
    d.drop()

# GOOD
@pytest.fixture(scope="session")
def db_template():
    """Immutable template — populate once per session."""
    d = create_db()
    d.insert({"id": 1, "name": "Alice"})
    yield d
    d.drop()

@pytest.fixture
def db(db_template):
    """Per-test copy — mutations are isolated."""
    return db_template.copy()
```

## When the replacement feels expensive

The reflex when a test starts hitting 2+ assertions is to think "this
is a workflow test; splitting it is duplicative". That reflex is the
signal that **a fixture is missing**. The two tests will share
arrange-phase setup; lift it into a fixture and each test stays a
single Act.

If a test genuinely needs to verify a multi-step workflow end-to-end,
it belongs in an integration suite under `tests/integration/`, not as
a unit test.

## Enforcement

- **Linter** (`scitex-dev lint check-files`) — fires on every save
  via the PostToolUse hook. Error-severity rules block the save;
  warning-severity rules surface for review.
- **Audit** (`scitex-dev ecosystem audit-python-apis`) — currently
  PA-306 (no-mocks) only; PA-307 for test-quality may be added if
  drift between leaf packages becomes an issue.

## Related skills

- [02_package/12_no-mocks.md](12_no-mocks.md) — Parent
  rule. TQ is downstream of NM.
- [02_package/06_project-structure-tests.md](06_project-structure-tests.md) — Where tests live.
- [02_package/11_ci-and-codecov.md](11_ci-and-codecov.md)
  — Coverage wiring; TQ-compliant tests are what makes the coverage
  number meaningful.
