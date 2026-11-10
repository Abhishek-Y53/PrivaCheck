"""Import all ORM models so Base.metadata is complete for Alembic."""

from backend.infrastructure.database.models.check_result import CheckResultRecord
from backend.infrastructure.database.models.observation import ScanObservation
from backend.infrastructure.database.models.scan import Scan
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession
from backend.infrastructure.database.models.platform_access import PlatformAccessDomain, PlatformAccessEmail

__all__ = ["User", "UserSession", "Scan", "ScanObservation", "CheckResultRecord", "PlatformAccessDomain", "PlatformAccessEmail"]
from backend.infrastructure.database.models.admin_audit_log import AdminAuditLog
__all__.append("AdminAuditLog")
from backend.infrastructure.database.models.framework import ComplianceFramework, RulesetVersion, FrameworkAccessRule
__all__ += ["ComplianceFramework", "RulesetVersion", "FrameworkAccessRule"]
