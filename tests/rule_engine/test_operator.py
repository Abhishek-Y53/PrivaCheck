from backend.rule_engine.operators import OperatorEvaluator


def test_equals():
    assert OperatorEvaluator.evaluate(
        "equals",
        "https",
        "https",
    ) is True

    assert OperatorEvaluator.evaluate(
        "equals",
        "http",
        "https",
    ) is False


def test_not_equals():
    assert OperatorEvaluator.evaluate(
        "not_equals",
        "http",
        "https",
    ) is True


def test_contains():
    assert OperatorEvaluator.evaluate(
        "contains",
        "Privacy Policy",
        "Privacy",
    ) is True


def test_exists():
    assert OperatorEvaluator.evaluate(
        "exists",
        "https",
        True,
    ) is True

    assert OperatorEvaluator.evaluate(
        "exists",
        None,
        True,
    ) is False


def test_not_exists():
    assert OperatorEvaluator.evaluate(
        "not_exists",
        None,
        True,
    ) is True


def test_starts_with():
    assert OperatorEvaluator.evaluate(
        "starts_with",
        "https://example.com",
        "https://",
    ) is True


def test_ends_with():
    assert OperatorEvaluator.evaluate(
        "ends_with",
        "example.com",
        ".com",
    ) is True


def test_matches():
    assert OperatorEvaluator.evaluate(
        "matches",
        "privacy@example.com",
        r"^[\w.-]+@[\w.-]+\.\w+$",
    ) is True


def test_greater_than():
    assert OperatorEvaluator.evaluate(
        "greater_than",
        10,
        5,
    ) is True


def test_less_than():
    assert OperatorEvaluator.evaluate(
        "less_than",
        5,
        10,
    ) is True


def test_in():
    assert OperatorEvaluator.evaluate(
        "in",
        "https",
        ["http", "https"],
    ) is True


def test_not_in():
    assert OperatorEvaluator.evaluate(
        "not_in",
        "ftp",
        ["http", "https"],
    ) is True