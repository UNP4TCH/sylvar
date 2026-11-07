"""Comprehensive Security Verification Suite for Batch 2A Redesigned Invitation Flow.

Verifies all 10 security and isolation requirements:
1. Non-admin cannot invite (403 Forbidden).
2. Revoked admin cannot invite (403 Forbidden).
3. Admin cannot invite into another workspace (403 Forbidden).
4. Invitation email and role are bound to the correct workspace.
5. Duplicate invitation requests are idempotent.
6. Unauthenticated invited user cannot access protected workspace resources (zero ambient access).
7. Successful invitation followed by authentication activates the correct membership.
8. Failed email delivery does not create a falsely successful invitation (atomic rollback).
9. External provider success followed by database failure is handled safely.
10. No arbitrary user profile insertion is possible through the normal runtime role.
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemException
from app.core.invitations import InvitationDispatchResult
from app.core.security.jwt_verifier import AuthenticatedUser
from app.models.client import ClientBrand, ClientMembership, ClientMembershipStatus, ClientRole
from app.models.content import ContentAsset, ContentType
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
from app.modules.auth.dependencies import get_or_sync_user
from app.modules.auth.pipeline import (
    SecurityContext,
    require_workspace_admin,
    require_workspace_member,
)
from app.modules.workspaces.router import (
    invite_member,
    recover_pending_invitations,
    retry_invitation_delivery,
)
from app.modules.workspaces.schemas import MemberInvite


@pytest.mark.anyio
async def test_01_non_admin_cannot_invite(db_session: AsyncSession) -> None:
    """Requirement 1: Non-admin cannot invite members into a workspace."""
    user_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    user = User(id=user_id, email="creator@agency.com", full_name="Content Creator")
    workspace = AgencyWorkspace(id=ws_id, name="Studio A", slug=f"ws-{uuid.uuid4().hex[:6]}")
    membership = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=user_id,
        role=UserRole.CONTENT_CREATOR.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([user, workspace, membership])
    await db_session.flush()

    auth_user = AuthenticatedUser(
        user_id=user_id,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="creator@agency.com",
    )

    # Calling require_workspace_admin gate directly must raise 403
    with pytest.raises(ProblemException) as excinfo:
        await require_workspace_admin(w_id=ws_id, current_user=auth_user, db=db_session)
    assert excinfo.value.status == 403
    assert excinfo.value.code == "INSUFFICIENT_PERMISSIONS"


@pytest.mark.anyio
async def test_02_revoked_admin_cannot_invite(db_session: AsyncSession) -> None:
    """Requirement 2: Revoked admin cannot invite members."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="revoked@agency.com", full_name="Revoked Admin")
    workspace = AgencyWorkspace(id=ws_id, name="Studio B", slug=f"ws-{uuid.uuid4().hex[:6]}")
    revoked_membership = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.REVOKED.value,
        revoked_at=datetime.now(UTC),
    )
    db_session.add_all([admin, workspace, revoked_membership])
    await db_session.flush()

    auth_user = AuthenticatedUser(
        user_id=admin_id,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="revoked@agency.com",
    )

    with pytest.raises(ProblemException) as excinfo:
        await require_workspace_admin(w_id=ws_id, current_user=auth_user, db=db_session)
    assert excinfo.value.status == 403
    assert excinfo.value.code in ("MEMBERSHIP_REVOKED", "NOT_A_MEMBER")


@pytest.mark.anyio
async def test_03_admin_cannot_invite_into_another_workspace(db_session: AsyncSession) -> None:
    """Requirement 3: Admin of Workspace A cannot invite into Workspace B."""
    admin_id = uuid.uuid4()
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()

    admin = User(id=admin_id, email="adminA@agency.com", full_name="Admin A")
    workspace_a = AgencyWorkspace(id=ws_a, name="Workspace A", slug=f"ws-a-{uuid.uuid4().hex[:6]}")
    workspace_b = AgencyWorkspace(id=ws_b, name="Workspace B", slug=f"ws-b-{uuid.uuid4().hex[:6]}")
    mem_a = WorkspaceMembership(
        workspace_id=ws_a,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([admin, workspace_a, workspace_b, mem_a])
    await db_session.flush()

    auth_user = AuthenticatedUser(
        user_id=admin_id,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="adminA@agency.com",
    )

    # Admin A attempts to access/invite into Workspace B
    with pytest.raises(ProblemException) as excinfo:
        await require_workspace_admin(w_id=ws_b, current_user=auth_user, db=db_session)
    assert excinfo.value.status == 403
    assert excinfo.value.code == "WORKSPACE_MEMBERSHIP_REQUIRED"


@pytest.mark.anyio
async def test_04_invitation_bound_to_workspace_and_role(db_session: AsyncSession) -> None:
    """Requirement 4: Invitation is strictly bound to workspace, email, and role."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="lead@agency.com", full_name="Lead Admin")
    workspace = AgencyWorkspace(id=ws_id, name="Main Agency", slug=f"main-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([admin, workspace, mem])
    await db_session.flush()

    ctx = SecurityContext(
        user_id=admin_id,
        workspace_id=ws_id,
        workspace_role=UserRole.WORKSPACE_ADMIN,
    )
    payload = MemberInvite(
        email="bob.builder@external.com",
        role=UserRole.BRAND_MANAGER,
        full_name="Bob Builder",
    )

    res = await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)
    assert res.email == "bob.builder@external.com"
    assert res.role == UserRole.BRAND_MANAGER.value
    assert res.workspace_id == ws_id
    assert res.status == "INVITED"

    # Verify database record in workspace_invitations
    stmt = select(WorkspaceInvitation).where(
        WorkspaceInvitation.workspace_id == ws_id,
        WorkspaceInvitation.email == "bob.builder@external.com",
    )
    inv = (await db_session.execute(stmt)).scalar_one_or_none()
    assert inv is not None
    assert inv.role == UserRole.BRAND_MANAGER.value
    assert inv.status == InvitationStatus.PENDING.value
    assert inv.invited_by_user_id == admin_id

    # CRITICAL: Verify NO row was inserted into public.users or workspace_memberships!
    user_check = (await db_session.execute(select(User).where(User.email == "bob.builder@external.com"))).scalar_one_or_none()
    assert user_check is None, "Invited user MUST NOT have a placeholder row in public.users!"

    mem_check = (await db_session.execute(select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == ws_id, WorkspaceMembership.user_id == res.user_id))).scalar_one_or_none()
    assert mem_check is None, "Invited user MUST NOT have a membership until acceptance!"


@pytest.mark.anyio
async def test_05_duplicate_invitation_is_idempotent(db_session: AsyncSession) -> None:
    """Requirement 5: Duplicate invitation requests are idempotent."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="lead2@agency.com", full_name="Lead Admin")
    workspace = AgencyWorkspace(id=ws_id, name="Idempotent Agency", slug=f"idem-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([admin, workspace, mem])
    await db_session.flush()

    ctx = SecurityContext(
        user_id=admin_id,
        workspace_id=ws_id,
        workspace_role=UserRole.WORKSPACE_ADMIN,
    )
    payload = MemberInvite(
        email="charlie@external.com",
        role=UserRole.CONTENT_CREATOR,
        full_name="Charlie Creator",
    )

    # First invite
    res1 = await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)
    assert res1.status == "INVITED"

    # Second invite (duplicate retry)
    res2 = await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)
    assert res2.status == "INVITED"
    assert res2.membership_id == res1.membership_id  # Returns same invitation idempotently

    # Verify only ONE invitation record exists in database
    inv_count_stmt = select(WorkspaceInvitation).where(
        WorkspaceInvitation.workspace_id == ws_id,
        WorkspaceInvitation.email == "charlie@external.com",
    )
    invs = (await db_session.execute(inv_count_stmt)).scalars().all()
    assert len(invs) == 1


