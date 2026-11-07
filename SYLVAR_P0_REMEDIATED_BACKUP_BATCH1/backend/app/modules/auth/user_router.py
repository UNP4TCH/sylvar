"""User profile and membership discovery endpoints (Group 1)."""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.jwt_verifier import AuthenticatedUser
from app.db.session import get_db
from app.models.client import ClientBrand, ClientMembership, ClientMembershipStatus
from app.models.workspace import AgencyWorkspace, MembershipStatus, WorkspaceMembership
from app.modules.auth.dependencies import get_current_user, get_or_sync_user
from app.modules.auth.pipeline import _set_tenant_local_context

router = APIRouter(prefix="/users", tags=["User Profile"])


class WorkspaceMembershipItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: uuid.UUID
    workspace_name: str
    role: str
    status: str


class ClientMembershipItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    client_role: str
    status: str


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    full_name: str | None = None
    avatar_url: str | None = None
    workspaces: list[WorkspaceMembershipItem]
    client_assignments: list[ClientMembershipItem]


@router.get("/me", response_model=UserProfileResponse, summary="Retrieve authenticated user profile and memberships")
async def get_my_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    # 1. Establish tenant context for RLS
    await _set_tenant_local_context(db, current_user.user_id, None, None)

    # 2. Ensure user profile exists and reconcile invited placeholder identities (M-01)
    user = await get_or_sync_user(db, current_user)

    # 2. Get active workspace memberships
    ws_stmt = (
        select(WorkspaceMembership, AgencyWorkspace)
        .join(AgencyWorkspace, WorkspaceMembership.workspace_id == AgencyWorkspace.id)
        .where(
            WorkspaceMembership.user_id == current_user.user_id,
            WorkspaceMembership.status == MembershipStatus.ACTIVE.value,
        )
    )
    ws_results = (await db.execute(ws_stmt)).all()
    workspaces = [
        WorkspaceMembershipItem(
            workspace_id=ws.id,
            workspace_name=ws.name,
            role=mem.role,
            status=mem.status,
        )
        for mem, ws in ws_results
    ]

    # 3. Get active client brand assignments
    client_stmt = (
        select(ClientMembership, ClientBrand)
        .join(ClientBrand, ClientMembership.client_id == ClientBrand.id)
        .where(
            ClientMembership.user_id == current_user.user_id,
            ClientMembership.status == ClientMembershipStatus.ACTIVE.value,
        )
    )
    client_results = (await db.execute(client_stmt)).all()
    clients = [
        ClientMembershipItem(
            workspace_id=cm.workspace_id,
            client_id=cb.id,
            client_name=cb.name,
            client_role=cm.client_role,
            status=cm.status,
        )
        for cm, cb in client_results
    ]

    return UserProfileResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        workspaces=workspaces,
        client_assignments=clients,
    )
