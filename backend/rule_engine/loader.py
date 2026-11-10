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
    "page_context",
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
        return self.load_text(path.read_text(encoding="utf-8"))

    def load_text(self, content: str) -> List[Rule]:
        """Parse trusted or administrator-authored YAML without executing code.

        Only the supported, deterministic, declarative subset can be published.
        Regex patterns are length-capped to limit complexity; administrators
        should still avoid expensive regex constructs.
        """
        if not isinstance(content, str) or len(content.encode("utf-8")) > 262144:
            raise ValueError("Ruleset exceeds 256 KiB limit.")
        class NoAliasesLoader(yaml.SafeLoader):
            def compose_node(self, parent, index):
                if self.check_event(yaml.AliasEvent):
                    raise ValueError("YAML aliases are not allowed.")
                return super().compose_node(parent, index)
        try:
            data = yaml.load(content, Loader=NoAliasesLoader)
        except (yaml.YAMLError, RecursionError) as exc:
            raise ValueError("Malformed or excessively complex YAML.") from exc
        if not isinstance(data, dict) or set(data) != {"rules"}:
            raise ValueError("Rules must be a mapping containing only 'rules'.")
        raw_rules = data["rules"]
        if not isinstance(raw_rules, list) or not 1 <= len(raw_rules) <= 200:
            raise ValueError("Rules must contain between 1 and 200 checks.")
        rules: List[Rule] = []
        for raw_rule in raw_rules:
            try:
                rule = Rule.model_validate(raw_rule)
            except ValidationError as exc:
                raise ValueError(f"Invalid rule definition: {exc}") from exc
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

        if len(rule.id) > 96 or len(rule.name) > 200 or len(rule.category) > 64:
            raise ValueError("Rule identifier, name or category is too long.")
        all_conditions = [*(rule.conditions.all or []), *(rule.conditions.any or []), *(rule.conditions.not_ or [])]
        if rule.applicability:
            if rule.applicability.observation not in SUPPORTED_OBSERVATIONS:
                raise ValueError("Unsupported applicability observation.")
            all_conditions += [*(rule.applicability.conditions.all or []), *(rule.applicability.conditions.any or []), *(rule.applicability.conditions.not_ or [])]
        valid_operators = {
            "equals", "not_equals", "contains", "not_contains", "starts_with",
            "ends_with", "exists", "not_exists", "matches", "greater_than",
            "less_than", "in", "not_in",
        }
        for condition in all_conditions:
            if condition.operator not in valid_operators:
                raise ValueError(f"Unsupported operator: {condition.operator}")
            if len(condition.field) > 160 or not condition.field:
                raise ValueError("Condition field is invalid.")
            if condition.operator == "matches":
                if not isinstance(condition.value, str) or len(condition.value) > 1024:
                    raise ValueError("Regex patterns must be strings up to 1024 characters.")
                import re
                try:
                    re.compile(condition.value)
                except re.error as exc:
                    raise ValueError("Invalid regular expression.") from exc
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