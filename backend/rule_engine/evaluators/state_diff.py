from __future__ import annotations

import json
from typing import Any, Iterable, List

from backend.domain.rules.models import Rule, RuleCondition
from backend.rule_engine.evaluator import EvaluationResult
from backend.rule_engine.operators import OperatorEvaluator
from backend.schemas.core import Observation


class StateDiffEvaluationResult(EvaluationResult):
    """Result of comparing the observations from two browser states."""

    def __init__(
        self,
        passed: bool,
        matched_observations: List[Observation],
        failed_observations: List[Observation],
        *,
        accept_only_count: int = 0,
        reject_only_count: int = 0,
        common_count: int = 0,
    ):
        super().__init__(
            passed=passed,
            matched_observations=matched_observations,
            failed_observations=failed_observations,
        )
        self.accept_only_count = accept_only_count
        self.reject_only_count = reject_only_count
        self.common_count = common_count


class StateDiffEvaluator:
    """Generic evaluator for comparing two named browser states.

    The evaluator knows nothing about GDPR, trackers, cookies, or consent.
    A rule supplies:
      - the observation category to compare,
      - optional conditions selecting relevant observations,
      - identity fields used to compare observations,
      - the set relationship that should hold between Accept and Reject.
    """

    def __init__(self) -> None:
        self.operator_evaluator = OperatorEvaluator()

    def evaluate(
        self,
        rule: Rule,
        accept_observations: List[Observation],
        reject_observations: List[Observation],
    ) -> StateDiffEvaluationResult:
        if rule.state_diff is None:
            raise ValueError(
                f"Rule '{rule.id}' uses state_diff but has no state_diff configuration."
            )

        accept_relevant = self._filter_observations(
            rule,
            accept_observations,
        )
        reject_relevant = self._filter_observations(
            rule,
            reject_observations,
        )

        key_fields = rule.state_diff.key_fields

        accept_map = self._build_identity_map(
            accept_relevant,
            key_fields,
        )
        reject_map = self._build_identity_map(
            reject_relevant,
            key_fields,
        )

        accept_keys = set(accept_map)
        reject_keys = set(reject_map)

        accept_only_keys = accept_keys - reject_keys
        reject_only_keys = reject_keys - accept_keys
        common_keys = accept_keys & reject_keys

        passed = self._evaluate_assertion(
            rule.state_diff.assertion,
            accept_keys,
            reject_keys,
        )

        failed_keys = self._failed_keys(
            rule.state_diff.assertion,
            accept_only_keys,
            reject_only_keys,
            common_keys,
        )
        matched_keys = self._matched_keys(
            rule.state_diff.assertion,
            accept_keys,
            reject_keys,
            accept_only_keys,
            reject_only_keys,
            common_keys,
        )

        failed_observations = self._observations_for_keys(
            failed_keys,
            accept_map,
            reject_map,
        )
        matched_observations = self._observations_for_keys(
            matched_keys,
            accept_map,
            reject_map,
        )

        return StateDiffEvaluationResult(
            passed=passed,
            matched_observations=matched_observations,
            failed_observations=failed_observations,
            accept_only_count=len(accept_only_keys),
            reject_only_count=len(reject_only_keys),
            common_count=len(common_keys),
        )

    def _filter_observations(
        self,
        rule: Rule,
        observations: Iterable[Observation],
    ) -> List[Observation]:
        return [
            observation
            for observation in observations
            if observation.category == rule.source.observation
            and self._matches_conditions(rule.conditions, observation)
        ]

    def _matches_conditions(
        self,
        conditions: Any,
        observation: Observation,
    ) -> bool:
        if conditions.all is not None:
            return all(
                self._evaluate_condition(condition, observation)
                for condition in conditions.all
            )

        if conditions.any is not None:
            return any(
                self._evaluate_condition(condition, observation)
                for condition in conditions.any
            )

        if conditions.not_ is not None:
            return not any(
                self._evaluate_condition(condition, observation)
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
    def _get_field(data: Any, field_path: str) -> Any:
        current = data
        for field in field_path.split("."):
            if isinstance(current, dict):
                current = current.get(field)
            else:
                return None
        return current

    @staticmethod
    def _build_identity_map(
        observations: Iterable[Observation],
        key_fields: List[str],
    ) -> dict[str, list[Observation]]:
        result: dict[str, list[Observation]] = {}

        for observation in observations:
            values = [
                StateDiffEvaluator._get_field(
                    observation.data,
                    field,
                )
                for field in key_fields
            ]

            identity = json.dumps(
                values,
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            )
            result.setdefault(identity, []).append(observation)

        return result

    @staticmethod
    def _evaluate_assertion(
        assertion: str,
        accept_keys: set[str],
        reject_keys: set[str],
    ) -> bool:
        if assertion == "equal":
            return accept_keys == reject_keys

        if assertion == "different":
            return accept_keys != reject_keys

        if assertion == "accept_subset_of_reject":
            return accept_keys <= reject_keys

        if assertion == "reject_subset_of_accept":
            return reject_keys <= accept_keys

        if assertion == "accept_superset_of_reject":
            return accept_keys >= reject_keys

        if assertion == "reject_superset_of_accept":
            return reject_keys >= accept_keys

        raise ValueError(
            f"Unsupported state_diff assertion: {assertion}"
        )

    @staticmethod
    def _failed_keys(
        assertion: str,
        accept_only_keys: set[str],
        reject_only_keys: set[str],
        common_keys: set[str],
    ) -> set[str]:
        if assertion == "equal":
            return accept_only_keys | reject_only_keys

        if assertion in {
            "accept_subset_of_reject",
            "reject_superset_of_accept",
        }:
            return accept_only_keys

        if assertion in {
            "reject_subset_of_accept",
            "accept_superset_of_reject",
        }:
            return reject_only_keys

        if assertion == "different":
            # When the assertion fails, the two states are identical.
            return common_keys

        raise ValueError(
            f"Unsupported state_diff assertion: {assertion}"
        )

    @staticmethod
    def _matched_keys(
        assertion: str,
        accept_keys: set[str],
        reject_keys: set[str],
        accept_only_keys: set[str],
        reject_only_keys: set[str],
        common_keys: set[str],
    ) -> set[str]:
        if assertion == "equal":
            return common_keys

        if assertion == "different":
            return accept_only_keys | reject_only_keys

        if assertion in {
            "accept_subset_of_reject",
            "reject_superset_of_accept",
        }:
            return accept_keys

        if assertion in {
            "reject_subset_of_accept",
            "accept_superset_of_reject",
        }:
            return reject_keys

        raise ValueError(
            f"Unsupported state_diff assertion: {assertion}"
        )

    @staticmethod
    def _observations_for_keys(
        keys: set[str],
        accept_map: dict[str, list[Observation]],
        reject_map: dict[str, list[Observation]],
    ) -> List[Observation]:
        observations: List[Observation] = []

        for key in keys:
            observations.extend(accept_map.get(key, []))
            observations.extend(reject_map.get(key, []))

        return observations