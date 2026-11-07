"""Targeted integration test suite for SYLVAR Batch 2A: Core Data and Authorization.

Verifies:
1. ClientBrand creation atomically creates ClientMembership as BRAND_MANAGER for the creator.
2. Member invitation workflow checks duplicates, dispatches invitations, and records membership.
3. Audit remediation creates new remediated AssetVersion without mutating immutable CorrectionSuggestion.
"""
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemException
from app.core.security.jwt_verifier import AuthenticatedUser
from app.models.audit import (
    AuditCheck,
    AuditFinding,
    AuditRun,
    AuditRunStatus,
    AuditVerdict,
    CheckStatus,
    CorrectionSuggestion,
    EngineType,
    FindingSeverity,
)
from app.models.client import ClientBrand, ClientMembership, ClientMembershipStatus, ClientRole
from app.models.content import AssetVersion, ContentAsset, ContentType
from app.models.memory import BrandMemorySnapshot, BrandMemoryVersion, MemoryVersionStatus
from app.models.user import User
from app.models.workspace import AgencyWorkspace, MembershipStatus, UserRole, WorkspaceMembership
from app.modules.audits.router import RemediationRequest, remediate_content
from app.modules.auth.pipeline import SecurityContext
from app.modules.clients.router import create_client
from app.modules.clients.schemas import ClientCreate
from app.modules.workspaces.router import invite_member
from app.modules.workspaces.schemas import MemberInvite


@pytest.mark.anyio
async def test_batch2a_client_brand_creation_atomicity(db_session: AsyncSession) -> None:
    """Requirement 1: ClientBrand creation atomically creates ClientMembership as BRAND_MANAGER."""
    user_id = uuid.uuid4()
    user = User(id=user_id, email="admin@agency.com", full_name="Admin User")
    ws_id = uuid.uuid4()
    workspace = AgencyWorkspace(id=ws_id, name="Creative Agency", slug=f"agency-{uuid.uuid4().hex[:6]}")
    admin_mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=user_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([user, workspace, admin_mem])
    await db_session.flush()

    ctx = SecurityContext(
        user_id=user_id,
        workspace_id=ws_id,
        workspace_role=UserRole.WORKSPACE_ADMIN,
    )

    client_payload = ClientCreate(
        name="Acme Corp",
        code=f"ACME_{uuid.uuid4().hex[:4].upper()}",
        description="Global Brands",
    )

    res = await create_client(payload=client_payload, w_id=ws_id, ctx=ctx, db=db_session)
    assert res.name == "Acme Corp"
    assert res.client_id is not None

    # Verify ClientMembership was atomically created in the same transaction
    stmt = select(ClientMembership).where(
        ClientMembership.client_id == res.client_id,
        ClientMembership.user_id == user_id,
    )
    membership = (await db_session.execute(stmt)).scalar_one_or_none()
    assert membership is not None
    assert membership.client_role == ClientRole.BRAND_MANAGER.value
    assert membership.status == ClientMembershipStatus.ACTIVE.value
    assert membership.workspace_id == ws_id


@pytest.mark.anyio
async def test_batch2a_invitation_workflow_and_duplicate_check(db_session: AsyncSession) -> None:
    """Requirements 3 & 4: Secure member invitation and duplicate detection."""
    user_id = uuid.uuid4()
    user = User(id=user_id, email="admin@agency.com", full_name="Admin User")
    ws_id = uuid.uuid4()
    workspace = AgencyWorkspace(id=ws_id, name="Test Studio", slug=f"studio-{uuid.uuid4().hex[:6]}")
    admin_mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=user_id,
        role=UserRole.WORKSPACE_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([user, workspace, admin_mem])
    await db_session.flush()

    ctx = SecurityContext(
        user_id=user_id,
        workspace_id=ws_id,
        workspace_role=UserRole.WORKSPACE_ADMIN,
    )

    invite_payload = MemberInvite(
        email="newmember@agency.com",
        role=UserRole.CONTENT_CREATOR,
        full_name="New Creator",
    )

    # 1. Invite new member
    res = await invite_member(payload=invite_payload, w_id=ws_id, ctx=ctx, db=db_session)
    assert res.email == "newmember@agency.com"
    assert res.role == UserRole.CONTENT_CREATOR.value
    assert res.status == MembershipStatus.INVITED.value

    # 2. Duplicate active member fails with 409 Conflict
    existing_user = User(id=uuid.uuid4(), email="active@agency.com", full_name="Active Member")
    active_mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=existing_user.id,
        role=UserRole.CONTENT_CREATOR.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add_all([existing_user, active_mem])
    await db_session.flush()

    conflict_payload = MemberInvite(
        email="active@agency.com",
        role=UserRole.CONTENT_CREATOR,
    )
    with pytest.raises(ProblemException) as excinfo:
        await invite_member(payload=conflict_payload, w_id=ws_id, ctx=ctx, db=db_session)
    assert excinfo.value.status == 409
    assert excinfo.value.code == "MEMBER_ALREADY_EXISTS"