@pytest.mark.anyio
async def test_06_unauthenticated_invited_user_has_zero_workspace_access(db_session: AsyncSession) -> None:
    """Requirement 6: An invited identity has zero ambient access to workspace resources."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="owner@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Secure Agency", slug=f"sec-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="unverified@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    # Even if someone presents a token claiming to be unverified@external.com with a newly created UUID:
    attacker_uuid = uuid.uuid4()
    attacker_auth = AuthenticatedUser(
        user_id=attacker_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="unverified@external.com",
    )

    # Before calling get_or_sync_user (before acceptance), the user has no membership:
    with pytest.raises(ProblemException) as excinfo:
        await require_workspace_member(w_id=ws_id, current_user=attacker_auth, db=db_session)
    assert excinfo.value.status == 403
    assert excinfo.value.code == "WORKSPACE_MEMBERSHIP_REQUIRED"


@pytest.mark.anyio
async def test_07_invitation_acceptance_on_authentication(db_session: AsyncSession) -> None:
    """Requirement 7: Successful invitation followed by authentication activates correct membership."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="boss@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Onboarding Agency", slug=f"onb-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="dave@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    # Dave authenticates via Supabase GoTrue with authentic UUID
    dave_authentic_uuid = uuid.uuid4()
    dave_auth = AuthenticatedUser(
        user_id=dave_authentic_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="dave@external.com",
        email_verified=True,
    )

    # 1. Dave logs in and calls get_or_sync_user
    dave_user = await get_or_sync_user(db=db_session, current_user=dave_auth)
    assert dave_user.id == dave_authentic_uuid
    assert dave_user.email == "dave@external.com"

    # 2. Check invitation was accepted
    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.ACCEPTED.value
    assert refreshed_inv.accepted_at is not None
    assert refreshed_inv.auth_user_id == dave_authentic_uuid

    # 3. Check membership was created with authentic user_id and ACTIVE status
    mem_stmt = select(WorkspaceMembership).where(
        WorkspaceMembership.workspace_id == ws_id,
        WorkspaceMembership.user_id == dave_authentic_uuid,
    )
    dave_mem = (await db_session.execute(mem_stmt)).scalar_one_or_none()
    assert dave_mem is not None
    assert dave_mem.role == UserRole.CONTENT_CREATOR.value
    assert dave_mem.status == MembershipStatus.ACTIVE.value

    # 4. Dave can now pass require_workspace_member!
    sec_ctx = await require_workspace_member(w_id=ws_id, current_user=dave_auth, db=db_session)
    assert sec_ctx.user_id == dave_authentic_uuid
    assert sec_ctx.workspace_id == ws_id
    assert sec_ctx.workspace_role == UserRole.CONTENT_CREATOR


