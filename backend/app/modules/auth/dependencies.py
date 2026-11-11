"""Authentication dependency: Bearer JWT -> verified AuthenticatedUser.

Authentication only. Workspace/client authorization (the 5-gate pipeline) is Phase 2 (TASK-010).
"""
from datetime import UTC, datetime
import logging

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemException
from app.core.security.errors import AuthError
from app.core.security.gotrue_verifier import verify_identity_with_gotrue
from app.core.security.jwt_verifier import AuthenticatedUser, JWTVerifier
from app.models.client import ClientMembership
from app.models.user import User
from app.models.workspace import (
    AgencyWorkspace,
    InvitationStatus,
    MembershipStatus,
    UserRole,
    WorkspaceInvitation,
    WorkspaceMembership,
)

logger = logging.getLogger("sylvar.auth")
_bearer = HTTPBearer(auto_error=False)
_WWW_AUTH = {"WWW-Authenticate": "Bearer"}


def _get_verifier(request: Request) -> JWTVerifier:
    verifier: JWTVerifier | None = getattr(request.app.state, "jwt_verifier", None)
    if verifier is None:
        raise ProblemException(
            503, "Authentication unavailable", "AUTH_NOT_CONFIGURED",
            "Authentication is not configured on this server.",
        )
    return verifier


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    verifier = _get_verifier(request)
    if credentials is None or not credentials.credentials:
        raise ProblemException(
            401, "Unauthorized", "TOKEN_MISSING", "Bearer token required.", _WWW_AUTH
        )
    try:
        return await verifier.verify(credentials.credentials)
    except AuthError as exc:
        headers = _WWW_AUTH if exc.status == 401 else None
        title = "Unauthorized" if exc.status == 401 else "Authentication unavailable"
        raise ProblemException(exc.status, title, exc.code, exc.detail, headers) from None


async def get_or_sync_user(db: AsyncSession, current_user: AuthenticatedUser) -> User:
    """Resolve and sync user identity from verified JWT.

    Resolves M-01 (Invitation identity reconciliation):
    If user was previously invited with a placeholder ID, reconciles to their authentic
    Supabase GoTrue user ID and re-links existing memberships.
    """
    # 1. Search by authentic user_id
    stmt = select(User).where(User.id == current_user.user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user:
        if current_user.email and user.email != current_user.email:
            user.email = current_user.email
            await db.flush()
    else:
        # 2. Check if user was previously invited by email with a placeholder UUID
        if current_user.email:
            email_stmt = select(User).where(User.email == current_user.email)
            invited_user = (await db.execute(email_stmt)).scalar_one_or_none()
            if invited_user:
                old_id = invited_user.id
                full_name = invited_user.full_name
                # In-place reconciliation without physical DELETE:
                # Updating users.id in-place cascades to workspace_memberships.user_id
                # and client_memberships.user_id via ON UPDATE CASCADE foreign keys.
                # Expunge the placeholder object so SQLAlchemy identity map tracks the new PK cleanly.
                db.expunge(invited_user)
                await db.execute(
                    update(User)
                    .where(User.id == old_id)
                    .values(id=current_user.user_id, full_name=full_name)
                )
                await db.execute(
                    update(WorkspaceMembership)
                    .where(WorkspaceMembership.user_id == old_id)
                    .values(user_id=current_user.user_id, status=MembershipStatus.ACTIVE.value)
                )
                await db.execute(
                    update(ClientMembership)
                    .where(ClientMembership.user_id == old_id)
                    .values(user_id=current_user.user_id)
                )
                await db.flush()
                user = (
                    await db.execute(select(User).where(User.id == current_user.user_id))
                ).scalar_one()

        # 3. Fresh user creation
        if not user:
            fresh_user = User(
                id=current_user.user_id,
                email=current_user.email or f"user-{current_user.user_id}@agency.local",
            )
            db.add(fresh_user)
            await db.flush()
            user = fresh_user

    # 4. Activate any pending workspace invitations bound to verified email
    if current_user.email:
        # Determine genuine trusted verification (root JWT claims or authoritative GoTrue Admin check)
        is_verified = current_user.email_verified
        if not is_verified:
            is_verified = await verify_identity_with_gotrue(current_user.user_id, current_user.email)

        if is_verified:
            inv_stmt = select(WorkspaceInvitation).where(
                func.lower(WorkspaceInvitation.email) == current_user.email.lower(),
                WorkspaceInvitation.status == InvitationStatus.PENDING.value,
                WorkspaceInvitation.expires_at > datetime.now(UTC),
            )
            pending_invitations = (await db.execute(inv_stmt)).scalars().all()
            bind = db.bind
            is_postgres = (bind.dialect.name == "postgresql") if bind else False
            for inv in pending_invitations:
                if inv.status != InvitationStatus.PENDING.value:
                    continue

                if is_postgres:
                    # Authoritative atomic SECURITY DEFINER procedure (Migration 007)
                    await db.execute(
                        text("SELECT public.accept_workspace_invitation(:inv_id, :user_id)"),
                        {"inv_id": inv.id, "user_id": user.id},
                    )
                else:
                    # SQLite fallback for offline unit tests
                    ws = await db.get(AgencyWorkspace, inv.workspace_id)
                    if not ws:
                        continue

                    mem_stmt = select(WorkspaceMembership).where(
                        WorkspaceMembership.workspace_id == inv.workspace_id,
                        WorkspaceMembership.user_id == user.id,
                    )
                    existing_mem = (await db.execute(mem_stmt)).scalar_one_or_none()
                    if not existing_mem:
                        new_mem = WorkspaceMembership(
                            workspace_id=inv.workspace_id,
                            user_id=user.id,
                            role=inv.role,
                            status=MembershipStatus.ACTIVE.value,
                        )
                        db.add(new_mem)
                    else:
                        # Guard 1: Deliberately revoked memberships CANNOT be silently reactivated
                        if (
                            existing_mem.status == MembershipStatus.REVOKED.value
                            or existing_mem.revoked_at is not None
                        ):
                            logger.warning(
                                "Deliberately revoked membership for user %s in workspace %s cannot be reactivated via standard invitation",
                                user.id,
                                inv.workspace_id,
                            )
                            inv.status = InvitationStatus.REVOKED.value
                            inv.updated_at = datetime.now(UTC)
                            continue

                        # Guard 2 & 3: Never downgrade WORKSPACE_ADMIN and preserve existing role
                        existing_mem.status = MembershipStatus.ACTIVE.value
                        # Preserves existing role (especially WORKSPACE_ADMIN from accidental downgrade)

                    inv.status = InvitationStatus.ACCEPTED.value
                    inv.accepted_at = datetime.now(UTC)
                    inv.auth_user_id = user.id
                    inv.updated_at = datetime.now(UTC)

            if pending_invitations:
                await db.flush()

    return user
