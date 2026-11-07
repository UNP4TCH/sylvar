"""5-Gate Server Authorization Pipeline (SECURITY_ARCHITECTURE.md).

Gates:
1. Cryptographic JWT verification (user_id resolution).
2. Workspace membership verification (asserts ACTIVE status, real-time revocation check).
3. Client brand assignment verification (asserts ACTIVE status, independent assignment check).
4. Role permission enforcement (WORKSPACE_ADMIN, BRAND_MANAGER, CONTENT_CREATOR).
5. Transaction-local session context setting via parameterized set_config().
"""
import logging
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Path, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemException
from app.core.security.jwt_verifier import AuthenticatedUser
from app.db.session import get_db
from app.models.client import ClientBrand, ClientMembership, ClientMembershipStatus, ClientRole
from app.models.workspace import MembershipStatus, UserRole, WorkspaceMembership
from app.modules.auth.dependencies import get_current_user

logger = logging.getLogger("sylvar.auth.pipeline")


@dataclass(frozen=True)
class SecurityContext:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_role: UserRole
    client_id: uuid.UUID | None = None
    client_role: ClientRole | None = None


async def _set_tenant_local_context(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
    client_id: uuid.UUID | None,
) -> None:
    """Set transaction-local PostgreSQL RLS context using bind-safe set_config."""
    bind = db.bind
    dialect_name = bind.dialect.name if bind else ""
    if dialect_name != "postgresql":
        return

    try:
        # Always write all three settings. Passing an empty value clears a prior
        # scope in the same transaction instead of accidentally retaining it.
        for setting_name, value in (
            ("app.current_user_id", user_id),
            ("app.current_workspace_id", workspace_id),
            ("app.current_client_id", client_id),
        ):
            await db.execute(
                text("SELECT set_config(:setting_name, :setting_value, true)"),
                {
                    "setting_name": setting_name,
                    "setting_value": str(value) if value is not None else "",
                },
            )
    except Exception as exc:  # fail closed: RLS context is mandatory on PostgreSQL
        logger.exception("Failed to establish PostgreSQL tenant context")
        raise ProblemException(
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="TENANT_CONTEXT_UNAVAILABLE",
            title="Service Unavailable",
            detail="Tenant authorization context could not be established.",
        ) from exc