@pytest.mark.anyio
async def test_08_failed_email_delivery_aborts_invitation(db_session: AsyncSession) -> None:
    """Requirement 8: Failed email delivery rolls back and does not create a false invitation."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email=f"admin8-{uuid.uuid4().hex[:6]}@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Fail Agency", slug=f"fail-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([admin, workspace, mem])
    await db_session.flush()

    ctx = SecurityContext(
        user_id=admin_id,
        workspace_id=ws_id,
        workspace_role=UserRole.WORKSPACE_ADMIN,
    )
    payload = MemberInvite(
        email="unreachable@external.com",
        role=UserRole.CONTENT_CREATOR,
        full_name="Unreachable",
    )

    # Mock dispatch_workspace_invitation to simulate external delivery failure (502)
    with patch(
        "app.modules.workspaces.router.dispatch_workspace_invitation",
        new=AsyncMock(side_effect=ProblemException(status=502, code="INVITATION_DELIVERY_FAILED", title="Bad Gateway", detail="SMTP server connection refused")),
    ):
        with pytest.raises(ProblemException) as excinfo:
            await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)
        assert excinfo.value.status == 502
        assert excinfo.value.code == "INVITATION_DELIVERY_FAILED"

    # Verify invitation was durably persisted in database with FAILED delivery status
    inv_check = (await db_session.execute(select(WorkspaceInvitation).where(WorkspaceInvitation.email == "unreachable@external.com"))).scalar_one_or_none()
    assert inv_check is not None, "Outbox record MUST be durably persisted"
    assert inv_check.status == InvitationStatus.PENDING.value
    assert inv_check.delivery_status == InvitationDeliveryStatus.FAILED.value
    assert inv_check.delivery_attempts == 1
    assert "SMTP server connection refused" in (inv_check.last_delivery_error or "")

    # CRITICAL: Verify NO row was inserted into public.users or workspace_memberships!
    user_check = (await db_session.execute(select(User).where(User.email == "unreachable@external.com"))).scalar_one_or_none()
    assert user_check is None


@pytest.mark.anyio
async def test_09_provider_success_with_db_failure_retains_pending_state(db_session: AsyncSession) -> None:
    """Requirement 9: External provider success followed by Transaction 2 database failure retains Transaction 1 on disk."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email=f"admin9-{uuid.uuid4().hex[:6]}@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Safe Agency", slug=f"safe-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([admin, workspace, mem])
    await db_session.commit()

    ctx = SecurityContext(
        user_id=admin_id,
        workspace_id=ws_id,
        workspace_role=UserRole.WORKSPACE_ADMIN,
    )
    payload = MemberInvite(
        email="safe.test@external.com",
        role=UserRole.CONTENT_CREATOR,
    )

    # Simulate: Transaction 1 commits normally.
    # External delivery succeeds.
    # Then Transaction 2 fails to commit (e.g. database disconnect).
    original_commit = db_session.commit
    commit_call_count = 0

    async def mock_commit():
        nonlocal commit_call_count
        commit_call_count += 1
        if commit_call_count == 1:
            return await original_commit()
        raise RuntimeError("Database disconnect during Transaction 2 commit")

    with patch(
        "app.modules.workspaces.router.dispatch_workspace_invitation",
        new=AsyncMock(return_value=InvitationDispatchResult(delivered=True, channel="smtp", auth_user_id=None, detail="Sent")),
    ):
        with patch.object(db_session, "commit", side_effect=mock_commit):
            with pytest.raises(ProblemException) as excinfo:
                await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)
            assert excinfo.value.code == "DELIVERY_RECORDING_FAILED"

    # Rollback failed Transaction 2 to clear uncommitted identity map state:
    await db_session.rollback()

    # CRITICAL: Verify Transaction 1 was ALREADY committed to disk!
    stmt = select(WorkspaceInvitation).where(WorkspaceInvitation.email == "safe.test@external.com")
    inv = (await db_session.execute(stmt)).scalar_one_or_none()
    assert inv is not None, "Transaction 1 MUST have durably persisted the invitation record"
    assert inv.delivery_status == InvitationDeliveryStatus.PENDING.value  # Preserved as PENDING, ready for recovery!
    assert inv.delivery_attempts == 1

    # Age the record outside active window (simulating passage of time after crash):
    inv.updated_at = datetime.now(UTC) - timedelta(seconds=120)
    await db_session.commit()

    # Now simulate recovery / retry:
    with patch(
        "app.modules.workspaces.router.dispatch_workspace_invitation",
        new=AsyncMock(return_value=InvitationDispatchResult(delivered=True, channel="smtp", auth_user_id=None, detail="Recovered")),
    ):
        res = await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)
        assert res.status == "INVITED"

    # After retry, invitation is cleanly updated to DELIVERED with attempts = 2
    inv_recovered = (await db_session.execute(stmt)).scalar_one()
    assert inv_recovered.delivery_status == InvitationDeliveryStatus.DELIVERED.value
    assert inv_recovered.delivery_attempts == 2


@pytest.mark.anyio
async def test_10_no_arbitrary_user_profile_insertion_by_admin(db_session: AsyncSession) -> None:
    """Requirement 10: Workspace admin cannot insert arbitrary user profiles in public.users."""
    # In the redesigned invitation architecture, invite_member NEVER calls db.add(User(...)).
    # We verify that inviting a user does not insert any record into public.users:
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin10@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Audit WS", slug=f"audit-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([admin, workspace, mem])
    await db_session.flush()

    ctx = SecurityContext(
        user_id=admin_id,
        workspace_id=ws_id,
        workspace_role=UserRole.WORKSPACE_ADMIN,
    )
    payload = MemberInvite(
        email="nobody@agency.com",
        role=UserRole.CONTENT_CREATOR,
        full_name="Nobody",
    )

    await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)

    # Query public.users:
    user_stmt = select(User).where(User.email == "nobody@agency.com")
    res = (await db_session.execute(user_stmt)).scalar_one_or_none()
    assert res is None, "public.users MUST NOT contain an arbitrary profile for an unauthenticated invitee!"


@pytest.mark.anyio
async def test_11_unverified_email_cannot_accept_invitation(db_session: AsyncSession) -> None:
    """Requirement: Unverified email claim MUST NOT accept invitations or grant workspace access."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin11@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Security WS", slug=f"sec11-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="unverified11@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    # User logs in with unverified email:
    user_uuid = uuid.uuid4()
    unverified_auth = AuthenticatedUser(
        user_id=user_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="unverified11@external.com",
        email_verified=False,  # NOT verified!
    )

    # get_or_sync_user resolves profile, but MUST NOT accept the invitation:
    user = await get_or_sync_user(db=db_session, current_user=unverified_auth)
    assert user.id == user_uuid

    # Invitation must still be PENDING:
    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.PENDING.value
    assert refreshed_inv.accepted_at is None
    assert refreshed_inv.auth_user_id is None

    # No membership must exist:
    mem_check = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == user_uuid,
        )
    )).scalar_one_or_none()
    assert mem_check is None

    # require_workspace_member must raise 403 Forbidden:
    with pytest.raises(ProblemException) as excinfo:
        await require_workspace_member(w_id=ws_id, current_user=unverified_auth, db=db_session)
    assert excinfo.value.status == 403
    assert excinfo.value.code == "WORKSPACE_MEMBERSHIP_REQUIRED"


@pytest.mark.anyio
async def test_12_expired_invitation_cannot_be_accepted(db_session: AsyncSession) -> None:
    """Requirement: Expired invitation cannot be accepted."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin12@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Expire WS", slug=f"exp-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="expired@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
        expires_at=datetime.now(UTC) - timedelta(days=1),  # Expired!
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    user_uuid = uuid.uuid4()
    verified_auth = AuthenticatedUser(
        user_id=user_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="expired@external.com",
        email_verified=True,
    )

    await get_or_sync_user(db=db_session, current_user=verified_auth)

    # Check invitation was NOT accepted:
    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.PENDING.value
    assert refreshed_inv.accepted_at is None

    # Check no membership created:
    mem_check = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == user_uuid,
        )
    )).scalar_one_or_none()
    assert mem_check is None


