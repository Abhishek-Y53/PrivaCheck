from pathlib import Path
from typing import List

import yaml
from pydantic import ValidationError

from backend.domain.rules.models import Rule


SUPPORTED_OBSERVATIONS = {
    "cookie",
    "network_request",
    "network_response",
    "dom_form",
    "dom_button",
    "dom_input",
    "dom_visible_text",
    "dom_scripts",
    "dom_layout",
    "link",
    "local_storage",
    "session_storage",
    "indexed_db",
    "tls_certificate",
}
SUPPORTED_EVALUATORS = {
    "declarative",
    "state_diff",
    "visual",
    "nlp",
}

SUPPORTED_MATCH_TYPES = {
    "all",
    "any",
    "none",
}


class RuleLoader:
    """
    Loads and validates rule definitions from YAML files.
    """

    def load(self, file_path: str | Path) -> List[Rule]:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Rule file not found: {path}")

        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

        if not isinstance(data, dict):
            raise ValueError("Rule file must contain a top-level mapping.")

        raw_rules = data.get("rules")

        if not isinstance(raw_rules, list):
            raise ValueError("Rule file must contain a 'rules' list.")

        rules: List[Rule] = []

        for raw_rule in raw_rules:
            try:
                rule = Rule.model_validate(raw_rule)
            except ValidationError as exc:
                raise ValueError(
                    f"Invalid rule definition: {exc}"
                ) from exc

            self._validate_rule(rule)

            rules.append(rule)

        self._validate_unique_ids(rules)

        return rules

    def _validate_rule(self, rule: Rule) -> None:
        if rule.source.observation not in SUPPORTED_OBSERVATIONS:
            raise ValueError(
                f"Unsupported observation type: "
                f"{rule.source.observation}"
            )

        if rule.source.match not in SUPPORTED_MATCH_TYPES:
            raise ValueError(
                f"Unsupported match type: {rule.source.match}"
            )

        if rule.evaluator not in SUPPORTED_EVALUATORS:
            raise ValueError(
                f"Unsupported evaluator: {rule.evaluator}"
            )

        if not self._has_conditions(rule):
            raise ValueError(
                f"Rule '{rule.id}' must contain at least one condition."
            )

    @staticmethod
    def _has_conditions(rule: Rule) -> bool:
        return any(
            [
                bool(rule.conditions.all),
                bool(rule.conditions.any),
                bool(rule.conditions.not_),
            ]
        )

    @staticmethod
    def _validate_unique_ids(rules: List[Rule]) -> None:
        ids = [rule.id for rule in rules]

        duplicates = {
            rule_id
            for rule_id in ids
            if ids.count(rule_id) > 1
        }

        if duplicates:
            raise ValueError(
                f"Duplicate rule IDs found: {sorted(duplicates)}"
            )