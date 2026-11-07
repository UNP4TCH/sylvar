"""Client brand management and client assignment API routes (Groups 4 & 5)."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemException
from app.db.session import get_db
from app.models.client import (
    ClientBrand,
    ClientMembership,
    ClientMembershipStatus,
    ClientRole,
)
from app.models.workspace import MembershipStatus, WorkspaceMembership
from app.modules.auth.pipeline import (
    SecurityContext,
    require_client_member,
    require_workspace_admin,
    require_workspace_member,
)
from app.modules.clients.schemas import (
    ClientCreate,
    ClientMemberAssign,
    ClientMemberResponse,
    ClientResponse,
    ClientUpdate,
)

router = APIRouter(tags=["Client Brands"])


@router.post(
    "/workspaces/{w_id}/clients",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision client brand space",
)
async def create_client(
    payload: ClientCreate,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    ctx: SecurityContext = Depends(require_workspace_admin),
    db: AsyncSession = Depends(get_db),
) -> ClientResponse:
    # 1. Check code conflict within workspace
    existing_stmt = select(ClientBrand).where(
        ClientBrand.workspace_id == w_id,
        ClientBrand.code == payload.code,
    )
    if (await db.execute(existing_stmt)).scalar_one_or_none():
        raise ProblemException(
            status=status.HTTP_409_CONFLICT,
            code="CLIENT_CODE_CONFLICT",
            title="Conflict",
            detail=f"Client brand with code '{payload.code}' already exists in this workspace.",
        )

    # 2. Create client brand
    client = ClientBrand(
        workspace_id=w_id,
        name=payload.name,
        code=payload.code,
        description=payload.description,
    )
    db.add(client)
    await db.flush()

    # 3. ADR-003: Atomically assign creator as BRAND_MANAGER in same transaction
    creator_membership = ClientMembership(
        workspace_id=w_id,
        client_id=client.id,
        user_id=ctx.user_id,
        client_role=ClientRole.BRAND_MANAGER.value,
        status=ClientMembershipStatus.ACTIVE.value,
    )
    db.add(creator_membership)
    await db.flush()

    return ClientResponse(
        client_id=client.id,
        workspace_id=client.workspace_id,
        name=client.name,
        code=client.code,
        description=client.description,
        active_memory_version_id=client.active_memory_version_id,
        created_at=client.created_at,
    )


@router.get(
    "/workspaces/{w_id}/clients",
    response_model=list[ClientResponse],
    summary="List client brands accessible to caller",
)
async def list_clients(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    ctx: SecurityContext = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> list[ClientResponse]:
    """ADR-003 & API_DESIGN: Must filter to active explicit client assignments for ALL roles,

    including Workspace Admin.
    """
    stmt = (
        select(ClientBrand)
        .join(ClientMembership, ClientBrand.id == ClientMembership.client_id)
        .where(
            ClientBrand.workspace_id == w_id,
            ClientMembership.user_id == ctx.user_id,
            ClientMembership.status == ClientMembershipStatus.ACTIVE.value,
        )
        .order_by(ClientBrand.name.asc())
    )
    results = (await db.execute(stmt)).scalars().all()
    return [
        ClientResponse(
            client_id=cb.id,
            workspace_id=cb.workspace_id,
            name=cb.name,
            code=cb.code,
            description=cb.description,
            active_memory_version_id=cb.active_memory_version_id,
            created_at=cb.created_at,
        )
        for cb in results
    ]


@router.get(
    "/workspaces/{w_id}/clients/{c_id}",
    response_model=ClientResponse,
    summary="Retrieve client brand details",
)
async def get_client(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> ClientResponse:
    brand = await db.get(ClientBrand, c_id)
    if not brand or brand.workspace_id != w_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Client brand not found.",
        )
    return ClientResponse(
        client_id=brand.id,
        workspace_id=brand.workspace_id,
        name=brand.name,
        code=brand.code,
        description=brand.description,
        active_memory_version_id=brand.active_memory_version_id,
        created_at=brand.created_at,
    )


@router.patch(
    "/workspaces/{w_id}/clients/{c_id}",
    response_model=ClientResponse,
    summary="Update/rename client brand metadata",
)
async def update_client(
    payload: ClientUpdate,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    ctx: SecurityContext = Depends(require_workspace_admin),
    db: AsyncSession = Depends(get_db),
) -> ClientResponse:
    brand = await db.get(ClientBrand, c_id)
    if not brand or brand.workspace_id != w_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Client brand not found.",
        )

    clean_name = payload.name.strip()
    if len(clean_name) < 2:
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="INVALID_NAME",
            title="Validation Error",
            detail="Client brand name must be at least 2 characters.",
        )

    # Check for duplicate client brand name within the same workspace
    conflict_stmt = select(ClientBrand).where(
        ClientBrand.workspace_id == w_id,
        ClientBrand.name == clean_name,
        ClientBrand.id != c_id,
    )
    if (await db.execute(conflict_stmt)).scalar_one_or_none():
        raise ProblemException(
            status=status.HTTP_409_CONFLICT,
            code="CLIENT_NAME_CONFLICT",
            title="Conflict",
            detail=f"A client brand named '{clean_name}' already exists in this workspace.",
        )

    brand.name = clean_name
    if payload.description is not None:
        brand.description = payload.description
    await db.flush()

    return ClientResponse(
        client_id=brand.id,
        workspace_id=brand.workspace_id,
        name=brand.name,
        code=brand.code,
        description=brand.description,
        active_memory_version_id=brand.active_memory_version_id,
        created_at=brand.created_at,
    )


@router.post(
    "/workspaces/{w_id}/clients/{c_id}/members",
    response_model=ClientMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign workspace member to client brand",
)
async def assign_client_member(
    payload: ClientMemberAssign,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    ctx: SecurityContext = Depends(require_workspace_admin),
    db: AsyncSession = Depends(get_db),
) -> ClientMemberResponse:
    # 1. Verify client brand exists in workspace
    brand = await db.get(ClientBrand, c_id)
    if not brand or brand.workspace_id != w_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Client brand not found in this workspace.",
        )

    # 2. Verify target user is an active workspace member
    ws_mem_stmt = select(WorkspaceMembership).where(
        WorkspaceMembership.workspace_id == w_id,
        WorkspaceMembership.user_id == payload.user_id,
        WorkspaceMembership.status == MembershipStatus.ACTIVE.value,
    )
    ws_mem = (await db.execute(ws_mem_stmt)).scalar_one_or_none()
    if not ws_mem:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_IN_WORKSPACE",
            title="Not Found",
            detail="User is not an active member of this workspace.",
        )

    # 3. Check existing assignment
    cm_stmt = select(ClientMembership).where(
        ClientMembership.client_id == c_id,
        ClientMembership.user_id == payload.user_id,
    )
    existing_cm = (await db.execute(cm_stmt)).scalar_one_or_none()
    if existing_cm:
        if existing_cm.status == ClientMembershipStatus.ACTIVE.value:
            raise ProblemException(
                status=status.HTTP_409_CONFLICT,
                code="CLIENT_ASSIGNMENT_EXISTS",
                title="Conflict",
                detail="User is already assigned to this client brand.",
            )
        # Reactivate
        existing_cm.status = ClientMembershipStatus.ACTIVE.value
        existing_cm.client_role = payload.client_role.value
        existing_cm.revoked_at = None
        await db.flush()
        return ClientMemberResponse(
            client_membership_id=existing_cm.id,
            client_id=existing_cm.client_id,
            workspace_id=existing_cm.workspace_id,
            user_id=existing_cm.user_id,
            client_role=existing_cm.client_role,
            status=existing_cm.status,
            created_at=existing_cm.created_at,
            revoked_at=existing_cm.revoked_at,
        )

    # 4. Create new client membership
    new_cm = ClientMembership(
        workspace_id=w_id,
        client_id=c_id,
        user_id=payload.user_id,
        client_role=payload.client_role.value,
        status=ClientMembershipStatus.ACTIVE.value,
    )
    db.add(new_cm)
    await db.flush()

    return ClientMemberResponse(
        client_membership_id=new_cm.id,
        client_id=new_cm.client_id,
        workspace_id=new_cm.workspace_id,
        user_id=new_cm.user_id,
        client_role=new_cm.client_role,
        status=new_cm.status,
        created_at=new_cm.created_at,
        revoked_at=new_cm.revoked_at,
    )


@router.delete(
    "/workspaces/{w_id}/clients/{c_id}/members/{cm_id}",
    response_model=ClientMemberResponse,
    summary="Revoke client brand assignment",
)
async def revoke_client_member(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    cm_id: uuid.UUID = Path(..., description="Client Membership ID"),
    ctx: SecurityContext = Depends(require_workspace_admin),
    db: AsyncSession = Depends(get_db),
) -> ClientMemberResponse:
    cm = await db.get(ClientMembership, cm_id)
    if not cm or cm.workspace_id != w_id or cm.client_id != c_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Client membership not found.",
        )

    now = datetime.now(UTC)
    cm.status = ClientMembershipStatus.REVOKED.value
    cm.revoked_at = now
    await db.flush()

    return ClientMemberResponse(
        client_membership_id=cm.id,
        client_id=cm.client_id,
        workspace_id=cm.workspace_id,
        user_id=cm.user_id,
        client_role=cm.client_role,
        status=cm.status,
        created_at=cm.created_at,
        revoked_at=cm.revoked_at,
    )