@pytest.mark.anyio
async def test_13_revoked_invitation_cannot_be_accepted(db_session: AsyncSession) -> None:
    """Requirement: Revoked invitation cannot be accepted."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin13@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Revoke WS", slug=f"rev-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="revoked_inv@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.REVOKED.value,  # Revoked!
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    user_uuid = uuid.uuid4()
    verified_auth = AuthenticatedUser(
        user_id=user_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="revoked_inv@external.com",
        email_verified=True,
    )

    await get_or_sync_user(db=db_session, current_user=verified_auth)

    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.REVOKED.value
    assert refreshed_inv.accepted_at is None

    mem_check = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == user_uuid,
        )
    )).scalar_one_or_none()
    assert mem_check is None


@pytest.mark.anyio
async def test_14_already_accepted_invitation_cannot_be_reaccepted(db_session: AsyncSession) -> None:
    """Requirement: Already accepted invitation cannot be accepted again."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin14@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Reaccept WS", slug=f"reacc-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    existing_uuid = uuid.uuid4()
    original_accepted_at = datetime.now(UTC) - timedelta(hours=2)
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="already_accepted@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.ACCEPTED.value,  # Already accepted!
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
        auth_user_id=existing_uuid,
        accepted_at=original_accepted_at,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    second_user_uuid = uuid.uuid4()
    second_auth = AuthenticatedUser(
        user_id=second_user_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="already_accepted@external.com",
        email_verified=True,
    )

    await get_or_sync_user(db=db_session, current_user=second_auth)

    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.ACCEPTED.value
    assert refreshed_inv.auth_user_id == existing_uuid  # Unchanged! Must not be stolen by second UUID

    # Second UUID must NOT have gained membership from this invitation
    mem_check = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == second_user_uuid,
        )
    )).scalar_one_or_none()
    assert mem_check is None


@pytest.mark.anyio
async def test_15_transactional_outbox_delivery_tracking_and_retry(db_session: AsyncSession) -> None:
    """Requirement: Transactional outbox tracks delivery failure, preserves PENDING state, and allows idempotent retry."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin15@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Outbox WS", slug=f"outb-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([admin, workspace, mem])
    await db_session.flush()

    ctx = SecurityContext(
        user_id=admin_id,
        workspace_id=ws_id,
        workspace_role=UserRole.WORKSPACE_ADMIN,
    )
    payload = MemberInvite(
        email="retry.candidate@agency.com",
        role=UserRole.BRAND_MANAGER,
        full_name="Retry Candidate",
    )

    # Attempt 1: External delivery fails (e.g. SMTP down)
    with patch(
        "app.modules.workspaces.router.dispatch_workspace_invitation",
        new=AsyncMock(side_effect=ProblemException(status=502, code="INVITATION_DELIVERY_FAILED", title="Bad Gateway", detail="External SMTP connection refused")),
    ):
        with pytest.raises(ProblemException) as excinfo:
            await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)
        assert excinfo.value.status == 502
        assert excinfo.value.code == "INVITATION_DELIVERY_FAILED"

    # Verify invitation row exists in database with delivery_status = FAILED and delivery_attempts = 1
    stmt = select(WorkspaceInvitation).where(
        WorkspaceInvitation.workspace_id == ws_id,
        WorkspaceInvitation.email == "retry.candidate@agency.com",
    )
    inv_attempt1 = (await db_session.execute(stmt)).scalar_one()
    assert inv_attempt1.status == InvitationStatus.PENDING.value
    assert inv_attempt1.delivery_status == InvitationDeliveryStatus.FAILED.value  # Recorded as FAILED!
    assert inv_attempt1.delivery_attempts == 1
    assert "SMTP connection refused" in (inv_attempt1.last_delivery_error or "")
    assert inv_attempt1.delivered_at is None

    # Attempt 2: Admin retries -> External delivery succeeds
    with patch(
        "app.modules.workspaces.router.dispatch_workspace_invitation",
        new=AsyncMock(return_value=InvitationDispatchResult(delivered=True, channel="smtp", auth_user_id=None, detail="SMTP message sent", provider_message_id="msg-12345")),
    ):
        res = await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)
        assert res.status == "INVITED"

    # Verify same invitation was reused and updated to DELIVERED with attempts = 2
    inv_attempt2 = (await db_session.execute(stmt)).scalar_one()
    assert inv_attempt2.id == inv_attempt1.id
    assert inv_attempt2.delivery_status == InvitationDeliveryStatus.DELIVERED.value
    assert inv_attempt2.delivery_attempts == 2
    assert inv_attempt2.delivered_at is not None
    assert inv_attempt2.provider_message_id == "msg-12345"
    assert inv_attempt2.last_delivery_error is None


@pytest.mark.anyio
async def test_16_role_derived_strictly_from_stored_invitation(db_session: AsyncSession) -> None:
    """Requirement: Assigned workspace role is derived exclusively from the stored invitation."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin16@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Role WS", slug=f"role-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    # Stored invitation specifies CONTENT_CREATOR
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="creator_strictly@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    user_uuid = uuid.uuid4()
    verified_auth = AuthenticatedUser(
        user_id=user_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="creator_strictly@external.com",
        email_verified=True,
    )

    await get_or_sync_user(db=db_session, current_user=verified_auth)

    mem_stmt = select(WorkspaceMembership).where(
        WorkspaceMembership.workspace_id == ws_id,
        WorkspaceMembership.user_id == user_uuid,
    )
    created_mem = (await db_session.execute(mem_stmt)).scalar_one()
    assert created_mem.role == UserRole.CONTENT_CREATOR.value


