from typing import List

from backend.crawler.two_pass import TwoPassResult

from backend.domain.rules.models import (
    Rule,
    RuleApplicability,
    RuleCondition,
)
from backend.rule_engine.operators import OperatorEvaluator
from backend.rule_engine.evaluator import (
    DeclarativeEvaluator,
    EvaluationResult,
)
from backend.rule_engine.evaluators.state_diff import StateDiffEvaluator
from backend.schemas.core import (
    CheckResult,
    ComplianceStatus,
    Observation,
)


class RuleEngine:
    """
    Executes compliance rules against crawler observations.
    """

    def __init__(self):
        self.declarative_evaluator = DeclarativeEvaluator()
        self.state_diff_evaluator = StateDiffEvaluator()
        self.operator_evaluator = OperatorEvaluator()

    def evaluate_rule(
        self,
        rule: Rule,
        observations: List[Observation] | TwoPassResult,
    ) -> CheckResult:

        if rule.applicability is not None:
            if not self._is_applicable(
                rule.applicability,
                observations,
            ):
                return CheckResult(
                    check_id=rule.id,
                    name=rule.name,
                    status=ComplianceStatus.NOT_APPLICABLE,
                    severity=rule.severity,
                    confidence=1.0,
                    explanation=(
                        f"Rule '{rule.name}' is not applicable because "
                        "its applicability conditions were not satisfied."
                    ),
                    recommendation=None,
                    evidence=[],
                )

        evaluation = self._evaluate(
            rule,
            observations,
        )

        status = (
            rule.result.pass_
            if evaluation.passed
            else rule.result.fail
        )

        if evaluation.passed:
            evidence = evaluation.matched_observations
        elif rule.source.match == "all":
            evidence = evaluation.failed_observations
        elif rule.source.match == "none":
            evidence = evaluation.matched_observations
        else:
            evidence = []

        explanation = self._build_explanation(
            rule,
            evaluation,
        )

        confidence = self._calculate_confidence(
            evaluation,
        )

        return CheckResult(
            check_id=rule.id,
            name=rule.name,
            status=status,
            severity=rule.severity,
            confidence=confidence,
            explanation=explanation,
            recommendation=(
                rule.recommendation
                if not evaluation.passed
                else None
            ),
            evidence=evidence,
        )

    def evaluate_rules(
        self,
        rules: List[Rule],
        observations: List[Observation] | TwoPassResult,
    ) -> List[CheckResult]:

        return [
            self.evaluate_rule(
                rule,
                observations,
            )
            for rule in rules
        ]

    def _is_applicable(
        self,
        applicability: RuleApplicability,
        observations: List[Observation] | TwoPassResult,
    ) -> bool:
        """
        Determine whether a rule should be evaluated.

        At least one observation of the configured category
        must satisfy the configured conditions.
        """

        if isinstance(observations, TwoPassResult):
            candidate_observations = observations.accept_observations
        else:
            candidate_observations = observations

        for observation in candidate_observations:
            if observation.category != applicability.observation:
                continue

            if self._matches_conditions(
                applicability.conditions,
                observation,
            ):
                return True

        return False

    def _matches_conditions(
        self,
        conditions,
        observation: Observation,
    ) -> bool:

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
        data,
        field_path: str,
    ):
        current = data

        for field in field_path.split("."):
            if isinstance(current, dict):
                current = current.get(field)
            else:
                return None

        return current

    def _evaluate(
        self,
        rule: Rule,
        observations: List[Observation],
    ) -> EvaluationResult:

        if rule.evaluator == "declarative":
            return self.declarative_evaluator.evaluate(
                rule,
                observations,
            )

        if rule.evaluator == "state_diff":
            if not isinstance(observations, TwoPassResult):
                raise TypeError(
                    "state_diff rules require a TwoPassResult containing "
                    "accept and reject observations."
                )

            return self.state_diff_evaluator.evaluate(
                rule,
                observations.accept_observations,
                observations.reject_observations,
            )

        if rule.evaluator == "visual":
            raise NotImplementedError(
                "visual evaluator is not implemented yet."
            )

        if rule.evaluator == "nlp":
            raise NotImplementedError(
                "nlp evaluator is not implemented yet."
            )

        raise ValueError(
            f"Unsupported evaluator: {rule.evaluator}"
        )

    @staticmethod
    def _build_explanation(
        rule: Rule,
        evaluation: EvaluationResult,
    ) -> str:

        if evaluation.passed:
            return (
                f"Rule '{rule.name}' passed. "
                f"{len(evaluation.matched_observations)} "
                f"observation(s) satisfied the rule."
            )

        return (
            f"Rule '{rule.name}' failed. "
            f"{len(evaluation.failed_observations)} "
            f"observation(s) did not satisfy the rule."
        )

    @staticmethod
    def _calculate_confidence(
        evaluation: EvaluationResult,
    ) -> float:

        total = (
            len(evaluation.matched_observations)
            + len(evaluation.failed_observations)
        )

        if total == 0:
            return 0.0

        return (
            len(evaluation.matched_observations)
            / total
        )