async def get_workspace_membership(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> WorkspaceMembership:
    """Gate 2: Real-time workspace membership and active status check."""
    stmt = select(WorkspaceMembership).where(
        WorkspaceMembership.workspace_id == workspace_id,
        WorkspaceMembership.user_id == user_id,
    )
    result = await db.execute(stmt)
    membership = result.scalar_one_or_none()

    if not membership:
        raise ProblemException(
            status=status.HTTP_403_FORBIDDEN,
            code="WORKSPACE_MEMBERSHIP_REQUIRED",
            title="Forbidden",
            detail="User is not a member of this workspace.",
        )

    if membership.status != MembershipStatus.ACTIVE.value or membership.revoked_at is not None:
        raise ProblemException(
            status=status.HTTP_403_FORBIDDEN,
            code="MEMBERSHIP_REVOKED",
            title="Forbidden",
            detail="Workspace membership is revoked or suspended.",
        )

    return membership


async def get_client_membership(
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ClientMembership:
    """Gate 3: Real-time independent client brand assignment check (ADR-003).

    Workspace Admin authority does NOT grant ambient client brand access without explicit assignment.
    """
    # 1. Verify client brand exists in this workspace
    client_stmt = select(ClientBrand).where(
        ClientBrand.id == client_id,
        ClientBrand.workspace_id == workspace_id,
    )
    client_result = await db.execute(client_stmt)
    brand = client_result.scalar_one_or_none()
    if not brand:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="CLIENT_NOT_FOUND",
            title="Not Found",
            detail="Client brand not found in this workspace.",
        )

    # 2. Verify explicit client assignment
    stmt = select(ClientMembership).where(
        ClientMembership.workspace_id == workspace_id,
        ClientMembership.client_id == client_id,
        ClientMembership.user_id == user_id,
    )
    result = await db.execute(stmt)
    membership = result.scalar_one_or_none()

    if not membership:
        raise ProblemException(
            status=status.HTTP_403_FORBIDDEN,
            code="CLIENT_ASSIGNMENT_REQUIRED",
            title="Forbidden",
            detail="Explicit client assignment is required to access this client brand.",
        )

    if membership.status != ClientMembershipStatus.ACTIVE.value or membership.revoked_at is not None:
        raise ProblemException(
            status=status.HTTP_403_FORBIDDEN,
            code="CLIENT_ASSIGNMENT_REVOKED",
            title="Forbidden",
            detail="Client brand assignment is revoked.",
        )

    return membership


def require_workspace_role(
    allowed_roles: set[UserRole],
) -> Callable[..., Coroutine[Any, Any, SecurityContext]]:
    """FastAPI dependency factory for workspace-scoped actions."""

    async def _dependency(
        w_id: uuid.UUID = Path(..., description="Workspace UUID"),
        current_user: AuthenticatedUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> SecurityContext:
        # The user context allows the RLS policy to find this user's membership.
        await _set_tenant_local_context(db, current_user.user_id, None, None)
        membership = await get_workspace_membership(w_id, current_user.user_id, db)
        user_role = UserRole(membership.role)

        if user_role not in allowed_roles:
            raise ProblemException(
                status=status.HTTP_403_FORBIDDEN,
                code="INSUFFICIENT_PERMISSIONS",
                title="Forbidden",
                detail=f"Action requires one of {[r.value for r in allowed_roles]}, but caller has {user_role.value}.",
            )

        await _set_tenant_local_context(db, current_user.user_id, w_id, None)
        return SecurityContext(
            user_id=current_user.user_id,
            workspace_id=w_id,
            workspace_role=user_role,
        )

    return _dependency


def require_client_role(
    allowed_client_roles: set[ClientRole],
) -> Callable[..., Coroutine[Any, Any, SecurityContext]]:
    """FastAPI dependency factory for client-scoped actions."""

    async def _dependency(
        w_id: uuid.UUID = Path(..., description="Workspace UUID"),
        c_id: uuid.UUID = Path(..., description="Client Brand UUID"),
        current_user: AuthenticatedUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> SecurityContext:
        # Resolve membership under the authenticated user context first.
        await _set_tenant_local_context(db, current_user.user_id, None, None)
        ws_membership = await get_workspace_membership(w_id, current_user.user_id, db)
        user_ws_role = UserRole(ws_membership.role)

        # Brand lookup requires the verified workspace context. Client assignment
        # remains independently checked; workspace admin is not ambient access.
        await _set_tenant_local_context(db, current_user.user_id, w_id, None)
        client_membership = await get_client_membership(w_id, c_id, current_user.user_id, db)
        client_role = ClientRole(client_membership.client_role)

        if client_role not in allowed_client_roles:
            raise ProblemException(
                status=status.HTTP_403_FORBIDDEN,
                code="INSUFFICIENT_PERMISSIONS",
                title="Forbidden",
                detail=f"Action requires client role {[r.value for r in allowed_client_roles]}, but user is {client_role.value}.",
            )

        await _set_tenant_local_context(db, current_user.user_id, w_id, c_id)
        return SecurityContext(
            user_id=current_user.user_id,
            workspace_id=w_id,
            workspace_role=user_ws_role,
            client_id=c_id,
            client_role=client_role,
        )

    return _dependency


# Pre-configured dependency shortcuts
require_workspace_admin = require_workspace_role({UserRole.WORKSPACE_ADMIN})
require_workspace_member = require_workspace_role({
    UserRole.WORKSPACE_ADMIN,
    UserRole.BRAND_MANAGER,
    UserRole.CONTENT_CREATOR,
})

require_brand_manager = require_client_role({ClientRole.BRAND_MANAGER})
require_client_member = require_client_role({ClientRole.BRAND_MANAGER, ClientRole.CONTENT_CREATOR})