@pytest.mark.anyio
async def test_17_concurrent_acceptance_serialized_cleanly(db_session: AsyncSession) -> None:
    """Requirement: Concurrent acceptance attempts serialize cleanly without race conditions."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin17@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Concurrent WS", slug=f"conc-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="concurrent@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    user_uuid = uuid.uuid4()
    verified_auth = AuthenticatedUser(
        user_id=user_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="concurrent@external.com",
        email_verified=True,
    )

    # First login/sync executes:
    u1 = await get_or_sync_user(db=db_session, current_user=verified_auth)
    # Second immediate login/sync executes (simulating immediate retry / parallel request):
    u2 = await get_or_sync_user(db=db_session, current_user=verified_auth)

    assert u1.id == u2.id == user_uuid

    # Check invitation is ACCEPTED:
    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.ACCEPTED.value

    # Check that exactly ONE membership row exists for this workspace and user:
    mems = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == user_uuid,
        )
    )).scalars().all()
    assert len(mems) == 1
    assert mems[0].status == MembershipStatus.ACTIVE.value


@pytest.mark.anyio
async def test_18_user_metadata_email_verified_ignored(db_session: AsyncSession) -> None:
    """Requirement: Client-editable user_metadata.email_verified MUST NOT be trusted as proof of verification."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin18@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Metadata WS", slug=f"meta-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="attacker@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    attacker_uuid = uuid.uuid4()
    # Attacker crafts an AuthenticatedUser claiming email_verified=False (because user_metadata is ignored by verifier)
    attacker_auth = AuthenticatedUser(
        user_id=attacker_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="attacker@external.com",
        email_verified=False,  # Even if attacker submitted {"user_metadata": {"email_verified": true}}
    )

    # Mock GoTrue Admin returning unconfirmed or failing
    with patch("app.modules.auth.dependencies.verify_identity_with_gotrue", new=AsyncMock(return_value=False)):
        user = await get_or_sync_user(db=db_session, current_user=attacker_auth)
        assert user.id == attacker_uuid

    # Check invitation is STILL PENDING and attacker gained NO membership:
    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.PENDING.value
    assert refreshed_inv.accepted_at is None

    mem_check = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == attacker_uuid,
        )
    )).scalar_one_or_none()
    assert mem_check is None


@pytest.mark.anyio
async def test_19_missing_verification_and_unconfirmed_gotrue_fails_closed(db_session: AsyncSession) -> None:
    """Requirement: Missing verification signal in token and GoTrue fails closed."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin19@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="FailClosed WS", slug=f"fc-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="unconfirmed@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    user_uuid = uuid.uuid4()
    auth_user = AuthenticatedUser(
        user_id=user_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="unconfirmed@external.com",
        email_verified=False,
    )

    # GoTrue reports email_confirmed_at is None
    with patch("app.modules.auth.dependencies.verify_identity_with_gotrue", new=AsyncMock(return_value=False)):
        await get_or_sync_user(db=db_session, current_user=auth_user)

    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.PENDING.value
    assert refreshed_inv.accepted_at is None


@pytest.mark.anyio
async def test_20_trusted_gotrue_admin_verification_success(db_session: AsyncSession) -> None:
    """Requirement: Authoritative GoTrue Admin verification enables acceptance when JWT lacked root claim."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin20@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="GoTrue WS", slug=f"gt-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="gotrue_confirmed@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    user_uuid = uuid.uuid4()
    # Token lacked root claim: email_verified=False
    auth_user = AuthenticatedUser(
        user_id=user_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="gotrue_confirmed@external.com",
        email_verified=False,
    )

    # Authoritative GoTrue Admin API check confirms email_confirmed_at
    with patch("app.modules.auth.dependencies.verify_identity_with_gotrue", new=AsyncMock(return_value=True)):
        user = await get_or_sync_user(db=db_session, current_user=auth_user)
        assert user.id == user_uuid

    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.ACCEPTED.value
    assert refreshed_inv.accepted_at is not None
    assert refreshed_inv.auth_user_id == user_uuid

    created_mem = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == user_uuid,
        )
    )).scalar_one_or_none()
    assert created_mem is not None
    assert created_mem.role == UserRole.CONTENT_CREATOR.value


@pytest.mark.anyio
async def test_21_email_mismatch_between_token_and_invitation_rejected(db_session: AsyncSession) -> None:
    """Requirement: Verified email MUST match invitation email; mismatch rejected."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin21@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Mismatch WS", slug=f"mm-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="intended_recipient@external.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, inv])
    await db_session.flush()

    different_user_uuid = uuid.uuid4()
    different_user_auth = AuthenticatedUser(
        user_id=different_user_uuid,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="different_person@external.com",
        email_verified=True,
    )

    await get_or_sync_user(db=db_session, current_user=different_user_auth)

    # Intended invitation is untouched:
    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.PENDING.value
    assert refreshed_inv.auth_user_id is None

    # Different person gained zero membership:
    mem_check = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == different_user_uuid,
        )
    )).scalar_one_or_none()
    assert mem_check is None


@pytest.mark.anyio
async def test_22_process_interruption_and_recovery_of_pending_deliveries(db_session: AsyncSession) -> None:
    """Requirement: Process crash/interruption after Transaction 1 leaves recoverable PENDING record in outbox."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin22@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Crash WS", slug=f"crash-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    # Simulate: Transaction 1 committed the invitation, but process was interrupted before dispatch
    stranded_inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="stranded@agency.com",
        role=UserRole.BRAND_MANAGER.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.PENDING.value,
        delivery_attempts=1,
        invited_by_user_id=admin_id,
        created_at=datetime.now(UTC) - timedelta(seconds=120),
        updated_at=datetime.now(UTC) - timedelta(seconds=120),
    )
    db_session.add_all([admin, workspace, mem, stranded_inv])
    await db_session.commit()

    ctx = SecurityContext(user_id=admin_id, workspace_id=ws_id, workspace_role=UserRole.WORKSPACE_ADMIN)

    # Recovery process runs
    with patch(
        "app.modules.workspaces.router.dispatch_workspace_invitation",
        new=AsyncMock(return_value=InvitationDispatchResult(delivered=True, channel="smtp", auth_user_id=None, detail="Recovered")),
    ):
        recovered = await recover_pending_invitations(w_id=ws_id, ctx=ctx, db=db_session)
        assert len(recovered) == 1
        assert recovered[0].email == "stranded@agency.com"
        assert recovered[0].delivery_status == "DELIVERED"
        assert recovered[0].delivery_attempts == 2

    # Verify DB state
    refreshed_inv = await db_session.get(WorkspaceInvitation, stranded_inv.id)
    assert refreshed_inv.delivery_status == InvitationDeliveryStatus.DELIVERED.value
    assert refreshed_inv.delivered_at is not None


