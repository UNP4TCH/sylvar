"""Pydantic schemas for Workspaces and Workspace Members."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.workspace import UserRole


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")


class WorkspaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=255)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: uuid.UUID
    name: str
    slug: str
    current_role: str | None = None
    created_at: datetime


class MemberInvite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: UserRole
    full_name: str | None = None


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membership_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str | None = None
    role: str
    status: str
    delivery_status: str | None = None
    delivery_attempts: int | None = None
    created_at: datetime
    revoked_at: datetime | None = None
