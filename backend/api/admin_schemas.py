"""Strictly validated privileged API request/response shapes."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.api.schemas import ScanStatusResponse


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChangeRoleRequest(StrictBody):
    role: Literal["USER", "ADMIN"]


class ChangeStatusRequest(StrictBody):
    is_active: bool


class SetAdmissionRequest(StrictBody):
    value: str = Field(min_length=3, max_length=320)
    is_active: bool = True


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    display_name: str | None
    role: Literal["USER", "ADMIN"]
    is_active: bool
    google_linked: bool
    created_at: datetime


class UserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int
    limit: int
    offset: int


class AdmissionEntryResponse(BaseModel):
    id: UUID
    value: str
    is_active: bool
    created_at: datetime


class AdmissionListResponse(BaseModel):
    domains: list[AdmissionEntryResponse]
    emails: list[AdmissionEntryResponse]


class AdminScanResponse(BaseModel):
    scan: ScanStatusResponse
    owner_email: str | None


class AdminScanListResponse(BaseModel):
    items: list[AdminScanResponse]
    total: int
    limit: int
    offset: int


class AdminAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_user_id: UUID
    action: str
    target_type: str
    target_id: str
    before_data: dict | None
    after_data: dict | None
    created_at: datetime


class AdminAuditListResponse(BaseModel):
    items: list[AdminAuditResponse]
    total: int
    limit: int
    offset: int