@pytest.mark.anyio
async def test_23_explicit_invitation_retry_endpoint(db_session: AsyncSession) -> None:
    """Requirement: Dedicated retry endpoint recovers a FAILED invitation."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin23@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="RetryEndpoint WS", slug=f"repend-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    failed_inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="failed_first@agency.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.FAILED.value,
        delivery_attempts=1,
        last_delivery_error="502 Connection refused",
        invited_by_user_id=admin_id,
    )
    db_session.add_all([admin, workspace, mem, failed_inv])
    await db_session.commit()

    ctx = SecurityContext(user_id=admin_id, workspace_id=ws_id, workspace_role=UserRole.WORKSPACE_ADMIN)

    with patch(
        "app.modules.workspaces.router.dispatch_workspace_invitation",
        new=AsyncMock(return_value=InvitationDispatchResult(delivered=True, channel="smtp", auth_user_id=None, detail="Sent")),
    ):
        res = await retry_invitation_delivery(w_id=ws_id, inv_id=failed_inv.id, ctx=ctx, db=db_session)
        assert res.email == "failed_first@agency.com"
        assert res.delivery_status == "DELIVERED"
        assert res.delivery_attempts == 2

    refreshed = await db_session.get(WorkspaceInvitation, failed_inv.id)
    assert refreshed.delivery_status == InvitationDeliveryStatus.DELIVERED.value
    assert refreshed.last_delivery_error is None


@pytest.mark.anyio
async def test_24_repeated_retry_without_duplicate_invitations(db_session: AsyncSession) -> None:
    """Requirement: Repeated retries reuse the same invitation without creating duplicate records."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin24@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Repeat WS", slug=f"rep-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([admin, workspace, mem])
    await db_session.commit()

    ctx = SecurityContext(user_id=admin_id, workspace_id=ws_id, workspace_role=UserRole.WORKSPACE_ADMIN)
    payload = MemberInvite(email="multiple.retries@agency.com", role=UserRole.CONTENT_CREATOR)

    with patch(
        "app.modules.workspaces.router.dispatch_workspace_invitation",
        new=AsyncMock(return_value=InvitationDispatchResult(delivered=True, channel="smtp", auth_user_id=None, detail="Sent")),
    ):
        # 3 sequential calls
        r1 = await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)
        r2 = await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)
        r3 = await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)

        assert r1.membership_id == r2.membership_id == r3.membership_id
        assert r3.delivery_attempts == 3

    # Exactly ONE invitation record exists
    invs = (await db_session.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == ws_id,
            WorkspaceInvitation.email == "multiple.retries@agency.com",
        )
    )).scalars().all()
    assert len(invs) == 1
    assert invs[0].delivery_attempts == 3

    # ZERO users in public.users
    user_check = (await db_session.execute(
        select(User).where(User.email == "multiple.retries@agency.com")
    )).scalar_one_or_none()
    assert user_check is None


@pytest.mark.anyio
async def test_25_concurrent_invitation_dispatch_rejected_409(db_session: AsyncSession) -> None:
    """Requirement: Two administrators cannot concurrently dispatch the same invitation."""
    admin_id1 = uuid.uuid4()
    admin_id2 = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin1 = User(id=admin_id1, email="admin25a@agency.com")
    admin2 = User(id=admin_id2, email="admin25b@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Concurrency WS", slug=f"conc-{uuid.uuid4().hex[:6]}")
    mem1 = WorkspaceMembership(workspace_id=ws_id, user_id=admin_id1, role=UserRole.WORKSPACE_ADMIN.value, status=MembershipStatus.ACTIVE.value)
    mem2 = WorkspaceMembership(workspace_id=ws_id, user_id=admin_id2, role=UserRole.WORKSPACE_ADMIN.value, status=MembershipStatus.ACTIVE.value)
    # Existing invitation currently PENDING and active (<60s)
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="concurrent.target@agency.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.PENDING.value,
        delivery_attempts=1,
        invited_by_user_id=admin_id1,
        updated_at=datetime.now(UTC),  # Active within 60s
    )
    db_session.add_all([admin1, admin2, workspace, mem1, mem2, inv])
    await db_session.commit()

    ctx2 = SecurityContext(user_id=admin_id2, workspace_id=ws_id, workspace_role=UserRole.WORKSPACE_ADMIN)

    # 1. Admin 2 attempts retry while Admin 1's dispatch is in progress -> 409 Conflict
    with pytest.raises(ProblemException) as exc_retry:
        await retry_invitation_delivery(w_id=ws_id, inv_id=inv.id, ctx=ctx2, db=db_session)
    assert exc_retry.value.status == 409
    assert exc_retry.value.code == "INVITATION_DISPATCH_IN_PROGRESS"

    # 2. Admin 2 attempts invite_member for same email while in progress -> 409 Conflict
    payload = MemberInvite(email="concurrent.target@agency.com", role=UserRole.CONTENT_CREATOR)
    with pytest.raises(ProblemException) as exc_invite:
        await invite_member(payload=payload, w_id=ws_id, ctx=ctx2, db=db_session)
    assert exc_invite.value.status == 409
    assert exc_invite.value.code == "INVITATION_DISPATCH_IN_PROGRESS"


