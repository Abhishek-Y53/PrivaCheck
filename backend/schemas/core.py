from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from enum import Enum

class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

class ComplianceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    MANUAL_REVIEW = "MANUAL_REVIEW"

# 1. This represents raw data found by the crawler
class Observation(BaseModel):
    category: str = Field(description="e.g., 'cookie', 'network_request', 'dom_element'")
    source_url: str
    timestamp: float
    data: Dict[str, Any] = Field(description="The actual data, like cookie values or HTML snippets")

# 2. This represents the final output of a single GDPR check
class CheckResult(BaseModel):
    check_id: str = Field(description="e.g., 'GDPR-001'")
    name: str
    status: ComplianceStatus
    severity: SeverityLevel
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    explanation: str
    recommendation: Optional[str] = None
    evidence: List[Observation] = [] # The crawler observations that triggered this result


class ScanReport(BaseModel):
    scan_id: str
    target_url: str
    overall_status: ComplianceStatus
    total_checks: int
    passed_checks: int
    failed_checks: int
    risk_score: float = Field(description="0-100 score, higher is worse")
    issues: List[CheckResult]
    metadata: Dict[str, Any] = Field(description="Browser version, plugins, etc.")
    created_at: float
