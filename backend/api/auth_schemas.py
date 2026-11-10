"""Safe public authentication response and legacy-link request schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: str
    display_name: str | None = None
    is_active: bool
    created_at: datetime


class CsrfResponse(BaseModel):
    csrf_token: str


class LinkLegacyAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