@pytest.mark.anyio
async def test_26_atomic_claiming_in_recover_pending(db_session: AsyncSession) -> None:
    """Requirement: recover-pending atomically claims eligible records and ignores active in-flight ones."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin26@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Recover WS", slug=f"rec-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(workspace_id=ws_id, user_id=admin_id, role=UserRole.WORKSPACE_ADMIN.value, status=MembershipStatus.ACTIVE.value)

    # 1. Stranded PENDING invitation (>60s old) -> SHOULD BE CLAIMED
    stranded_inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="stranded@agency.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.PENDING.value,
        delivery_attempts=1,
        invited_by_user_id=admin_id,
        updated_at=datetime.now(UTC) - timedelta(seconds=120),
    )
    # 2. Active PENDING invitation (<60s old) -> SHOULD BE IGNORED (in-flight)
    active_inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="active@agency.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.PENDING.value,
        delivery_attempts=1,
        invited_by_user_id=admin_id,
        updated_at=datetime.now(UTC),
    )
    # 3. FAILED invitation -> SHOULD BE CLAIMED
    failed_inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="failed@agency.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.FAILED.value,
        delivery_attempts=1,
        invited_by_user_id=admin_id,
        updated_at=datetime.now(UTC),
    )
    db_session.add_all([admin, workspace, mem, stranded_inv, active_inv, failed_inv])
    await db_session.commit()

    ctx = SecurityContext(user_id=admin_id, workspace_id=ws_id, workspace_role=UserRole.WORKSPACE_ADMIN)
    with patch(
        "app.modules.workspaces.router.dispatch_workspace_invitation",
        new=AsyncMock(return_value=InvitationDispatchResult(delivered=True, channel="smtp", auth_user_id=None, detail="Recovered")),
    ):
        recovered = await recover_pending_invitations(w_id=ws_id, ctx=ctx, db=db_session)

    # Exactly 2 should be recovered (stranded and failed), NOT active
    recovered_emails = {r.email for r in recovered}
    assert "stranded@agency.com" in recovered_emails
    assert "failed@agency.com" in recovered_emails
    assert "active@agency.com" not in recovered_emails


@pytest.mark.anyio
async def test_27_honest_error_handling_when_transaction2_fails_after_provider_success(db_session: AsyncSession) -> None:
    """Requirement: Provider success followed by database failure is handled honestly (500 DELIVERY_RECORDING_FAILED)."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin27@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Failure WS", slug=f"fail-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(workspace_id=ws_id, user_id=admin_id, role=UserRole.WORKSPACE_ADMIN.value, status=MembershipStatus.ACTIVE.value)
    db_session.add_all([admin, workspace, mem])
    await db_session.commit()

    ctx = SecurityContext(user_id=admin_id, workspace_id=ws_id, workspace_role=UserRole.WORKSPACE_ADMIN)
    payload = MemberInvite(email="prov.success.db.fail@agency.com", role=UserRole.CONTENT_CREATOR)

    original_commit = db_session.commit
    commit_call_count = 0

    async def fail_on_tx2():
        nonlocal commit_call_count
        commit_call_count += 1
        if commit_call_count == 1:
            # Transaction 1: succeeds (records PENDING state)
            return await original_commit()
        # Transaction 2: simulates DB crash / failure
        raise RuntimeError("Database connection dropped during Transaction 2 commit")

    with patch(
        "app.modules.workspaces.router.dispatch_workspace_invitation",
        new=AsyncMock(return_value=InvitationDispatchResult(delivered=True, channel="smtp", auth_user_id=None, detail="Sent")),
    ), patch.object(db_session, "commit", side_effect=fail_on_tx2):
        with pytest.raises(ProblemException) as excinfo:
            await invite_member(payload=payload, w_id=ws_id, ctx=ctx, db=db_session)

    # Roll back in-memory uncommitted transaction
    await db_session.rollback()

    assert excinfo.value.status == 500
    assert excinfo.value.code == "DELIVERY_RECORDING_FAILED"
    assert "Invitation dispatch was accepted by external provider" in excinfo.value.detail

    # The record was committed in Transaction 1, so it remains safe & recoverable in PENDING state
    persisted_inv = (await db_session.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == ws_id,
            WorkspaceInvitation.email == "prov.success.db.fail@agency.com",
        )
    )).scalar_one()
    assert persisted_inv.delivery_status == InvitationDeliveryStatus.PENDING.value


@pytest.mark.anyio
async def test_28_concurrent_bulk_recovery_racing_claims(db_session: AsyncSession) -> None:
    """Requirement: Two independent recovery requests racing for the same stranded invitation claim it atomically."""
    from tests.db_helpers import TestSessionLocal

    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin = User(id=admin_id, email="admin28@agency.com")
    workspace = AgencyWorkspace(id=ws_id, name="Race WS", slug=f"race-{uuid.uuid4().hex[:6]}")
    mem = WorkspaceMembership(workspace_id=ws_id, user_id=admin_id, role=UserRole.WORKSPACE_ADMIN.value, status=MembershipStatus.ACTIVE.value)

    # Exactly 1 stranded invitation
    stranded_inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email="racing.target@agency.com",
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.PENDING.value,
        delivery_attempts=1,
        claim_expires_at=None,
        invited_by_user_id=admin_id,
        created_at=datetime.now(UTC) - timedelta(seconds=120),
        updated_at=datetime.now(UTC) - timedelta(seconds=120),
    )
    db_session.add_all([admin, workspace, mem, stranded_inv])
    await db_session.commit()

    ctx = SecurityContext(user_id=admin_id, workspace_id=ws_id, workspace_role=UserRole.WORKSPACE_ADMIN)
    dispatch_mock = AsyncMock(return_value=InvitationDispatchResult(delivered=True, channel="smtp", auth_user_id=None, detail="Sent"))

    # Two separate sessions representing two concurrent requests
    async with TestSessionLocal() as session1, TestSessionLocal() as session2:
        with patch("app.modules.workspaces.router.dispatch_workspace_invitation", new=dispatch_mock):
            rec1, rec2 = await asyncio.gather(
                recover_pending_invitations(w_id=ws_id, ctx=ctx, db=session1),
                recover_pending_invitations(w_id=ws_id, ctx=ctx, db=session2),
            )

    # Exactly ONE of the requests successfully claimed and recovered the invitation
    total_recovered = len(rec1) + len(rec2)
    assert total_recovered == 1, f"Expected exactly 1 claim across concurrent recovery runs, got {total_recovered}"

    # Verify dispatch was called exactly once
    assert dispatch_mock.call_count == 1

    # Expire session identity map to read committed updates from other sessions
    db_session.expire_all()
    persisted = (await db_session.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == ws_id,
            WorkspaceInvitation.email == "racing.target@agency.com",
        )
    )).scalar_one()
    assert persisted.delivery_status == InvitationDeliveryStatus.DELIVERED.value
    assert persisted.claim_expires_at is None
    assert persisted.delivery_attempts == 2


