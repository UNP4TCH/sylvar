"""Authentication dependency: Bearer JWT -> verified AuthenticatedUser.

Authentication only. Workspace/client authorization (the 5-gate pipeline) is Phase 2 (TASK-010).
"""
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemException
from app.core.security.errors import AuthError
from app.core.security.jwt_verifier import AuthenticatedUser, JWTVerifier
from app.models.client import ClientMembership
from app.models.user import User
from app.models.workspace import WorkspaceMembership

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
        return user

    # 2. Check if user was previously invited by email with a placeholder UUID
    if current_user.email:
        email_stmt = select(User).where(User.email == current_user.email)
        invited_user = (await db.execute(email_stmt)).scalar_one_or_none()
        if invited_user:
            old_id = invited_user.id
            full_name = invited_user.full_name
            # Reassign memberships to authentic user_id
            await db.execute(
                update(WorkspaceMembership)
                .where(WorkspaceMembership.user_id == old_id)
                .values(user_id=current_user.user_id)
            )
            await db.execute(
                update(ClientMembership)
                .where(ClientMembership.user_id == old_id)
                .values(user_id=current_user.user_id)
            )
            # Replace placeholder user with authentic user record
            await db.delete(invited_user)
            await db.flush()

            reconciled = User(
                id=current_user.user_id,
                email=current_user.email,
                full_name=full_name,
            )
            db.add(reconciled)
            await db.flush()
            return reconciled

    # 3. Fresh user creation
    fresh_user = User(
        id=current_user.user_id,
        email=current_user.email or f"user-{current_user.user_id}@agency.local",
    )
    db.add(fresh_user)
    await db.flush()
    return fresh_user
