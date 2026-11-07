"""Pydantic schemas for Client Brands and Client Memberships (Domain B)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.client import ClientRole


class ClientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    description: str | None = Field(default=None, max_length=1000)


class ClientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class ClientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    client_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    active_memory_version_id: uuid.UUID | None = None
    created_at: datetime


class ClientMemberAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    client_role: ClientRole


class ClientMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    client_membership_id: uuid.UUID
    client_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    client_role: str
    status: str
    created_at: datetime
    revoked_at: datetime | None = None
