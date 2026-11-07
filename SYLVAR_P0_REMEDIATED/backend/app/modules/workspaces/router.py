"""Workspaces and workspace membership API routes (Groups 2 & 3)."""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.errors import ProblemException
from app.core.invitations import dispatch_workspace_invitation
from app.core.security.jwt_verifier import AuthenticatedUser
from app.db.session import get_db
from app.models.user import User
from app.models.workspace import (
    AgencyWorkspace,
    InvitationDeliveryStatus,
    InvitationStatus,
    MembershipStatus,
    UserRole,
    WorkspaceInvitation,
    WorkspaceMembership,
)
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
    WorkspaceUpdate,
)

router = APIRouter(tags=["Workspaces"])


def _is_active_delivery(dt: datetime | None, window_seconds: int = 60) -> bool:
    """Check if a delivery attempt is actively in progress within the given window."""
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt > datetime.now(UTC) - timedelta(seconds=window_seconds)


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
    await get_or_sync_user(db, current_user)
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


@router.patch(
    "/workspaces/{w_id}",
    response_model=WorkspaceResponse,
    summary="Update/rename workspace metadata",
)
async def update_workspace(
    payload: WorkspaceUpdate,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    ctx: SecurityContext = Depends(require_workspace_admin),
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
    clean_name = payload.name.strip()
    if len(clean_name) < 2:
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="INVALID_NAME",
            title="Validation Error",
            detail="Workspace name must be at least 2 characters.",
        )
    workspace.name = clean_name
    await db.flush()
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
    workspace = await db.get(AgencyWorkspace, w_id)
    if not workspace:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Workspace not found.",
        )

    norm_email = payload.email.lower().strip()

    # 1. Check if user already exists with an active workspace membership
    user_stmt = select(User).where(func.lower(User.email) == norm_email)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if user:
        mem_stmt = select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == w_id,
            WorkspaceMembership.user_id == user.id,
        )
        existing_mem = (await db.execute(mem_stmt)).scalar_one_or_none()
        if existing_mem and existing_mem.status == MembershipStatus.ACTIVE.value:
            raise ProblemException(
                status=status.HTTP_409_CONFLICT,
                code="MEMBER_ALREADY_EXISTS",
                title="Conflict",
                detail=f"User '{payload.email}' is already an active member of this workspace.",
            )

    # 2. Idempotency & Concurrency Check: Check if an active PENDING invitation already exists
    inv_stmt = (
        select(WorkspaceInvitation)
        .where(
            WorkspaceInvitation.workspace_id == w_id,
            func.lower(WorkspaceInvitation.email) == norm_email,
            WorkspaceInvitation.status == InvitationStatus.PENDING.value,
        )
        .with_for_update()
    )
    existing_inv = (await db.execute(inv_stmt)).scalar_one_or_none()
    if existing_inv:
        # Prevent concurrent dispatch: if an in-flight dispatch is active (<60s window), reject concurrent attempt
        if (
            existing_inv.delivery_status == InvitationDeliveryStatus.PENDING.value
            and _is_active_delivery(existing_inv.updated_at, window_seconds=60)
        ):
            raise ProblemException(
                status=status.HTTP_409_CONFLICT,
                code="INVITATION_DISPATCH_IN_PROGRESS",
                title="Conflict",
                detail=f"An invitation dispatch for '{payload.email}' is currently in progress. Please wait before retrying.",
            )
        inv = existing_inv
        inv.delivery_attempts += 1
        inv.delivery_status = InvitationDeliveryStatus.PENDING.value
        inv.claim_expires_at = datetime.now(UTC) + timedelta(seconds=60)
        inv.last_delivery_error = None
        inv.updated_at = datetime.now(UTC)
    else:
        # 3. Create scoped invitation record in database with initial PENDING delivery
        inv = WorkspaceInvitation(
            workspace_id=w_id,
            email=norm_email,
            role=payload.role.value,
            status=InvitationStatus.PENDING.value,
            delivery_status=InvitationDeliveryStatus.PENDING.value,
            claim_expires_at=datetime.now(UTC) + timedelta(seconds=60),
            delivery_attempts=1,
            invited_by_user_id=ctx.user_id,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        db.add(inv)

    # =========================================================================
    # TRANSACTION 1: Persist invitation and PENDING delivery state in a committed transaction
    # =========================================================================
    await db.commit()
    inv_id = inv.id

    # =========================================================================
    # DISPATCH: Run external delivery completely independently from Transaction 1
    # =========================================================================
    dispatch_error: Exception | None = None
    invitation_res = None
    try:
        invitation_res = await dispatch_workspace_invitation(
            recipient_email=payload.email,
            recipient_name=payload.full_name,
            workspace_id=w_id,
            workspace_name=workspace.name,
            role=payload.role.value,
        )
    except Exception as exc:
        dispatch_error = exc

    # =========================================================================
    # TRANSACTION 2: Persist DELIVERED or FAILED in a separate transaction
    # =========================================================================
    try:
        await _set_tenant_local_context(db, ctx.user_id, w_id, None)
        inv_record = await db.get(WorkspaceInvitation, inv_id)
        if inv_record is None:
            inv_record = (await db.execute(select(WorkspaceInvitation).where(WorkspaceInvitation.id == inv_id))).scalar_one()

        if invitation_res and invitation_res.delivered and not dispatch_error:
            inv_record.delivery_status = InvitationDeliveryStatus.DELIVERED.value
            inv_record.claim_expires_at = None
            inv_record.delivered_at = datetime.now(UTC)
            inv_record.last_delivery_error = None
            if invitation_res.auth_user_id:
                inv_record.auth_user_id = invitation_res.auth_user_id
            if invitation_res.provider_message_id:
                inv_record.provider_message_id = invitation_res.provider_message_id
            inv_record.updated_at = datetime.now(UTC)
            await db.commit()

            return MemberResponse(
                membership_id=inv_record.id,
                workspace_id=inv_record.workspace_id,
                user_id=inv_record.auth_user_id or uuid.UUID(int=0),
                email=inv_record.email,
                full_name=payload.full_name,
                role=inv_record.role,
                status=MembershipStatus.INVITED.value,
                delivery_status=inv_record.delivery_status,
                delivery_attempts=inv_record.delivery_attempts,
                created_at=inv_record.created_at,
                revoked_at=None,
            )
        else:
            error_detail = str(dispatch_error) if dispatch_error else "Unknown dispatch error"
            inv_record.delivery_status = InvitationDeliveryStatus.FAILED.value
            inv_record.claim_expires_at = None
            inv_record.last_delivery_error = error_detail
            inv_record.updated_at = datetime.now(UTC)
            await db.commit()

            if isinstance(dispatch_error, ProblemException):
                raise dispatch_error
            raise ProblemException(
                status=status.HTTP_502_BAD_GATEWAY,
                code="INVITATION_DELIVERY_FAILED",
                title="Bad Gateway",
                detail=f"External invitation delivery failed: {error_detail}",
            ) from dispatch_error
    except ProblemException:
        raise
    except Exception as db_exc:
        logger.error(
            "CRITICAL: Transaction 2 commit failed for invitation %s after provider dispatch: %s",
            inv_id,
            str(db_exc),
            exc_info=True,
        )
        if invitation_res and invitation_res.delivered:
            raise ProblemException(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="DELIVERY_RECORDING_FAILED",
                title="Internal Server Error",
                detail="Invitation dispatch was accepted by external provider, but recording delivered status in database failed. Record remains recoverable in PENDING state.",
            ) from db_exc
        raise ProblemException(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_COMMIT_FAILED",
            title="Internal Server Error",
            detail=f"Failed to record invitation outcome: {str(db_exc)}",
        ) from db_exc


@router.post(
    "/workspaces/{w_id}/invitations/{inv_id}/retry",
    response_model=MemberResponse,
    summary="Explicitly retry unconfirmed or failed invitation delivery",
)
async def retry_invitation_delivery(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    inv_id: uuid.UUID = Path(..., description="Invitation ID"),
    ctx: SecurityContext = Depends(require_workspace_admin),
    db: AsyncSession = Depends(get_db),
) -> MemberResponse:
    workspace = await db.get(AgencyWorkspace, w_id)
    if not workspace:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Workspace not found.",
        )

    inv_stmt = (
        select(WorkspaceInvitation)
        .where(
            WorkspaceInvitation.id == inv_id,
            WorkspaceInvitation.workspace_id == w_id,
        )
        .with_for_update()
    )
    inv = (await db.execute(inv_stmt)).scalar_one_or_none()
    if not inv:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="INVITATION_NOT_FOUND",
            title="Not Found",
            detail="Workspace invitation not found.",
        )

    if inv.status != InvitationStatus.PENDING.value:
        raise ProblemException(
            status=status.HTTP_409_CONFLICT,
            code="INVITATION_ALREADY_RESOLVED",
            title="Conflict",
            detail=f"Invitation is already in status '{inv.status}'.",
        )

    # Concurrency check: If another admin is actively dispatching (<60s window), prevent concurrent dispatch
    if (
        inv.delivery_status == InvitationDeliveryStatus.PENDING.value
        and _is_active_delivery(inv.updated_at, window_seconds=60)
    ):
        raise ProblemException(
            status=status.HTTP_409_CONFLICT,
            code="INVITATION_DISPATCH_IN_PROGRESS",
            title="Conflict",
            detail="An invitation dispatch is currently in progress. Please wait before retrying.",
        )

    # TRANSACTION 1: Record retry attempt and acquire lease
    inv.delivery_attempts += 1
    inv.delivery_status = InvitationDeliveryStatus.PENDING.value
    inv.claim_expires_at = datetime.now(UTC) + timedelta(seconds=60)
    inv.last_delivery_error = None
    inv.updated_at = datetime.now(UTC)
    await db.commit()

    # DISPATCH: Execute external delivery
    dispatch_error: Exception | None = None
    invitation_res = None
    try:
        invitation_res = await dispatch_workspace_invitation(
            recipient_email=inv.email,
            recipient_name=inv.email.split("@")[0],
            workspace_id=w_id,
            workspace_name=workspace.name,
            role=inv.role,
        )
    except Exception as exc:
        dispatch_error = exc

    # TRANSACTION 2: Record outcome
    try:
        await _set_tenant_local_context(db, ctx.user_id, w_id, None)
        inv_record = await db.get(WorkspaceInvitation, inv_id)
        if inv_record is None:
            inv_record = (await db.execute(select(WorkspaceInvitation).where(WorkspaceInvitation.id == inv_id))).scalar_one()

        if invitation_res and invitation_res.delivered and not dispatch_error:
            inv_record.delivery_status = InvitationDeliveryStatus.DELIVERED.value
            inv_record.claim_expires_at = None
            inv_record.delivered_at = datetime.now(UTC)
            inv_record.last_delivery_error = None
            if invitation_res.auth_user_id:
                inv_record.auth_user_id = invitation_res.auth_user_id
            if invitation_res.provider_message_id:
                inv_record.provider_message_id = invitation_res.provider_message_id
            inv_record.updated_at = datetime.now(UTC)
            await db.commit()

            return MemberResponse(
                membership_id=inv_record.id,
                workspace_id=inv_record.workspace_id,
                user_id=inv_record.auth_user_id or uuid.UUID(int=0),
                email=inv_record.email,
                full_name=None,
                role=inv_record.role,
                status=MembershipStatus.INVITED.value,
                delivery_status=inv_record.delivery_status,
                delivery_attempts=inv_record.delivery_attempts,
                created_at=inv_record.created_at,
                revoked_at=None,
            )
        else:
            error_detail = str(dispatch_error) if dispatch_error else "Unknown dispatch error"
            inv_record.delivery_status = InvitationDeliveryStatus.FAILED.value
            inv_record.claim_expires_at = None
            inv_record.last_delivery_error = error_detail
            inv_record.updated_at = datetime.now(UTC)
            await db.commit()

            if isinstance(dispatch_error, ProblemException):
                raise dispatch_error
            raise ProblemException(
                status=status.HTTP_502_BAD_GATEWAY,
                code="INVITATION_DELIVERY_FAILED",
                title="Bad Gateway",
                detail=f"External invitation delivery retry failed: {error_detail}",
            ) from dispatch_error
    except ProblemException:
        raise
    except Exception as db_exc:
        logger.error(
            "CRITICAL: Transaction 2 commit failed for retry invitation %s after provider dispatch: %s",
            inv_id,
            str(db_exc),
            exc_info=True,
        )
        if invitation_res and invitation_res.delivered:
            raise ProblemException(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="DELIVERY_RECORDING_FAILED",
                title="Internal Server Error",
                detail="Invitation dispatch was accepted by external provider, but recording delivered status in database failed. Record remains recoverable in PENDING state.",
            ) from db_exc
        raise ProblemException(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_COMMIT_FAILED",
            title="Internal Server Error",
            detail=f"Failed to record invitation outcome: {str(db_exc)}",
        ) from db_exc


