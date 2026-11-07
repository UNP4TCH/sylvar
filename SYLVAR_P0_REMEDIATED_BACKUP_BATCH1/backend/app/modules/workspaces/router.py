"""Workspaces and workspace membership API routes (Groups 2 & 3)."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemException
from app.core.security.jwt_verifier import AuthenticatedUser
from app.db.session import get_db
from app.models.user import User
from app.models.workspace import AgencyWorkspace, MembershipStatus, UserRole, WorkspaceMembership
from app.modules.auth.dependencies import get_current_user, get_or_sync_user
from app.modules.auth.pipeline import (
    SecurityContext,
    _set_tenant_local_context,
    require_workspace_admin,
    require_workspace_member,
)
from app.modules.workspaces.schemas import (
    MemberInvite,
    MemberResponse,
    WorkspaceCreate,
    WorkspaceResponse,
)

router = APIRouter(tags=["Workspaces"])


@router.get(
    "/workspaces",
    response_model=list[WorkspaceResponse],
    summary="List workspaces for authenticated user (TASK-011 / M-02)",
)
async def list_workspaces(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceResponse]:
    # Establish transaction-local user context for RLS
    await _set_tenant_local_context(db, current_user.user_id, None, None)
    stmt = (
        select(WorkspaceMembership, AgencyWorkspace)
        .join(AgencyWorkspace, WorkspaceMembership.workspace_id == AgencyWorkspace.id)
        .where(
            WorkspaceMembership.user_id == current_user.user_id,
            WorkspaceMembership.status == MembershipStatus.ACTIVE.value,
        )
        .order_by(AgencyWorkspace.name.asc())
    )
    results = (await db.execute(stmt)).all()
    return [
        WorkspaceResponse(
            workspace_id=ws.id,
            name=ws.name,
            slug=ws.slug,
            current_role=mem.role,
            created_at=ws.created_at,
        )
        for mem, ws in results
    ]


@router.post(
    "/workspaces",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create agency workspace",
)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    # Establish the authenticated principal before RLS-protected profile/workspace operations.
    await _set_tenant_local_context(db, current_user.user_id, None, None)

    # 1. Ensure user profile exists and reconcile invited placeholder identities (M-01)
    await get_or_sync_user(db, current_user)

    # 2. Check slug uniqueness
    existing_stmt = select(AgencyWorkspace).where(AgencyWorkspace.slug == payload.slug)
    if (await db.execute(existing_stmt)).scalar_one_or_none():
        raise ProblemException(
            status=status.HTTP_409_CONFLICT,
            code="SLUG_EXISTS",
            title="Conflict",
            detail=f"Workspace with slug '{payload.slug}' already exists.",
        )

    # 3. Preallocate the workspace ID and set it transaction-locally. The
    # workspace RLS policy permits the INSERT only when id matches this context.
    workspace_id = uuid.uuid4()
    await _set_tenant_local_context(db, current_user.user_id, workspace_id, None)
    workspace = AgencyWorkspace(
        id=workspace_id,
        name=payload.name,
        slug=payload.slug,
    )
    db.add(workspace)
    await db.flush()

    # 4. Creator becomes WORKSPACE_ADMIN
    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=current_user.user_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db.add(membership)
    await db.flush()

    return WorkspaceResponse(
        workspace_id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        current_role=UserRole.WORKSPACE_ADMIN.value,
        created_at=workspace.created_at,
    )


@router.get(
    "/workspaces/{w_id}",
    response_model=WorkspaceResponse,
    summary="Retrieve workspace metadata",
)
async def get_workspace(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    ctx: SecurityContext = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    workspace = await db.get(AgencyWorkspace, w_id)
    if not workspace:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Workspace not found.",
        )
    return WorkspaceResponse(
        workspace_id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        current_role=ctx.workspace_role.value,
        created_at=workspace.created_at,
    )


@router.post(
    "/workspaces/{w_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite/add workspace member",
)
async def invite_member(
    payload: MemberInvite,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    ctx: SecurityContext = Depends(require_workspace_admin),
    db: AsyncSession = Depends(get_db),
) -> MemberResponse:
    # 1. Resolve or create user profile
    user_stmt = select(User).where(User.email == payload.email)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        user = User(
            email=payload.email,
            full_name=payload.full_name,
        )
        db.add(user)
        await db.flush()

    # 2. Check if already a member
    mem_stmt = select(WorkspaceMembership).where(
        WorkspaceMembership.workspace_id == w_id,
        WorkspaceMembership.user_id == user.id,
    )
    existing_mem = (await db.execute(mem_stmt)).scalar_one_or_none()
    if existing_mem:
        if existing_mem.status == MembershipStatus.ACTIVE.value:
            raise ProblemException(
                status=status.HTTP_409_CONFLICT,
                code="MEMBER_ALREADY_EXISTS",
                title="Conflict",
                detail=f"User '{payload.email}' is already an active member of this workspace.",
            )
        # Reactivate if previously revoked
        existing_mem.status = MembershipStatus.ACTIVE.value
        existing_mem.role = payload.role.value
        existing_mem.revoked_at = None
        await db.flush()
        return MemberResponse(
            membership_id=existing_mem.id,
            workspace_id=existing_mem.workspace_id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=existing_mem.role,
            status=existing_mem.status,
            created_at=existing_mem.created_at,
            revoked_at=existing_mem.revoked_at,
        )

    # 3. Create active membership
    new_mem = WorkspaceMembership(
        workspace_id=w_id,
        user_id=user.id,
        role=payload.role.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db.add(new_mem)
    await db.flush()

    return MemberResponse(
        membership_id=new_mem.id,
        workspace_id=new_mem.workspace_id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=new_mem.role,
        status=new_mem.status,
        created_at=new_mem.created_at,
        revoked_at=new_mem.revoked_at,
    )


@router.get(
    "/workspaces/{w_id}/members",
    response_model=list[MemberResponse],
    summary="List workspace members",
)
async def list_members(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    ctx: SecurityContext = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> list[MemberResponse]:
    stmt = (
        select(WorkspaceMembership, User)
        .join(User, WorkspaceMembership.user_id == User.id)
        .where(
            WorkspaceMembership.workspace_id == w_id,
            WorkspaceMembership.status == MembershipStatus.ACTIVE.value,
        )
    )
    results = (await db.execute(stmt)).all()
    return [
        MemberResponse(
            membership_id=mem.id,
            workspace_id=mem.workspace_id,
            user_id=usr.id,
            email=usr.email,
            full_name=usr.full_name,
            role=mem.role,
            status=mem.status,
            created_at=mem.created_at,
            revoked_at=mem.revoked_at,
        )
        for mem, usr in results
    ]


@router.delete(
    "/workspaces/{w_id}/members/{m_id}",
    response_model=MemberResponse,
    summary="Revoke workspace membership",
)
async def revoke_member(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    m_id: uuid.UUID = Path(..., description="Membership ID"),
    ctx: SecurityContext = Depends(require_workspace_admin),
    db: AsyncSession = Depends(get_db),
) -> MemberResponse:
    mem = await db.get(WorkspaceMembership, m_id)
    if not mem or mem.workspace_id != w_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Membership record not found in this workspace.",
        )

    # Last Admin Protection
    if mem.role == UserRole.WORKSPACE_ADMIN.value and mem.status == MembershipStatus.ACTIVE.value:
        admin_count_stmt = select(func.count(WorkspaceMembership.id)).where(
            WorkspaceMembership.workspace_id == w_id,
            WorkspaceMembership.role == UserRole.WORKSPACE_ADMIN.value,
            WorkspaceMembership.status == MembershipStatus.ACTIVE.value,
        )
        active_admins = (await db.execute(admin_count_stmt)).scalar() or 0
        if active_admins <= 1:
            raise ProblemException(
                status=status.HTTP_409_CONFLICT,
                code="LAST_ADMIN_PROTECTION",
                title="Conflict",
                detail="Cannot revoke the last active Workspace Admin in this workspace.",
            )

    user = await db.get(User, mem.user_id)
    now = datetime.now(UTC)
    mem.status = MembershipStatus.REVOKED.value
    mem.revoked_at = now
    await db.flush()

    return MemberResponse(
        membership_id=mem.id,
        workspace_id=mem.workspace_id,
        user_id=mem.user_id,
        email=user.email if user else "",
        full_name=user.full_name if user else None,
        role=mem.role,
        status=mem.status,
        created_at=mem.created_at,
        revoked_at=mem.revoked_at,
    )
