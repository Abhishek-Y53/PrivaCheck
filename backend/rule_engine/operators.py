import re
from typing import Any


class OperatorEvaluator:
    """
    Evaluates generic comparison operators.
    """

    @staticmethod
    def evaluate(
        operator: str,
        actual: Any,
        expected: Any,
    ) -> bool:

        if operator == "equals":
            return actual == expected

        if operator == "not_equals":
            return actual != expected

        if operator == "contains":
            if isinstance(actual, (str, list, tuple, set)):
                return expected in actual
            return False

        if operator == "not_contains":
            if isinstance(actual, (str, list, tuple, set)):
                return expected not in actual
            return False

        if operator == "starts_with":
            return (
                isinstance(actual, str)
                and isinstance(expected, str)
                and actual.startswith(expected)
            )

        if operator == "ends_with":
            return (
                isinstance(actual, str)
                and isinstance(expected, str)
                and actual.endswith(expected)
            )

        if operator == "exists":
            return actual is not None

        if operator == "not_exists":
            return actual is None

        if operator == "matches":
            if not isinstance(actual, str):
                return False

            if not isinstance(expected, str):
                return False

            return re.search(expected, actual) is not None

        if operator == "greater_than":
            try:
                return actual > expected
            except TypeError:
                return False

        if operator == "less_than":
            try:
                return actual < expected
            except TypeError:
                return False

        if operator == "in":
            try:
                return actual in expected
            except TypeError:
                return False

        if operator == "not_in":
            try:
                return actual not in expected
            except TypeError:
                return False

        raise ValueError(f"Unsupported operator: {operator}")