@router.post(
    "/workspaces/{w_id}/invitations/recover-pending",
    response_model=list[MemberResponse],
    summary="Recover all pending or stranded unconfirmed invitation deliveries",
)
async def recover_pending_invitations(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    ctx: SecurityContext = Depends(require_workspace_admin),
    db: AsyncSession = Depends(get_db),
) -> list[MemberResponse]:
    workspace = await db.get(AgencyWorkspace, w_id)
    if not workspace:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Workspace not found.",
        )

    # =========================================================================
    # TRANSACTION 1: ATOMIC CLAIM TRANSACTION
    # Select all eligible unconfirmed or stranded invitations with FOR UPDATE SKIP LOCKED
    # and atomically persist their in-flight claim before committing Transaction 1.
    # =========================================================================
    now = datetime.now(UTC)
    claim_expiry = now + timedelta(seconds=60)
    stranded_cutoff = now - timedelta(seconds=60)

    # Atomic claim: single UPDATE statement acquires lease on matching rows
    claim_stmt = (
        update(WorkspaceInvitation)
        .where(
            WorkspaceInvitation.workspace_id == w_id,
            WorkspaceInvitation.status == InvitationStatus.PENDING.value,
            or_(
                WorkspaceInvitation.delivery_status == InvitationDeliveryStatus.FAILED.value,
                and_(
                    WorkspaceInvitation.delivery_status == InvitationDeliveryStatus.PENDING.value,
                    or_(
                        WorkspaceInvitation.claim_expires_at.is_(None),
                        WorkspaceInvitation.claim_expires_at <= now,
                    ),
                    func.coalesce(WorkspaceInvitation.updated_at, WorkspaceInvitation.created_at) <= stranded_cutoff,
                ),
            ),
        )
        .values(
            delivery_attempts=WorkspaceInvitation.delivery_attempts + 1,
            delivery_status=InvitationDeliveryStatus.PENDING.value,
            claim_expires_at=claim_expiry,
            last_delivery_error=None,
            updated_at=now,
        )
        .returning(WorkspaceInvitation.id, WorkspaceInvitation.email, WorkspaceInvitation.role)
    )
    claim_result = (await db.execute(claim_stmt)).all()
    if not claim_result:
        return []

    claimed_details: list[tuple[uuid.UUID, str, str, str]] = [
        (row[0], row[1], row[2], workspace.name)
        for row in claim_result
    ]

    # Durably commit claims to disk BEFORE any external dispatch is attempted
    await db.commit()

    # =========================================================================
    # DISPATCH & TRANSACTION 2: Run external dispatch and record outcome per item
    # =========================================================================
    recovered_responses: list[MemberResponse] = []

    for inv_id, email, role, ws_name in claimed_details:
        dispatch_error: Exception | None = None
        invitation_res = None
        try:
            invitation_res = await dispatch_workspace_invitation(
                recipient_email=email,
                recipient_name=email.split("@")[0],
                workspace_id=w_id,
                workspace_name=ws_name,
                role=role,
            )
        except Exception as exc:
            dispatch_error = exc

        # TRANSACTION 2: Record outcome for this claimed item
        try:
            await _set_tenant_local_context(db, ctx.user_id, w_id, None)
            inv_record = await db.get(WorkspaceInvitation, inv_id)
            if inv_record is None:
                inv_record = (await db.execute(select(WorkspaceInvitation).where(WorkspaceInvitation.id == inv_id))).scalar_one()

            if invitation_res and invitation_res.delivered and not dispatch_error:
                inv_record.delivery_status = InvitationDeliveryStatus.DELIVERED.value
                inv_record.claim_expires_at = None
                inv_record.delivered_at = datetime.now(UTC)
                inv_record.last_delivery_error = None
                if invitation_res.auth_user_id:
                    inv_record.auth_user_id = invitation_res.auth_user_id
                if invitation_res.provider_message_id:
                    inv_record.provider_message_id = invitation_res.provider_message_id
            else:
                inv_record.delivery_status = InvitationDeliveryStatus.FAILED.value
                inv_record.claim_expires_at = None
                inv_record.last_delivery_error = str(dispatch_error) if dispatch_error else "Unknown dispatch error"

            inv_record.updated_at = datetime.now(UTC)
            await db.commit()

            recovered_responses.append(
                MemberResponse(
                    membership_id=inv_record.id,
                    workspace_id=inv_record.workspace_id,
                    user_id=inv_record.auth_user_id or uuid.UUID(int=0),
                    email=inv_record.email,
                    full_name=None,
                    role=inv_record.role,
                    status=MembershipStatus.INVITED.value,
                    delivery_status=inv_record.delivery_status,
                    delivery_attempts=inv_record.delivery_attempts,
                    created_at=inv_record.created_at,
                    revoked_at=None,
                )
            )
        except Exception as exc:
            logger.error("Failed to record recovery outcome for %s: %s", inv_id, exc)

    return recovered_responses


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
