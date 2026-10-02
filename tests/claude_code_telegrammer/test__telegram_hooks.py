"""The declared no-bare rule resolves to its shipped owner predicate."""

from importlib import import_module

from claude_code_telegrammer._telegram_hooks import provide_hooks


def test_declared_predicate_refuses_bare_reference():
    # Arrange
    rule = next(row for row in provide_hooks() if row.id == "telegrammer.no-bare-issue-number")
    module, name = rule.check.split(":")
    check = getattr(import_module(module), name)

    # Act
    verdict = check("PR #106")

    # Assert
    assert verdict.ok is False


def test_declared_predicate_accepts_parenthetical_reference():
    # Arrange
    rule = next(row for row in provide_hooks() if row.id == "telegrammer.no-bare-issue-number")
    module, name = rule.check.split(":")
    check = getattr(import_module(module), name)

    # Act
    verdict = check("PR #106（Storage 容量超過処理）")

    # Assert
    assert verdict.ok is True
