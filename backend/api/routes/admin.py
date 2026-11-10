"""Private administration endpoints. The normal /scans routes remain owner-only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.admin_schemas import (
    AdminAuditListResponse, AdminAuditResponse, AdminScanListResponse,
    AdminScanResponse, AdminUserResponse, AdmissionEntryResponse,
    AdmissionListResponse, ChangeRoleRequest, ChangeStatusRequest,
    SetAdmissionRequest, UserListResponse,
)
from backend.api.dependencies.auth import get_current_user, require_csrf, session_cookie_name
from backend.api.schemas import ScanReportResponse
from backend.api.services.admin_service import audit, change_user, set_admission, user_response
from backend.api.services.async_scan_service import AsyncScanService, _safe_public_url
from backend.api.services.auth_service import hash_session_token
from backend.infrastructure.database.models.admin_audit_log import AdminAuditLog
from backend.infrastructure.database.models.platform_access import PlatformAccessDomain, PlatformAccessEmail
from backend.infrastructure.database.models.scan import Scan
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession
from backend.infrastructure.database.repositories.check_result_repository import CheckResultRepository
from backend.infrastructure.database.session import get_db
from backend.schemas.core import CheckResult

router = APIRouter(prefix="/admin", tags=["Administration"])


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Administrator permission is required.")
    return user


def require_recent_admin(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    """Sensitive changes need a recently established Google-linked session.

    The user can sign out and sign in again to reauthenticate. This is not a
    cached browser check; the server checks the revocable DB session row.
    """
    token = request.cookies.get(session_cookie_name())
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    created_at = db.scalar(select(UserSession.created_at).where(
        UserSession.user_id == admin.id,
        UserSession.token_hash == hash_session_token(token),
        UserSession.revoked_at.is_(None),
    ))
    if created_at is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created_at > timedelta(minutes=30):
        raise HTTPException(
            status_code=403,
            detail="Recent Google sign-in required. Sign out and sign in again before changing administrator settings.",
        )
    return admin


@router.get("/users", response_model=UserListResponse)
def users(
    response: Response,
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListResponse:
    no_store(response)
    stmt = select(User)
    count_stmt = select(func.count(User.id))
    if q.strip():
        # Literal substring match, not a caller-supplied SQL wildcard.
        needle = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        condition = User.email.ilike(f"%{needle}%", escape="\\")
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = int(db.scalar(count_stmt) or 0)
    records = db.scalars(stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit).offset(offset)).all()
    return UserListResponse(items=[user_response(record) for record in records], total=total, limit=limit, offset=offset)


@router.post("/users/{user_id}/role", response_model=AdminUserResponse)
def change_role(
    user_id: UUID,
    payload: ChangeRoleRequest,
    response: Response,
    _csrf: None = Depends(require_csrf),
    admin: User = Depends(require_recent_admin),
    db: Session = Depends(get_db),
) -> AdminUserResponse:
    no_store(response)
    return change_user(db, admin, user_id, field="role", value=payload.role)


@router.post("/users/{user_id}/status", response_model=AdminUserResponse)
def change_status(
    user_id: UUID,
    payload: ChangeStatusRequest,
    response: Response,
    _csrf: None = Depends(require_csrf),
    admin: User = Depends(require_recent_admin),
    db: Session = Depends(get_db),
) -> AdminUserResponse:
    no_store(response)
    return change_user(db, admin, user_id, field="is_active", value=payload.is_active)


@router.get("/allowlist", response_model=AdmissionListResponse)
def allowlist(
    response: Response,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdmissionListResponse:
    no_store(response)
    domains = db.scalars(select(PlatformAccessDomain).order_by(PlatformAccessDomain.domain)).all()
    emails = db.scalars(select(PlatformAccessEmail).order_by(PlatformAccessEmail.email)).all()
    return AdmissionListResponse(
        domains=[AdmissionEntryResponse(id=x.id, value=x.domain, is_active=x.is_active, created_at=x.created_at) for x in domains],
        emails=[AdmissionEntryResponse(id=x.id, value=x.email, is_active=x.is_active, created_at=x.created_at) for x in emails],
    )


@router.post("/allowlist/{selector_type}", response_model=AdmissionEntryResponse)
def update_allowlist(
    selector_type: Literal["domains", "emails"],
    payload: SetAdmissionRequest,
    response: Response,
    _csrf: None = Depends(require_csrf),
    admin: User = Depends(require_recent_admin),
    db: Session = Depends(get_db),
) -> AdmissionEntryResponse:
    no_store(response)
    return set_admission(db, admin, selector_type=selector_type, value=payload.value, is_active=payload.is_active)


@router.get("/scans", response_model=AdminScanListResponse)
def all_scans(
    response: Response,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    lifecycle_status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"] | None = None,
) -> AdminScanListResponse:
    no_store(response)
    stmt = select(Scan, User.email).outerjoin(User, Scan.user_id == User.id)
    count_stmt = select(func.count(Scan.id))
    if lifecycle_status:
        stmt = stmt.where(Scan.lifecycle_status == lifecycle_status)
        count_stmt = count_stmt.where(Scan.lifecycle_status == lifecycle_status)
    records = db.execute(stmt.order_by(Scan.created_at.desc(), Scan.id.desc()).limit(limit).offset(offset)).all()
    return AdminScanListResponse(
        items=[AdminScanResponse(scan=AsyncScanService._to_status_response(scan), owner_email=email) for scan, email in records],
        total=int(db.scalar(count_stmt) or 0), limit=limit, offset=offset,
    )


def _admin_scan(db: Session, scan_id: UUID) -> Scan:
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return scan


def _log_report_access(db: Session, actor: User, scan: Scan, action: str) -> None:
    # Reading another user's data must be auditable; own report access is
    # already possible via /scans and is not logged as an admin escalation.
    if scan.user_id != actor.id:
        audit(db, actor=actor.id, action=action, kind="scan", target=str(scan.id),
              after={"owner_user_id": str(scan.user_id) if scan.user_id else None})
        db.commit()


@router.get("/scans/{scan_id}", response_model=AdminScanResponse)
def admin_scan_status(
    scan_id: UUID,
    response: Response,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminScanResponse:
    no_store(response)
    scan = _admin_scan(db, scan_id)
    owner_email = db.scalar(select(User.email).where(User.id == scan.user_id)) if scan.user_id else None
    result = AdminScanResponse(scan=AsyncScanService._to_status_response(scan), owner_email=owner_email)
    return result


@router.get("/scans/{scan_id}/report", response_model=ScanReportResponse)
def admin_scan_report(
    scan_id: UUID,
    response: Response,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ScanReportResponse:
    no_store(response)
    scan = _admin_scan(db, scan_id)
    if scan.lifecycle_status != "COMPLETED" or scan.compliance_status is None or scan.risk_score is None:
        raise HTTPException(status_code=409, detail="The final report is not available.")
    records = CheckResultRepository.list_for_scan(db, scan.id)
    result = ScanReportResponse(
        scan_id=scan.id,
        website=_safe_public_url(scan.website),
        framework=scan.framework,
        ruleset_version_id=getattr(scan, "ruleset_version_id", None),
        lifecycle_status="COMPLETED",
        compliance_status=scan.compliance_status,
        total_checks=scan.total_checks,
        passed_checks=scan.passed_checks,
        failed_checks=scan.failed_checks,
        observation_count=scan.observation_count,
        risk_score=float(scan.risk_score),
        metadata=scan.report_metadata or {},
        results=[CheckResult.model_validate({
            "check_id": record.check_id, "name": record.name,
            "status": record.status, "severity": record.severity,
            "confidence": record.confidence, "explanation": record.explanation,
            "recommendation": record.recommendation, "evidence": record.evidence or [],
        }) for record in records],
        created_at=scan.created_at, started_at=scan.started_at, completed_at=scan.completed_at,
    )
    _log_report_access(db, admin, scan, "report.viewed")
    return result


@router.get("/audit", response_model=AdminAuditListResponse)
def audit_history(
    response: Response,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminAuditListResponse:
    no_store(response)
    count = int(db.scalar(select(func.count(AdminAuditLog.id))) or 0)
    records = db.scalars(select(AdminAuditLog).order_by(
        AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc(),
    ).limit(limit).offset(offset)).all()
    return AdminAuditListResponse(
        items=[AdminAuditResponse.model_validate(row) for row in records],
        total=count, limit=limit, offset=offset,
    )
