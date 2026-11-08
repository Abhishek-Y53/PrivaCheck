"""Import all ORM models so Base.metadata is complete for Alembic."""

from backend.infrastructure.database.models.check_result import CheckResultRecord
from backend.infrastructure.database.models.observation import ScanObservation
from backend.infrastructure.database.models.scan import Scan
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession

__all__ = ["User", "UserSession", "Scan", "ScanObservation", "CheckResultRecord"]
