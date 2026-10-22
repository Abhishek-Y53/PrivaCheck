"""Build safe, explainable ScanReport objects from crawler and rule results.

Risk scores are deterministic project heuristics, not legal conclusions or
statistically calibrated probabilities.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from time import time
from typing import Iterable
from urllib.parse import SplitResult, urlsplit, urlunsplit
from uuid import uuid4

from backend.schemas.core import (
    CheckResult,
    ComplianceStatus,
    CrawlerResult,
    ScanReport,
)

# Higher weight means a more consequential rule if it is not satisfied.
_SEVERITY_WEIGHTS = {
    "CRITICAL": 5.0,
    "HIGH": 4.0,
    "MEDIUM": 3.0,
    "LOW": 2.0,
    "INFO": 1.0,
}
_STATUS_RISK_FACTORS = {
    "PASS": 0.0,
    "FAIL": 1.0,
    "WARNING": 0.5,
    "MANUAL_REVIEW": 0.25,
    # Not applicable checks do not contribute to either side of the score.
    "NOT_APPLICABLE": 0.0,
}
_NOT_APPLICABLE_STATUSES = {"NOT_APPLICABLE", "SKIPPED"}
_SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-access-token",
}
_SECRET_FIELD_NAMES = {
    "authorization",
    "proxy-authorization",
    "password",
    "passwd",
    "secret",
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "client_secret",
    "csrf_token",
    "token",
    "session_token",
    "jwt",
    "api_token",
    "private_key",
}
_REDACTED = "[REDACTED]"


def _enum_value(value: object) -> str:
    """Return a stable string for a plain string or an Enum value."""
    enum_value = getattr(value, "value", value)
    return str(enum_value).upper()


def _safe_url(value: str) -> str:
    """Remove query values and fragments before putting a URL in a report."""
    try:
        parsed: SplitResult = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return value
        # The crawler URL policy rejects userinfo; rebuild the authority from
        # hostname/port rather than preserving arbitrary user-supplied netloc.
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        try:
            port = parsed.port
        except ValueError:
            port = None
        default_port = 80 if parsed.scheme.lower() == "http" else 443
        authority = hostname if port in (None, default_port) else f"{hostname}:{port}"
        return urlunsplit((parsed.scheme.lower(), authority, parsed.path, "", ""))
    except (TypeError, ValueError):
        return "[URL REDACTED]"


def _redact_headers(headers: object) -> object:
    """Redact credential-bearing HTTP headers while preserving header names."""
    if isinstance(headers, dict):
        cleaned: dict[str, object] = {}
        for name, value in headers.items():
            if str(name).lower().strip() in _SENSITIVE_HEADERS:
                cleaned[str(name)] = _REDACTED
            else:
                cleaned[str(name)] = _redact_nested(value, key=str(name))
        return cleaned
    if isinstance(headers, list):
        return [_redact_headers(item) if isinstance(item, dict) else _redact_nested(item) for item in headers]
    return _redact_nested(headers)


def _redact_nested(value: object, key: str | None = None) -> object:
    """Redact obvious secret fields and URL query data in nested evidence."""
    if key is not None and key.lower().replace("-", "_") in _SECRET_FIELD_NAMES:
        return _REDACTED

    if isinstance(value, dict):
        cleaned: dict[str, object] = {}
        for child_key, child_value in value.items():
            lowered = str(child_key).lower()
            if lowered == "headers":
                cleaned[str(child_key)] = _redact_headers(child_value)
            elif lowered in {"url", "source_url", "final_url", "href", "action_url", "request_url", "document_url"} and isinstance(child_value, str):
                cleaned[str(child_key)] = _safe_url(child_value)
            else:
                cleaned[str(child_key)] = _redact_nested(child_value, key=str(child_key))
        return cleaned
    if isinstance(value, list):
        return [_redact_nested(item) for item in value]
    return value


def sanitize_check_result(result: CheckResult) -> CheckResult:
    """Return a copy with secrets and URL query values removed from evidence.

    Rule evaluation must run on the original, unredacted observations. Call
    this only when preparing a report/API response, never before evaluation.
    """
    safe_result = result.model_copy(deep=True)
    safe_evidence = []
    for observation in safe_result.evidence:
        data = deepcopy(observation.data)
        category = observation.category.lower()

        # These values can carry identifiers, session tokens or personal data;
        # their names and metadata remain useful as compliance evidence.
        if category in {"cookie", "local_storage", "session_storage", "indexed_db"}:
            if "value" in data:
                data["value"] = _REDACTED

        data = _redact_nested(data)
        safe_evidence.append(
            observation.model_copy(
                update={
                    "source_url": _safe_url(observation.source_url),
                    "data": data,
                },
                deep=True,
            )
        )

    safe_result.evidence = safe_evidence
    return safe_result


def calculate_risk_score(results: Iterable[CheckResult]) -> float:
    """Calculate a severity-weighted concern score between 0 and 100.

    PASS contributes zero risk. FAIL, WARNING and MANUAL_REVIEW contribute
    1.0, 0.5 and 0.25 of that check's severity weight respectively. Checks
    marked NOT_APPLICABLE/SKIPPED are excluded. If no checks are applicable,
    the score is zero while the overall report status remains MANUAL_REVIEW.
    """
    weighted_concern = 0.0
    applicable_weight = 0.0

    for result in results:
        status = _enum_value(result.status)
        if status in _NOT_APPLICABLE_STATUSES:
            continue

        severity_weight = _SEVERITY_WEIGHTS.get(_enum_value(result.severity), 1.0)
        applicable_weight += severity_weight
        weighted_concern += severity_weight * _STATUS_RISK_FACTORS.get(status, 0.25)

    if applicable_weight == 0.0:
        return 0.0
    return round(max(0.0, min(100.0, 100.0 * weighted_concern / applicable_weight)), 2)


def determine_overall_status(
    crawler_result: CrawlerResult,
    results: Iterable[CheckResult],
) -> ComplianceStatus:
    """Aggregate rule outcomes conservatively; never treat an empty scan as PASS."""
    result_list = list(results)
    statuses = [_enum_value(result.status) for result in result_list]

    if "FAIL" in statuses:
        return ComplianceStatus.FAIL

    crawler_status = _enum_value(crawler_result.status)
    if crawler_status != "COMPLETED":
        return ComplianceStatus.MANUAL_REVIEW

    applicable_statuses = [s for s in statuses if s not in _NOT_APPLICABLE_STATUSES]
    if not applicable_statuses:
        return ComplianceStatus.MANUAL_REVIEW
    if "MANUAL_REVIEW" in applicable_statuses:
        return ComplianceStatus.MANUAL_REVIEW
    if "WARNING" in applicable_statuses:
        return ComplianceStatus.WARNING
    if all(status == "PASS" for status in applicable_statuses):
        return ComplianceStatus.PASS
    return ComplianceStatus.MANUAL_REVIEW


def build_scan_report(
    crawler_result: CrawlerResult,
    check_results: Iterable[CheckResult],
    *,
    framework: str,
    scan_id: str | None = None,
) -> ScanReport:
    """Aggregate a crawler run and its rule results into a safe ScanReport."""
    raw_results = list(check_results)
    safe_results = [sanitize_check_result(result) for result in raw_results]

    status_counts = Counter(_enum_value(result.status) for result in raw_results)
    observation_counts = Counter(
        observation.category for observation in crawler_result.observations
    )
    applicable_count = sum(
        1
        for result in raw_results
        if _enum_value(result.status) not in _NOT_APPLICABLE_STATUSES
    )

    # ScanReport.issues is the project's existing list of CheckResult objects.
    # Keep all rule outcomes there so PASS as well as issue evidence remains
    # available; metadata separately identifies the non-PASS finding count.
    target_url = _safe_url(crawler_result.target_url)
    final_url = _safe_url(crawler_result.final_url) if crawler_result.final_url else ""

    created_at = time()
    metadata = {
        "framework": framework,
        "crawler_status": _enum_value(crawler_result.status),
        "crawl_duration_seconds": round(
            max(0.0, crawler_result.completed_at - crawler_result.started_at), 3
        ),
        "observation_count": len(crawler_result.observations),
        "observations_by_category": dict(sorted(observation_counts.items())),
        "result_counts": dict(sorted(status_counts.items())),
        "applicable_checks": applicable_count,
        "non_pass_findings": sum(
            1
            for result in raw_results
            if _enum_value(result.status) not in {"PASS", *_NOT_APPLICABLE_STATUSES}
        ),
        "final_url": final_url,
        "crawler_error_present": bool(crawler_result.error),
        "risk_scoring_policy": {
            "version": "severity_weighted_v1",
            "severity_weights": dict(_SEVERITY_WEIGHTS),
            "status_factors": dict(_STATUS_RISK_FACTORS),
            "interpretation": "Heuristic score; not a probability or legal determination.",
        },
    }

    return ScanReport(
        scan_id=scan_id or str(uuid4()),
        target_url=target_url,
        overall_status=determine_overall_status(crawler_result, raw_results),
        total_checks=len(raw_results),
        passed_checks=status_counts.get("PASS", 0),
        failed_checks=status_counts.get("FAIL", 0),
        risk_score=calculate_risk_score(raw_results),
        issues=safe_results,
        metadata=metadata,
        created_at=created_at,
    )
