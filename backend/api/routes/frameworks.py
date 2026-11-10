"""Normal-user framework discovery and restricted admin governance APIs."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.dependencies.auth import get_current_user, require_csrf
from backend.api.routes.admin import no_store, require_admin, require_recent_admin
from backend.api.services.framework_service import (
    admin_framework, create_framework, current_version, edit_framework,
    is_allowed, public_framework, publish, replace_access, require_framework,
    save_draft, set_archived, validate_rules,
)
from backend.infrastructure.database.models.framework import ComplianceFramework, RulesetVersion
from backend.rule_engine.loader import RuleLoader, SUPPORTED_OBSERVATIONS
from backend.rule_engine.engine import RuleEngine
from backend.schemas.core import Observation, ComplianceStatus
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.session import get_db

router = APIRouter(tags=["Compliance Frameworks"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrameworkData(Strict):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)


class NewFramework(FrameworkData):
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")


class DraftInput(Strict):
    yaml_content: str = Field(min_length=5, max_length=262144)
    version_id: UUID | None = None


class AccessInput(Strict):
    everyone: bool = False
    domains: list[str] = Field(default_factory=list, max_length=100)
    emails: list[str] = Field(default_factory=list, max_length=100)


class ArchiveInput(Strict):
    archived: bool


class FixtureObservation(Strict):
    category: str = Field(min_length=1, max_length=64)
    data: dict[str, Any]


class PreviewInput(Strict):
    yaml_content: str = Field(min_length=5, max_length=262144)
    observations: list[FixtureObservation] = Field(min_length=1, max_length=25)


@router.post("/admin/frameworks/preview")
def admin_preview(payload: PreviewInput, response: Response,
                  _csrf: None = Depends(require_csrf), _admin: User = Depends(require_admin)) -> dict:
    """Evaluate tiny, synthetic sample observations; never treat as a real scan."""
    import json
    no_store(response)
    validate_rules(payload.yaml_content)
    if any(item.category not in SUPPORTED_OBSERVATIONS or len(json.dumps(item.data)) > 4096
           for item in payload.observations):
        raise HTTPException(status_code=422, detail="Sample observations must use supported categories and <=4 KiB of JSON data each.")
    rules = RuleLoader().load_text(payload.yaml_content)
    observations = [Observation(category=o.category, source_url="https://example.com/",
                                timestamp=0.0, data=o.data) for o in payload.observations]
    engine = RuleEngine()
    summary = []
    for rule in rules:
        try:
            result = engine.evaluate_rule(rule, observations)
            status = str(getattr(result.status, "value", result.status))
        except Exception:
            status = "MANUAL_REVIEW"
        summary.append({"id": rule.id, "name": rule.name, "status": status})
    return {"sample_only": True, "rule_count": len(summary), "results": summary,
            "warning": "Synthetic observations are not a website scan; missing evidence can produce misleading results."}


@router.get("/frameworks")
def available_frameworks(response: Response, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    no_store(response)
    rows = db.scalars(select(ComplianceFramework).where(ComplianceFramework.status == "PUBLISHED").order_by(ComplianceFramework.name)).all()
    return [public_framework(fw) for fw in rows if is_allowed(db, current_user, fw.slug)]


@router.get("/frameworks/{slug}")
def framework_info(slug: str, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    no_store(response)
    return public_framework(require_framework(db, user, slug))


@router.get("/admin/frameworks")
def list_admin_frameworks(response: Response, _admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    no_store(response)
    return [admin_framework(db, fw) for fw in db.scalars(select(ComplianceFramework).order_by(ComplianceFramework.slug)).all()]


@router.post("/admin/frameworks", status_code=201)
def admin_create_framework(payload: NewFramework, response: Response, _csrf: None = Depends(require_csrf), admin: User = Depends(require_recent_admin), db: Session = Depends(get_db)) -> dict:
    no_store(response)
    return create_framework(db, admin, payload.slug, payload.name, payload.description)


@router.put("/admin/frameworks/{slug}")
def admin_edit_framework(slug: str, payload: FrameworkData, response: Response, _csrf: None = Depends(require_csrf), admin: User = Depends(require_recent_admin), db: Session = Depends(get_db)) -> dict:
    no_store(response)
    return edit_framework(db, admin, slug, name=payload.name, description=payload.description)


@router.post("/admin/frameworks/{slug}/archive")
def admin_archive_framework(slug: str, payload: ArchiveInput, response: Response, _csrf: None = Depends(require_csrf), admin: User = Depends(require_recent_admin), db: Session = Depends(get_db)) -> dict:
    no_store(response)
    return set_archived(db, admin, slug, payload.archived)


@router.put("/admin/frameworks/{slug}/access")
def admin_access(slug: str, payload: AccessInput, response: Response, _csrf: None = Depends(require_csrf), admin: User = Depends(require_recent_admin), db: Session = Depends(get_db)) -> dict:
    no_store(response)
    return replace_access(db, admin, slug, everyone=payload.everyone, domains=payload.domains, emails=payload.emails)


@router.post("/admin/frameworks/validate")
def admin_validate(payload: DraftInput, response: Response, _csrf: None = Depends(require_csrf), _admin: User = Depends(require_admin)) -> dict:
    no_store(response)
    return {"valid": True, "rule_count": validate_rules(payload.yaml_content)}


@router.post("/admin/frameworks/{slug}/draft")
def admin_save_draft(slug: str, payload: DraftInput, response: Response, _csrf: None = Depends(require_csrf), admin: User = Depends(require_recent_admin), db: Session = Depends(get_db)) -> dict:
    no_store(response)
    return save_draft(db, admin, slug, payload.yaml_content, payload.version_id)


@router.get("/admin/frameworks/{slug}/versions/{version_id}")
def admin_get_version(slug: str, version_id: UUID, response: Response, _admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    no_store(response)
    version = db.get(RulesetVersion, version_id)
    if version is None or version.framework_slug != slug:
        raise HTTPException(status_code=404, detail="Ruleset version not found.")
    return {"id": str(version.id), "version_no": version.version_no, "status": version.status,
            "rule_count": version.rule_count, "sha256": version.sha256, "yaml_content": version.yaml_content}


@router.post("/admin/frameworks/{slug}/publish/{version_id}")
def admin_publish(slug: str, version_id: UUID, response: Response, _csrf: None = Depends(require_csrf), admin: User = Depends(require_recent_admin), db: Session = Depends(get_db)) -> dict:
    no_store(response)
    return publish(db, admin, slug, version_id)