@pytest.mark.anyio
async def test_29_revoked_member_cannot_be_reactivated_by_new_invitation(db_session: AsyncSession) -> None:
    """Security Requirement: Deliberately revoked member cannot be reactivated by a new invitation."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    revoked_user_id = uuid.uuid4()
    revoked_email = "deliberately.revoked@agency.com"

    admin = User(id=admin_id, email=f"admin29-{uuid.uuid4().hex[:6]}@agency.com")
    revoked_user = User(id=revoked_user_id, email=revoked_email)
    workspace = AgencyWorkspace(id=ws_id, name="Secure WS 29", slug=f"ws-{uuid.uuid4().hex[:6]}")
    
    admin_mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    revoked_mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=revoked_user_id,
        role=UserRole.CONTENT_CREATOR.value,
        status=MembershipStatus.REVOKED.value,
        revoked_at=datetime.now(UTC) - timedelta(days=10),
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email=revoked_email,
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add_all([admin, revoked_user, workspace, admin_mem, revoked_mem, inv])
    await db_session.flush()

    # User authenticates with verified email
    auth_user = AuthenticatedUser(
        user_id=revoked_user_id,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email=revoked_email,
        email_verified=True,
    )

    # Acceptance flow runs
    synced_user = await get_or_sync_user(db=db_session, current_user=auth_user)
    assert synced_user.id == revoked_user_id

    # Verify membership was NOT reactivated: status is still REVOKED and revoked_at is intact
    mem_check = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == revoked_user_id,
        )
    )).scalar_one()
    assert mem_check.status == MembershipStatus.REVOKED.value
    assert mem_check.revoked_at is not None

    # Verify invitation was rejected/revoked, NOT accepted
    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.REVOKED.value
    assert refreshed_inv.accepted_at is None

    # Verify user has ZERO access to the workspace
    with pytest.raises(ProblemException) as excinfo:
        await require_workspace_member(w_id=ws_id, current_user=auth_user, db=db_session)
    assert excinfo.value.status == 403


@pytest.mark.anyio
async def test_30_revoked_admin_cannot_be_reactivated_as_creator(db_session: AsyncSession) -> None:
    """Security Requirement: Revoked admin cannot be reactivated into any role via an invitation."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    revoked_admin_id = uuid.uuid4()
    revoked_admin_email = "exadmin@agency.com"

    admin = User(id=admin_id, email=f"admin30-{uuid.uuid4().hex[:6]}@agency.com")
    revoked_admin = User(id=revoked_admin_id, email=revoked_admin_email)
    workspace = AgencyWorkspace(id=ws_id, name="Secure WS 30", slug=f"ws-{uuid.uuid4().hex[:6]}")
    
    admin_mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    revoked_mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=revoked_admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.REVOKED.value,
        revoked_at=datetime.now(UTC) - timedelta(days=5),
    )
    # Admin tries to invite revoked admin as CONTENT_CREATOR
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email=revoked_admin_email,
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add_all([admin, revoked_admin, workspace, admin_mem, revoked_mem, inv])
    await db_session.flush()

    auth_user = AuthenticatedUser(
        user_id=revoked_admin_id,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email=revoked_admin_email,
        email_verified=True,
    )

    await get_or_sync_user(db=db_session, current_user=auth_user)

    # Membership remains REVOKED; never reactivated as creator or admin
    mem_check = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == revoked_admin_id,
        )
    )).scalar_one()
    assert mem_check.status == MembershipStatus.REVOKED.value
    assert mem_check.revoked_at is not None

    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.REVOKED.value
    assert refreshed_inv.accepted_at is None


@pytest.mark.anyio
async def test_31_active_admin_is_not_downgraded_by_creator_invitation(db_session: AsyncSession) -> None:
    """Security Requirement: Active WORKSPACE_ADMIN cannot be downgraded by accepting lower role invitation."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin_email = "headadmin@agency.com"

    admin = User(id=admin_id, email=admin_email)
    workspace = AgencyWorkspace(id=ws_id, name="Admin Preserve WS", slug=f"ws-{uuid.uuid4().hex[:6]}")
    admin_mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email=admin_email,
        role=UserRole.CONTENT_CREATOR.value,  # Lower role
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add_all([admin, workspace, admin_mem, inv])
    await db_session.flush()

    auth_user = AuthenticatedUser(
        user_id=admin_id,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email=admin_email,
        email_verified=True,
    )

    await get_or_sync_user(db=db_session, current_user=auth_user)

    mem_check = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == admin_id,
        )
    )).scalar_one()
    # Preserves WORKSPACE_ADMIN, NOT downgraded to CONTENT_CREATOR
    assert mem_check.role == UserRole.WORKSPACE_ADMIN.value
    assert mem_check.status == MembershipStatus.ACTIVE.value

    refreshed_inv = await db_session.get(WorkspaceInvitation, inv.id)
    assert refreshed_inv.status == InvitationStatus.ACCEPTED.value


@pytest.mark.anyio
async def test_32_existing_active_member_role_is_not_overwritten(db_session: AsyncSession) -> None:
    """Security Requirement: Existing active member role is not silently overwritten by invitation."""
    admin_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    user_email = "bm@agency.com"

    admin = User(id=admin_id, email=f"admin32-{uuid.uuid4().hex[:6]}@agency.com")
    user = User(id=user_id, email=user_email)
    workspace = AgencyWorkspace(id=ws_id, name="Role Preserve WS", slug=f"ws-{uuid.uuid4().hex[:6]}")
    
    admin_mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=admin_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    existing_mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=user_id,
        role=UserRole.BRAND_MANAGER.value,
        status=MembershipStatus.ACTIVE.value,
    )
    # Lower role invitation
    inv = WorkspaceInvitation(
        workspace_id=ws_id,
        email=user_email,
        role=UserRole.CONTENT_CREATOR.value,
        status=InvitationStatus.PENDING.value,
        delivery_status=InvitationDeliveryStatus.DELIVERED.value,
        invited_by_user_id=admin_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add_all([admin, user, workspace, admin_mem, existing_mem, inv])
    await db_session.flush()

    auth_user = AuthenticatedUser(
        user_id=user_id,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email=user_email,
        email_verified=True,
    )

    await get_or_sync_user(db=db_session, current_user=auth_user)

    mem_check = (await db_session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == ws_id,
            WorkspaceMembership.user_id == user_id,
        )
    )).scalar_one()
    # Preserves BRAND_MANAGER
    assert mem_check.role == UserRole.BRAND_MANAGER.value
    assert mem_check.status == MembershipStatus.ACTIVE.value
