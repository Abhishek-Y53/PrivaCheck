"""Application service for asynchronous compliance evaluation and persistence."""

from __future__ import annotations

import logging
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from backend.contracts.task_messages import ComplianceEvaluationRequested
from backend.domain.rules.models import Rule
from backend.infrastructure.database.repositories import (
    CheckResultRepository,
    ObservationRepository,
    ScanRepository,
)
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.database.models.framework import RulesetVersion
from backend.rule_engine.engine import RuleEngine
from backend.rule_engine.framework_registry import (
    FrameworkRegistry,
    UnsupportedFrameworkError as RegistryFrameworkError,
)
from backend.rule_engine.loader import RuleLoader
from backend.rule_engine.scan_evaluator import evaluate_observations
from backend.schemas.core import CrawlerResult, CrawlerStatus, Observation, ScanReport

logger = logging.getLogger(__name__)

FailureCode = Literal[
    "UNSUPPORTED_FRAMEWORK",
    "RULE_LOAD_FAILED",
    "OBSERVATIONS_UNAVAILABLE",
    "EVALUATION_FAILED",
    "COMPLIANCE_INTERNAL_ERROR",
]

_FAILURE_MESSAGES: dict[str, str] = {
    "UNSUPPORTED_FRAMEWORK": "The requested compliance framework is not supported.",
    "RULE_LOAD_FAILED": "The registered framework rules could not be loaded.",
    "OBSERVATIONS_UNAVAILABLE": "The crawler observations are unavailable or inconsistent.",
    "EVALUATION_FAILED": "Compliance evaluation could not be completed.",
    "COMPLIANCE_INTERNAL_ERROR": "The compliance service could not complete this scan.",
}


class EvaluationRejected(RuntimeError):
    """A non-retryable, controlled compliance evaluation rejection."""

    def __init__(self, failure_code: FailureCode) -> None:
        self.failure_code = failure_code
        super().__init__(_FAILURE_MESSAGES[failure_code])

    @property
    def safe_message(self) -> str:
        return _FAILURE_MESSAGES[self.failure_code]


@dataclass(frozen=True)
class EvaluationSnapshot:
    scan_id: UUID
    framework_id: str
    rule_path: Path | None
    rules_yaml: str | None
    crawler_result: CrawlerResult
    observation_count: int


@dataclass(frozen=True)
class EvaluationOutcome:
    status: Literal["completed", "skipped"]
    scan_id: str
    result_count: int = 0
    compliance_status: str | None = None
    risk_score: float | None = None
    reason: str | None = None


def reconstruct_crawler_result(
    *,
    website: str,
    started_at: datetime | None,
    created_at: datetime,
    occurred_at: datetime,
    observation_rows: list[object],
) -> CrawlerResult:
    """Rebuild the report input from the scan row and staged observation rows.

    M3.4B currently persists observations, not the entire CrawlerResult. The
    original requested URL and start time come from ``scans``; the final URL is
    recovered from the crawler's ``page_context`` evidence. The completion
    timestamp is the validated timestamp on the compliance handoff message.
    """
    observations: list[Observation] = []
    final_url = website

    for row in observation_rows:
        row_data = getattr(row, "data", None)
        if not isinstance(row_data, dict):
            raise EvaluationRejected("OBSERVATIONS_UNAVAILABLE")
        try:
            observed_at = getattr(row, "observed_at")
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=timezone.utc)
            observation = Observation(
                category=str(getattr(row, "category")),
                source_url=str(getattr(row, "source_url")),
                timestamp=float(observed_at.timestamp()),
                data=row_data,
            )
        except Exception as exc:
            raise EvaluationRejected("OBSERVATIONS_UNAVAILABLE") from exc
        observations.append(observation)

        if observation.category == "page_context":
            candidate = observation.data.get("final_url")
            if isinstance(candidate, str) and candidate.strip():
                final_url = candidate

    start_time = started_at or created_at
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)

    started_timestamp = start_time.timestamp()
    completed_timestamp = max(started_timestamp, occurred_at.timestamp())

    return CrawlerResult(
        target_url=website,
        final_url=final_url,
        observations=observations,
        started_at=started_timestamp,
        completed_at=completed_timestamp,
        status=CrawlerStatus.COMPLETED,
        error=None,
    )


