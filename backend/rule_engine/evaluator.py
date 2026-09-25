from typing import Any, List

from backend.domain.rules.models import Rule, RuleCondition
from backend.rule_engine.operators import OperatorEvaluator
from backend.schemas.core import Observation


class EvaluationResult:
    """
    Result of evaluating a single rule against observations.
    """

    def __init__(
        self,
        passed: bool,
        matched_observations: List[Observation],
        failed_observations: List[Observation],
    ):
        self.passed = passed
        self.matched_observations = matched_observations
        self.failed_observations = failed_observations


class DeclarativeEvaluator:
    """
    Evaluates declarative rules against crawler observations.
    """

    def __init__(self):
        self.operator_evaluator = OperatorEvaluator()

    def evaluate(
        self,
        rule: Rule,
        observations: List[Observation],
    ) -> EvaluationResult:

        relevant_observations = [
            observation
            for observation in observations
            if observation.category == rule.source.observation
        ]

        matched_observations: List[Observation] = []
        failed_observations: List[Observation] = []

        for observation in relevant_observations:
            if self._evaluate_observation(rule, observation):
                matched_observations.append(observation)
            else:
                failed_observations.append(observation)

        passed = self._evaluate_match(
            rule.source.match,
            relevant_observations,
            matched_observations,
        )

        return EvaluationResult(
            passed=passed,
            matched_observations=matched_observations,
            failed_observations=failed_observations,
        )

    def _evaluate_observation(
        self,
        rule: Rule,
        observation: Observation,
    ) -> bool:

        conditions = rule.conditions

        if conditions.all is not None:
            return all(
                self._evaluate_condition(
                    condition,
                    observation,
                )
                for condition in conditions.all
            )

        if conditions.any is not None:
            return any(
                self._evaluate_condition(
                    condition,
                    observation,
                )
                for condition in conditions.any
            )

        if conditions.not_ is not None:
            return not any(
                self._evaluate_condition(
                    condition,
                    observation,
                )
                for condition in conditions.not_
            )

        return False

    def _evaluate_condition(
        self,
        condition: RuleCondition,
        observation: Observation,
    ) -> bool:

        actual_value = self._get_field(
            observation.data,
            condition.field,
        )

        return self.operator_evaluator.evaluate(
            condition.operator,
            actual_value,
            condition.value,
        )

    @staticmethod
    def _get_field(
        data: Any,
        field_path: str,
    ) -> Any:

        current = data

        for field in field_path.split("."):

            if isinstance(current, dict):
                current = current.get(field)

            else:
                return None

        return current

    @staticmethod
    def _evaluate_match(
        match_type: str,
        relevant_observations: List[Observation],
        matched_observations: List[Observation],
    ) -> bool:

        if not relevant_observations:
            return False

        if match_type == "all":
            return len(matched_observations) == len(
                relevant_observations
            )

        if match_type == "any":
            return len(matched_observations) > 0

        raise ValueError(
            f"Unsupported match type: {match_type}"
        )