@pytest.mark.anyio
async def test_batch2a_remediation_immutable_audit_evidence(db_session: AsyncSession) -> None:
    """Requirement 5: Remediation leaves CorrectionSuggestion immutable while tracking link on AssetVersion."""
    user_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    client_id = uuid.uuid4()

    user = User(id=user_id, email="creator@agency.com", full_name="Content Creator")
    workspace = AgencyWorkspace(id=ws_id, name="Audit Studio", slug=f"audit-{uuid.uuid4().hex[:6]}")
    client = ClientBrand(id=client_id, workspace_id=ws_id, name="Brand X", code="BRANDX")
    asset = ContentAsset(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        title="Test Marketing Copy",
        content_type=ContentType.TEXT.value,
        created_by_user_id=user_id,
    )
    version = AssetVersion(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        asset_id=asset.id,
        version_number=1,
        text_content="This product is completely guaranteed to heal all conditions.",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        created_by_user_id=user_id,
    )
    mem_ver = BrandMemoryVersion(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        version_number=1,
        version_tag="v1.0.0",
        status=MemoryVersionStatus.ACTIVE.value,
    )
    snapshot = BrandMemorySnapshot(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        memory_version_id=mem_ver.id,
        snapshot_hash="a" * 64,
        snapshot_data={"rules": []},
    )
    audit_run = AuditRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        asset_id=asset.id,
        asset_version_id=version.id,
        snapshot_id=snapshot.id,
        triggered_by_user_id=user_id,
        status=AuditRunStatus.COMPLETED.value,
        overall_verdict=AuditVerdict.BLOCKED.value,
    )
    audit_check = AuditCheck(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        audit_run_id=audit_run.id,
        engine_type=EngineType.FACTUAL.value,
        status=CheckStatus.FAIL.value,
    )
    finding = AuditFinding(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        audit_run_id=audit_run.id,
        check_id=audit_check.id,
        severity=FindingSeverity.CRITICAL.value,
        message="Unsupported medical health claim.",
        snippet="completely guaranteed to heal all conditions",
        location_start=16,
        location_end=60,
        evidence={},
    )
    suggestion = CorrectionSuggestion(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        finding_id=finding.id,
        audit_run_id=audit_run.id,
        original_text="completely guaranteed to heal all conditions",
        suggested_text="formulated to support daily wellness",
        rationale="Align with compliant wellness framing.",
        applied_at=None,
    )

    db_session.add_all(
        [
            user,
            workspace,
            client,
            asset,
            version,
            mem_ver,
            snapshot,
            audit_run,
            audit_check,
            finding,
            suggestion,
        ]
    )
    await db_session.flush()

    ctx = SecurityContext(
        user_id=user_id,
        workspace_id=ws_id,
        workspace_role=UserRole.CONTENT_CREATOR,
        client_id=client_id,
        client_role=ClientRole.CONTENT_CREATOR,
    )

    remed_payload = RemediationRequest(suggestion_ids=[suggestion.id])

    res = await remediate_content(
        payload=remed_payload,
        w_id=ws_id,
        c_id=client_id,
        run_id=audit_run.id,
        ctx=ctx,
        db=db_session,
    )

    # 1. New version was created with corrected text
    assert res.version_id != version.id
    assert "formulated to support daily wellness" in res.text_content
    assert res.created_from_correction_id == suggestion.id

    # 2. CorrectionSuggestion remains unmodified and immutable
    refreshed_sugg = await db_session.get(CorrectionSuggestion, suggestion.id)
    assert refreshed_sugg is not None
    assert refreshed_sugg.applied_at is None  # Immutability preserved!
