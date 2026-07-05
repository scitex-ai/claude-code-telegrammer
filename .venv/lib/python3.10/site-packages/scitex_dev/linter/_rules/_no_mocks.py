#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: "2026-05-14 22:31:05 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-dev/src/scitex_dev/linter/_rules/_no_mocks.py


"""Category NM: no-mocks rules.

Tests exist to raise the quality of production code. They have no
other purpose. A test that passes while production is broken has
negative value: it manufactures false confidence, which is worse
than no test at all.

Mocks are the single largest source of false confidence in test
suites we have seen. The failure mode is structural, not anecdotal:

  1. A mock encodes the test author's *assumption* about how a
     collaborator behaves.
  2. Production code talks to the real collaborator, whose actual
     behaviour can drift from the assumption at any time — a library
     upgrade, a schema change, a renamed field, a new error path.
  3. The test continues to pass because it is asking the mock, not
     reality. The drift is invisible until production breaks.

This is especially dangerous in agent-assisted development. An LLM
asked to "make the tests pass" will reach for mocks first, because
mocks are the cheapest way to turn red green. The resulting test
suite reports green while exercising nothing real. We have watched
this happen often enough that we are closing the door entirely.

The rule is therefore absolute: no `unittest.mock`, no `pytest-mock`,
no `monkeypatch`, no exceptions, no per-line suppressions. If a
piece of code cannot be tested without mocking, that is a design
signal — the code should be restructured so its collaborators are
injected as arguments, or the test should run against the real
collaborator (a `tmp_path`, a hand-rolled fake, a local fake server,
a real subprocess).

The goal is not test coverage. The goal is tests that actually
exercise production paths, so that a green suite is evidence the
system works.

We are trying to raise the quality of the code. We want real tests — tests that actually exercise production paths, not tests that pass because everything is mocked out. We want meaningful tests, not green-bar theater.

See `_skills/general/02_package/12_no-mocks.md` for the full rationale,
the replacement menu, and a worked example.
"""

from ._base import Rule

NM001 = Rule(
    id="STX-NM001",
    severity="error",
    category="testing",
    message=(
        "Mock library import (`unittest.mock` / `mock` / `pytest_mock`) — "
        "forbidden ecosystem-wide, no exceptions. A test that imports a "
        "mock library is on a path to manufacturing false confidence: "
        "green when reality has drifted, silent when production breaks. "
        "We want meaningful tests to raise the quality of the code, "
        "not green-bar theater."
    ),
    suggestion=(
        "Delete the import and rewrite the test against a real "
        "collaborator. Replacement menu, in preference order: "
        "(1) restructure production code so the collaborator is "
        "injected as an argument and pass a hand-rolled fake class "
        "with just the methods the test exercises; "
        "(2) run against the real thing — `tmp_path` for filesystem, "
        "a real subprocess against a fixture script, a local fake "
        "server, an in-process SQLite for DB-shaped tests; "
        "(3) if neither is feasible, delete the test — a test that "
        "needs mocks to pass is exercising the mock, not the code. "
        "Per-line suppression (`# stx-allow: STX-NM001`) is not "
        "supported; the rule has no carve-outs by design. See "
        "docs/testing/no-mock-recipes.md."
    ),
)

NM002 = Rule(
    id="STX-NM002",
    severity="error",
    category="testing",
    message=(
        "pytest `mocker` / `monkeypatch` fixture parameter — forbidden "
        "ecosystem-wide, no exceptions. These fixtures encode the "
        "author's assumption about a collaborator; production talks to "
        "the real collaborator, so the test goes green while drift "
        "(library upgrade, renamed field, new error path) goes silent. "
        "We want meaningful tests to raise the quality of the code, "
        "not green-bar theater."
    ),
    suggestion=(
        "Remove the fixture parameter and substitute reality: "
        "for env vars, use a `yield`-based fixture that sets "
        "`os.environ[...]` and pops on teardown; "
        "for attributes, refactor the production code to take the "
        "collaborator as a parameter and pass a hand-rolled fake; "
        "for filesystem state, use `tmp_path` and write the real bytes; "
        "for subprocess, invoke a real helper script in `tmp_path`. "
        "If the test only passes because `monkeypatch` is rewriting "
        "production internals, the test isn't testing production — "
        "rewrite or delete it. No per-line suppression."
    ),
)

NM003 = Rule(
    id="STX-NM003",
    severity="error",
    category="testing",
    message=(
        "Mock symbol (`Mock`, `MagicMock`, `AsyncMock`, `patch`, "
        "`mock_open`, `PropertyMock`, `create_autospec`, `MockerFixture`) "
        "— forbidden ecosystem-wide, no exceptions. A `MagicMock` "
        "answers every question the test asks; that's the whole "
        "failure mode — the test stops asking reality and starts "
        "asking its own assumption. "
        "We want meaningful tests to raise the quality of the code, "
        "not green-bar theater."
    ),
    suggestion=(
        "Replace the mock object/decorator with a real value: "
        "hand-roll a small fake class (a dataclass or plain class with "
        "the few attributes/methods the production code actually uses, "
        "with `calls.append(...)` if the test asserts on call "
        "arguments) and inject it via constructor/parameter/fixture; "
        "or restructure so the production code calls a function that "
        "the test can pass a real implementation to. If the only way "
        "to get the test green is `patch(...)`-ing internals, treat "
        "that as a design signal — invert the dependency or delete "
        "the test. The rule has no carve-outs and no `# stx-allow:` "
        "suppression."
    ),
)

# EOF