class ComplianceEvaluationService:
    """Load staged evidence, evaluate allowlisted rules and atomically persist."""

    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        rule_loader: RuleLoader | None = None,
        rule_engine: RuleEngine | None = None,
        framework_registry: FrameworkRegistry | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.rule_loader = rule_loader or RuleLoader()
        self.rule_engine = rule_engine or RuleEngine()
        self.framework_registry = framework_registry or FrameworkRegistry()

    def evaluate(self, message: ComplianceEvaluationRequested) -> EvaluationOutcome:
        """Evaluate one message. A duplicate after completion is a safe no-op."""
        snapshot = self._load_snapshot(message)
        if snapshot is None:
            return EvaluationOutcome(
                status="skipped",
                scan_id=str(message.scan_id),
                reason="scan_is_terminal",
            )

        try:
            rules: list[Rule] = (self.rule_loader.load_text(snapshot.rules_yaml)
                                 if snapshot.rules_yaml is not None else self.rule_loader.load(snapshot.rule_path))
            if not rules:
                raise ValueError("The registered rule file contains no rules")
        except Exception as exc:
            logger.exception(
                "Could not load allowlisted rules for framework=%s scan_id=%s",
                snapshot.framework_id,
                message.scan_id,
            )
            raise EvaluationRejected("RULE_LOAD_FAILED") from exc

        try:
            report = evaluate_observations(
                snapshot.crawler_result,
                rules,
                framework=snapshot.framework_id,
                rule_engine=self.rule_engine,
                # M3.4B does not persist TwoPassResult metadata. State-diff rules
                # therefore become MANUAL_REVIEW, never an inferred PASS/FAIL.
                two_pass_result=None,
                scan_id=str(snapshot.scan_id),
            )
        except Exception as exc:
            logger.exception("Report evaluation failed for scan_id=%s", message.scan_id)
            raise EvaluationRejected("EVALUATION_FAILED") from exc

        return self._persist_report(message, report, snapshot.observation_count)

    def _load_snapshot(
        self,
        message: ComplianceEvaluationRequested,
    ) -> EvaluationSnapshot | None:
        """Read and validate scan/evidence under a short row-lock transaction."""
        with self.session_factory() as session:
            with session.begin():
                scan = ScanRepository.get_by_id_for_update(session, message.scan_id)
                if scan is None:
                    raise EvaluationRejected("COMPLIANCE_INTERNAL_ERROR")

                lifecycle = str(scan.lifecycle_status).upper()
                if lifecycle in {"COMPLETED", "FAILED", "CANCELLED"}:
                    return None
                if lifecycle != "RUNNING":
                    raise EvaluationRejected("EVALUATION_FAILED")

                stored_framework = str(scan.framework).strip().lower()
                requested_framework = message.framework_id.strip().lower()
                if stored_framework != requested_framework:
                    raise EvaluationRejected("UNSUPPORTED_FRAMEWORK")

                pinned_id = getattr(scan, "ruleset_version_id", None)
                if pinned_id != message.ruleset_version_id:
                    # Message and durable scan record must select the same
                    # immutable ruleset even if a new version is published.
                    raise EvaluationRejected("UNSUPPORTED_FRAMEWORK")
                if pinned_id is not None:
                    version = session.get(RulesetVersion, pinned_id)
                    if (version is None or version.status != "PUBLISHED"
                            or version.framework_slug != stored_framework
                            or hashlib.sha256(version.yaml_content.encode("utf-8")).hexdigest() != version.sha256):
                        raise EvaluationRejected("RULE_LOAD_FAILED")
                    framework_id, rule_path, rules_yaml = stored_framework, None, version.yaml_content
                else:
                    # Legacy scan queued before governance migration, with no
                    # version identity. The original registered GDPR path only.
                    try:
                        framework_id, rule_path = self.framework_registry.resolve(message.framework_id)
                    except RegistryFrameworkError as exc:
                        raise EvaluationRejected("UNSUPPORTED_FRAMEWORK") from exc
                    rules_yaml = None

                rows = ObservationRepository.list_for_scan(session, message.scan_id)
                if (
                    message.observation_count <= 0
                    or len(rows) != message.observation_count
                ):
                    raise EvaluationRejected("OBSERVATIONS_UNAVAILABLE")

                crawler_result = reconstruct_crawler_result(
                    website=scan.website,
                    started_at=scan.started_at,
                    created_at=scan.created_at,
                    occurred_at=message.occurred_at,
                    observation_rows=rows,
                )
                return EvaluationSnapshot(
                    scan_id=scan.id,
                    framework_id=framework_id,
                    rule_path=rule_path,
                    rules_yaml=rules_yaml,
                    crawler_result=crawler_result,
                    observation_count=len(rows),
                )

    def _persist_report(
        self,
        message: ComplianceEvaluationRequested,
        report: ScanReport,
        observation_count: int,
    ) -> EvaluationOutcome:
        """Commit findings, summary, completion and staging cleanup atomically.

        The second FOR UPDATE check serializes duplicate workers. If another
        delivery completed first, this delivery returns without overwriting it.
        Any exception rolls the entire transaction back and leaves observations
        available for a later retry.
        """
        with self.session_factory() as session:
            with session.begin():
                scan = ScanRepository.get_by_id_for_update(session, message.scan_id)
                if scan is None:
                    raise EvaluationRejected("COMPLIANCE_INTERNAL_ERROR")

                lifecycle = str(scan.lifecycle_status).upper()
                if lifecycle in {"COMPLETED", "FAILED", "CANCELLED"}:
                    return EvaluationOutcome(
                        status="skipped",
                        scan_id=str(message.scan_id),
                        reason="scan_became_terminal_during_evaluation",
                    )
                if lifecycle != "RUNNING":
                    raise EvaluationRejected("EVALUATION_FAILED")

                # Guard against evidence being modified or removed mid-evaluation.
                current_count = ObservationRepository.count_for_scan(
                    session,
                    message.scan_id,
                )
                if current_count != observation_count:
                    raise EvaluationRejected("OBSERVATIONS_UNAVAILABLE")

                CheckResultRepository.replace_for_scan(
                    session,
                    message.scan_id,
                    report.issues,
                )
                ScanRepository.update_report_summary(
                    session,
                    message.scan_id,
                    compliance_status=self._enum_value(report.overall_status),
                    total_checks=report.total_checks,
                    passed_checks=report.passed_checks,
                    failed_checks=report.failed_checks,
                    observation_count=observation_count,
                    risk_score=float(report.risk_score),
                    report_metadata=report.metadata,
                )
                # Staging rows are removed only after a report is ready to commit.
                ObservationRepository.delete_for_scan(session, message.scan_id)
                ScanRepository.set_lifecycle_status(
                    session,
                    message.scan_id,
                    "COMPLETED",
                )

        return EvaluationOutcome(
            status="completed",
            scan_id=str(message.scan_id),
            result_count=report.total_checks,
            compliance_status=self._enum_value(report.overall_status),
            risk_score=float(report.risk_score),
        )

    def mark_failed(self, scan_id: UUID | str, failure_code: FailureCode) -> None:
        """Persist only a controlled error; retain evidence until its TTL expires."""
        safe_message = _FAILURE_MESSAGES[failure_code]
        with self.session_factory() as session:
            with session.begin():
                scan = ScanRepository.get_by_id_for_update(session, scan_id)
                if scan is None:
                    return
                if str(scan.lifecycle_status).upper() in {"QUEUED", "RUNNING"}:
                    ScanRepository.set_lifecycle_status(
                        session,
                        scan_id,
                        "FAILED",
                        error_message=safe_message,
                    )

    @staticmethod
    def _enum_value(value: object) -> str:
        return str(getattr(value, "value", value)).upper()
