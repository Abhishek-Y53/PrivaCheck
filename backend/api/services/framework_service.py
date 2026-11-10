"""Framework governance, authorization, publishing, and legacy compatibility.

Permissions are queried from PostgreSQL on each request; no browser-side
visibility or session-cached grant is treated as authorization.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.services.admin_service import _governance_lock, _validate_actor, audit, normalized_domain
from backend.api.services.auth_service import normalize_email
from backend.infrastructure.database.models.framework import ComplianceFramework, FrameworkAccessRule, RulesetVersion
from backend.infrastructure.database.models.user import User
from backend.rule_engine.loader import RuleLoader

SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def is_allowed(db: Session, user: User, framework_slug: str) -> bool:
    """Published and active framework + OR selector match, ADMIN bypasses selectors.

    Archived/draft frameworks never permit new user scans, including for admins.
    Admins may still inspect historical reports via /admin/scans.
    """
    fw = db.get(ComplianceFramework, framework_slug)
    if fw is None or fw.status != "PUBLISHED" or fw.active_version_id is None:
        return False
    if user.role == "ADMIN":
        return True
    if not user.is_active:
        return False
    selectors = db.scalars(select(FrameworkAccessRule).where(
        FrameworkAccessRule.framework_slug == fw.slug, FrameworkAccessRule.is_active.is_(True),
    )).all()
    address = user.email.strip().lower()
    domain = address.rsplit("@", 1)[-1] if "@" in address else ""
    hd = (user.google_hd or "").strip().lower()
    for rule in selectors:
        if rule.selector_type == "EVERYONE":
            return True
        if rule.selector_type == "EMAIL" and rule.selector_value == address:
            return True
        if rule.selector_type == "DOMAIN" and hd and hd == domain and rule.selector_value == hd:
            return True
    return False


def require_framework(db: Session, user: User, slug: str) -> ComplianceFramework:
    fw = db.get(ComplianceFramework, slug)
    if fw is None or not is_allowed(db, user, slug):
        # Avoid exposing existence of private/archived frameworks.
        raise HTTPException(status_code=404, detail="Framework not available.")
    return fw


def current_version(db: Session, fw: ComplianceFramework) -> RulesetVersion:
    if fw.active_version_id is None:
        raise HTTPException(status_code=409, detail="The framework has no published ruleset.")
    version = db.get(RulesetVersion, fw.active_version_id)
    if version is None or version.framework_slug != fw.slug or version.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="Published framework version is unavailable.")
    return version


def public_framework(fw: ComplianceFramework) -> dict:
    return {
        "id": fw.slug, "name": fw.name, "description": fw.description,
        "enabled": fw.status == "PUBLISHED" and fw.active_version_id is not None,
    }


def admin_framework(db: Session, fw: ComplianceFramework) -> dict:
    versions = db.scalars(select(RulesetVersion).where(RulesetVersion.framework_slug == fw.slug).order_by(RulesetVersion.version_no.desc())).all()
    rules = db.scalars(select(FrameworkAccessRule).where(
        FrameworkAccessRule.framework_slug == fw.slug, FrameworkAccessRule.is_active.is_(True),
    ).order_by(FrameworkAccessRule.selector_type, FrameworkAccessRule.selector_value)).all()
    return {
        "id": fw.slug, "name": fw.name, "description": fw.description, "status": fw.status,
        "active_version_id": str(fw.active_version_id) if fw.active_version_id else None,
        "versions": [{"id": str(v.id), "version_no": v.version_no, "status": v.status, "rule_count": v.rule_count,
                      "sha256": v.sha256, "created_at": v.created_at.isoformat(),
                      "published_at": v.published_at.isoformat() if v.published_at else None} for v in versions],
        "access": {
            "everyone": any(r.selector_type == "EVERYONE" for r in rules),
            "domains": [r.selector_value for r in rules if r.selector_type == "DOMAIN"],
            "emails": [r.selector_value for r in rules if r.selector_type == "EMAIL"],
        },
    }


def validate_rules(content: str) -> int:
    try:
        rules = RuleLoader().load_text(content)
    except (ValueError, UnicodeError, TypeError) as exc:
        # Errors from schema may contain YAML snippets; never reflect raw YAML
        # to arbitrary clients. All callers are ADMIN but still sanitize.
        raise HTTPException(status_code=422, detail=f"Ruleset validation failed: {str(exc)[:450]}") from None
    # The rule engine currently persists a full TwoPassResult only in memory;
    # until durable state-diff support exists, prevent publishing rules that
    # could silently become MANUAL_REVIEW after asynchronous evaluation.
    if any(rule.evaluator != "declarative" for rule in rules):
        raise HTTPException(status_code=422, detail="Only declarative rules can currently be published.")
    return len(rules)


def create_framework(db: Session, admin: User, slug: str, name: str, description: str) -> dict:
    if not SLUG_PATTERN.fullmatch(slug):
        raise HTTPException(status_code=422, detail="Framework ID must be 2–64 lowercase letters, numbers, _ or -, starting with a letter.")
    _governance_lock(db)
    _validate_actor(db, admin)
    if db.get(ComplianceFramework, slug):
        raise HTTPException(status_code=409, detail="Framework ID already exists.")
    fw = ComplianceFramework(slug=slug, name=name, description=description, status="DRAFT", created_by=admin.id)
    db.add(fw)
    db.flush()
    audit(db, actor=admin.id, action="framework.created", kind="framework", target=slug,
          after={"name": name, "status": "DRAFT"})
    db.commit()
    return admin_framework(db, fw)


def edit_framework(db: Session, admin: User, slug: str, *, name: str, description: str) -> dict:
    _governance_lock(db)
    _validate_actor(db, admin)
    fw = db.get(ComplianceFramework, slug)
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found.")
    before = {"name": fw.name, "description": fw.description}
    fw.name, fw.description = name, description
    audit(db, actor=admin.id, action="framework.metadata.updated", kind="framework", target=slug,
          before=before, after={"name": name, "description": description})
    db.commit()
    return admin_framework(db, fw)


def set_archived(db: Session, admin: User, slug: str, archived: bool) -> dict:
    _governance_lock(db)
    _validate_actor(db, admin)
    fw = db.get(ComplianceFramework, slug)
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found.")
    before = fw.status
    fw.status = "ARCHIVED" if archived else ("PUBLISHED" if fw.active_version_id else "DRAFT")
    audit(db, actor=admin.id, action="framework.archive.changed", kind="framework", target=slug,
          before={"status": before}, after={"status": fw.status})
    db.commit()
    return admin_framework(db, fw)


def save_draft(db: Session, admin: User, slug: str, content: str, version_id: UUID | None = None) -> dict:
    _governance_lock(db)
    _validate_actor(db, admin)
    fw = db.scalar(select(ComplianceFramework).where(ComplianceFramework.slug == slug).with_for_update())
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found.")
    count = validate_rules(content)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if version_id is not None:
        version = db.get(RulesetVersion, version_id)
        if not version or version.framework_slug != slug:
            raise HTTPException(status_code=404, detail="Draft not found.")
        if version.status != "DRAFT":
            raise HTTPException(status_code=409, detail="Published versions are immutable. Create a new draft.")
        version.yaml_content, version.sha256, version.rule_count = content, digest, count
        action = "ruleset.draft.updated"
    else:
        next_no = (db.scalar(select(func.max(RulesetVersion.version_no)).where(RulesetVersion.framework_slug == slug)) or 0) + 1
        version = RulesetVersion(framework_slug=slug, version_no=next_no, status="DRAFT",
                                 yaml_content=content, sha256=digest, rule_count=count, created_by=admin.id)
        db.add(version)
        db.flush()
        action = "ruleset.draft.created"
    audit(db, actor=admin.id, action=action, kind="ruleset", target=str(version.id),
          after={"framework": slug, "version_no": version.version_no, "sha256": digest, "rule_count": count})
    db.commit()
    return {"id": str(version.id), "version_no": version.version_no, "rule_count": count, "sha256": digest}


def publish(db: Session, admin: User, slug: str, version_id: UUID) -> dict:
    _governance_lock(db)
    _validate_actor(db, admin)
    fw = db.scalar(select(ComplianceFramework).where(ComplianceFramework.slug == slug).with_for_update())
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found.")
    version = db.get(RulesetVersion, version_id)
    if not version or version.framework_slug != slug:
        raise HTTPException(status_code=404, detail="Draft not found.")
    if version.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only drafts may be published.")
    count = validate_rules(version.yaml_content)
    if hashlib.sha256(version.yaml_content.encode("utf-8")).hexdigest() != version.sha256 or count != version.rule_count:
        raise HTTPException(status_code=409, detail="Ruleset contents failed integrity verification.")
    old = fw.active_version_id
    version.status = "PUBLISHED"
    version.published_at = datetime.now(timezone.utc)
    version.published_by = admin.id
    fw.active_version_id = version.id
    fw.status = "PUBLISHED"   # publishing intentionally restores archived frameworks
    audit(db, actor=admin.id, action="ruleset.published", kind="framework", target=slug,
          before={"version_id": str(old) if old else None},
          after={"version_id": str(version.id), "sha256": version.sha256, "rule_count": count})
    db.commit()
    return admin_framework(db, fw)


def replace_access(db: Session, admin: User, slug: str, *, everyone: bool, domains: list[str], emails: list[str]) -> dict:
    try:
        normalized = ({("EVERYONE", "")} if everyone else set()) | {
            ("DOMAIN", normalized_domain(value)) for value in domains
        } | {("EMAIL", normalize_email(value)) for value in emails}
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid exact domain or email in access policy.") from None
    if len(normalized) > 101:
        raise HTTPException(status_code=422, detail="At most 100 domain/email selectors are allowed.")
    _governance_lock(db)
    _validate_actor(db, admin)
    fw = db.get(ComplianceFramework, slug)
    if fw is None:
        raise HTTPException(status_code=404, detail="Framework not found.")
    existing = db.scalars(select(FrameworkAccessRule).where(FrameworkAccessRule.framework_slug == slug)).all()
    old = {(r.selector_type, r.selector_value) for r in existing if r.is_active}
    for row in existing:
        row.is_active = (row.selector_type, row.selector_value) in normalized
    registered = {(r.selector_type, r.selector_value) for r in existing}
    for kind, value in normalized - registered:
        db.add(FrameworkAccessRule(framework_slug=slug, selector_type=kind, selector_value=value, is_active=True))
    audit(db, actor=admin.id, action="framework.access.changed", kind="framework", target=slug,
          before={"selectors": sorted([list(x) for x in old])},
          after={"selectors": sorted([list(x) for x in normalized])})
    db.commit()
    return admin_framework(db, fw)
