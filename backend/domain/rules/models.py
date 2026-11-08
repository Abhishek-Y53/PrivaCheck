from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.core import ComplianceStatus, SeverityLevel


class RuleSource(BaseModel):
    observation: str
    match: Literal["all", "any", "none"] = "all"


class RuleCondition(BaseModel):
    field: str
    operator: str
    value: Any


class RuleConditions(BaseModel):
    all: Optional[List[RuleCondition]] = None
    any: Optional[List[RuleCondition]] = None
    not_: Optional[List[RuleCondition]] = Field(default=None, alias="not")

    model_config = ConfigDict(populate_by_name=True)


class RuleResult(BaseModel):
    pass_: ComplianceStatus = Field(alias="pass")
    fail: ComplianceStatus

    model_config = ConfigDict(populate_by_name=True)


class StateDiffConfig(BaseModel):
    key_fields: List[str] = Field(min_length=1)
    assertion: Literal[
        "equal",
        "different",
        "accept_subset_of_reject",
        "reject_subset_of_accept",
        "accept_superset_of_reject",
        "reject_superset_of_accept",
    ] = "equal"


class RuleApplicability(BaseModel):
    """Defines when a rule should be evaluated."""

    observation: str
    conditions: RuleConditions


class Rule(BaseModel):
    id: str
    name: str
    description: str
    category: str
    source: RuleSource
    evaluator: str
    conditions: RuleConditions
    result: RuleResult
    applicability: Optional[RuleApplicability] = None
    state_diff: Optional[StateDiffConfig] = None
    severity: SeverityLevel
    recommendation: Optional[str] = None
