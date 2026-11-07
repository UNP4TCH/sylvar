"""Automated Regression Suite for SYLVAR Batch 1 Remediation.

Validates:
- A2: Review finding association: Review approval strictly validates that acknowledged finding IDs
      belong to the specific audit run tied to the review request, rejecting IDs from other runs.
- A4: Safe offline demo mode:
      - Fail-closed behavior when ALLOW_OFFLINE_DEMO=false and no Gemini API key is present.
      - Safe warning behavior (never PASS) when ALLOW_OFFLINE_DEMO=true.
      - Deterministic critical violations remain BLOCKED even in demo mode.
      - Certificates issued from offline audits are labeled DEMO ONLY with explicit disclosures.
      - Production environment (app_env="production") strictly rejects ALLOW_OFFLINE_DEMO=true.
- B1: Review decision concurrency & certificate uniqueness:
      - Terminal state enforcement (duplicate decisions return 409 REVIEW_ALREADY_DECIDED).
      - Unique certificate enforcement (duplicate certificates return 409 CERTIFICATE_ALREADY_ISSUED).
- B2/B3: Database RLS policies in migrations:
      - RLS enabled and forced on public.users.
      - Cross-workspace client brand isolation policy enforced.
"""
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ProblemException
from app.models.audit import (
    AuditCheck,
    AuditFinding,
    AuditRun,
    AuditRunStatus,
    AuditVerdict,
)
from app.models.client import ClientBrand, ClientRole
from app.models.content import AssetVersion, ContentAsset
from app.models.memory import BrandMemorySnapshot
from app.models.review import ApprovalRequest, ApprovalStatus, ComplianceCertificate
from app.models.workspace import AgencyWorkspace, UserRole
from app.modules.auth.pipeline import SecurityContext
from app.modules.orchestrator.runner import execute_audit
from app.modules.reviews.router import (
    ReviewDecisionRequest,
    ReviewSubmitRequest,
    decide_review,
    submit_for_review,
)
from tests.settings_helpers import clean_settings

# ==============================================================================
# A2: Review Finding Association Regression Tests
# ==============================================================================

@pytest.mark.anyio
async def test_review_approval_acknowledges_only_own_audit_findings(db_session: AsyncSession):
    """A2: Ensures that acknowledging a finding from a different audit run is rejected with 422."""
    ws_id = uuid.uuid4()
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()
    bm_user_id = uuid.uuid4()

    workspace = AgencyWorkspace(id=ws_id, name="Agency A2", slug=f"a2-{uuid.uuid4().hex[:6]}")
    brand = ClientBrand(id=client_id, workspace_id=ws_id, name="Brand A2", code="BA2")
    asset1 = ContentAsset(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, title="Doc 1", created_by_user_id=user_id)
    version1 = AssetVersion(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, asset_id=asset1.id, version_number=1, sha256_hash="h1", created_by_user_id=user_id)

    asset2 = ContentAsset(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, title="Doc 2", created_by_user_id=user_id)
    version2 = AssetVersion(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, asset_id=asset2.id, version_number=1, sha256_hash="h2", created_by_user_id=user_id)

    snapshot = BrandMemorySnapshot(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, memory_version_id=uuid.uuid4(), snapshot_hash="snapA2", snapshot_data={})

    # Audit 1 for Version 1
    audit1 = AuditRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        asset_id=asset1.id,
        asset_version_id=version1.id,
        snapshot_id=snapshot.id,
        status=AuditRunStatus.COMPLETED.value,
        overall_verdict=AuditVerdict.WARNINGS.value,
        triggered_by_user_id=user_id,
    )

    # Audit 2 for Version 2 (latest audit)
    audit2 = AuditRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        asset_id=asset2.id,
        asset_version_id=version2.id,
        snapshot_id=snapshot.id,
        status=AuditRunStatus.COMPLETED.value,
        overall_verdict=AuditVerdict.WARNINGS.value,
        triggered_by_user_id=user_id,
    )

    db_session.add_all([workspace, brand, asset1, version1, asset2, version2, snapshot, audit1, audit2])
    await db_session.flush()

    # Checks and findings for both audits
    check1 = AuditCheck(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, audit_run_id=audit1.id, engine_type="VISUAL", status="WARNING")
    finding1 = AuditFinding(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        audit_run_id=audit1.id,
        check_id=check1.id,
        severity="ADVISORY",
        message="Finding on Audit 1",
    )

    check2 = AuditCheck(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, audit_run_id=audit2.id, engine_type="VISUAL", status="WARNING")
    finding2 = AuditFinding(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        audit_run_id=audit2.id,
        check_id=check2.id,
        severity="ADVISORY",
        message="Finding on Audit 2",
    )
    db_session.add_all([check1, finding1, check2, finding2])
    await db_session.flush()

    # Submit review for Audit 1
    cr_ctx = SecurityContext(user_id=user_id, workspace_id=ws_id, workspace_role=UserRole.CONTENT_CREATOR, client_id=client_id, client_role=ClientRole.CONTENT_CREATOR)
    submit_req = ReviewSubmitRequest(
        asset_id=asset1.id,
        asset_version_id=version1.id,
        audit_run_id=audit1.id,
    )
    review_resp = await submit_for_review(submit_req, ws_id, client_id, cr_ctx, db_session)

    bm_ctx = SecurityContext(user_id=bm_user_id, workspace_id=ws_id, workspace_role=UserRole.BRAND_MANAGER, client_id=client_id, client_role=ClientRole.BRAND_MANAGER)

    # Attempt to approve Review 1 by acknowledging finding2 (from Audit 2) -> Must fail with 422
    with pytest.raises(ProblemException) as exc_info:
        await decide_review(
            ReviewDecisionRequest(decision=ApprovalStatus.APPROVED, advisory_acknowledgments=[str(finding2.id)]),
            ws_id,
            client_id,
            review_resp.review_id,
            bm_ctx,
            db_session,
        )
    assert exc_info.value.status == 422
    assert exc_info.value.code == "INVALID_ACKNOWLEDGMENT_IDS"

    # Approving Review 1 with finding1 (from Audit 1) -> Succeeds
    approved = await decide_review(
        ReviewDecisionRequest(decision=ApprovalStatus.APPROVED, advisory_acknowledgments=[str(finding1.id)]),
        ws_id,
        client_id,
        review_resp.review_id,
        bm_ctx,
        db_session,
    )
    assert approved.status == ApprovalStatus.APPROVED.value
    assert approved.advisory_acknowledgments == [str(finding1.id)]


# ==============================================================================
# A4: Safe Offline Demo Mode Regression Tests
# ==============================================================================

def test_production_strictly_rejects_allow_offline_demo():
    """A4: Settings must reject allow_offline_demo=True in production."""
    with pytest.raises(ValidationError, match="ALLOW_OFFLINE_DEMO cannot be enabled in production"):
        Settings(_env_file=None, app_env="production", allow_offline_demo=True)


@pytest.mark.anyio
async def test_offline_demo_disabled_fails_closed(db_session: AsyncSession):
    """A4: When allow_offline_demo=False and no Gemini key is set, audit fails closed."""
    ws_id = uuid.uuid4()
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()

    workspace = AgencyWorkspace(id=ws_id, name="Agency Demo Fail", slug=f"fail-{uuid.uuid4().hex[:6]}")
    brand = ClientBrand(id=client_id, workspace_id=ws_id, name="Brand Fail", code="BF")
    asset = ContentAsset(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, title="Doc", created_by_user_id=user_id)
    version = AssetVersion(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, asset_id=asset.id, version_number=1, sha256_hash="hfail", created_by_user_id=user_id)
    snapshot = BrandMemorySnapshot(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        memory_version_id=uuid.uuid4(),
        snapshot_hash="snapfail",
        snapshot_data={"terminology_rules": [], "factual_rules": [{"category": "FACT", "rule_code": "F-01", "content": {"statement": "Organic"}}], "visual_rules": []},
    )
    db_session.add_all([workspace, brand, asset, version, snapshot])
    await db_session.flush()

    settings = clean_settings(allow_offline_demo=False, gemini_api_key=None)
    with patch("app.modules.orchestrator.runner.get_settings", return_value=settings):
        audit = await execute_audit(
            workspace_id=ws_id,
            client_id=client_id,
            asset_id=asset.id,
            asset_version_id=version.id,
            snapshot_id=snapshot.id,
            rules=snapshot.snapshot_data.get("factual_rules", []),
            text_content="Clean text with no rules violated.",
            image_bytes=None,
            user_id=user_id,
            db=db_session,
        )

    assert audit.status == AuditRunStatus.FAILED.value
    assert audit.overall_verdict == AuditVerdict.BLOCKED.value


@pytest.mark.anyio
async def test_offline_demo_enabled_returns_warnings_and_demo_labels(db_session: AsyncSession):
    """A4: When allow_offline_demo=True and no Gemini key is set, audit completes with WARNINGS (never PASS)."""
    ws_id = uuid.uuid4()
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()
    bm_user_id = uuid.uuid4()

    workspace = AgencyWorkspace(id=ws_id, name="Agency Demo Pass", slug=f"dpass-{uuid.uuid4().hex[:6]}")
    brand = ClientBrand(id=client_id, workspace_id=ws_id, name="Brand Demo", code="BD")
    asset = ContentAsset(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, title="Doc", created_by_user_id=user_id)
    version = AssetVersion(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, asset_id=asset.id, version_number=1, sha256_hash="hdpass", created_by_user_id=user_id)
    snapshot = BrandMemorySnapshot(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        memory_version_id=uuid.uuid4(),
        snapshot_hash="snapdpass",
        snapshot_data={"terminology_rules": [], "factual_rules": [{"category": "FACT", "rule_code": "F-01", "content": {"statement": "Organic"}}], "visual_rules": []},
    )
    db_session.add_all([workspace, brand, asset, version, snapshot])
    await db_session.flush()

    settings = clean_settings(allow_offline_demo=True, gemini_api_key=None)
    with patch("app.modules.orchestrator.runner.get_settings", return_value=settings):
        audit = await execute_audit(
            workspace_id=ws_id,
            client_id=client_id,
            asset_id=asset.id,
            asset_version_id=version.id,
            snapshot_id=snapshot.id,
            rules=snapshot.snapshot_data.get("factual_rules", []),
            text_content="Clean text with no rules violated.",
            image_bytes=None,
            user_id=user_id,
            db=db_session,
        )

    # In demo mode, status is COMPLETED, but overall verdict is WARNINGS (never PASS)
    assert audit.status == AuditRunStatus.COMPLETED.value
    assert audit.overall_verdict == AuditVerdict.WARNINGS.value
    assert "DEMO MODE" in str(audit.error_details)

    # Now verify that human review can be submitted and results in a DEMO ONLY certificate
    cr_ctx = SecurityContext(user_id=user_id, workspace_id=ws_id, workspace_role=UserRole.CONTENT_CREATOR, client_id=client_id, client_role=ClientRole.CONTENT_CREATOR)
    submit_req = ReviewSubmitRequest(
        asset_id=asset.id,
        asset_version_id=version.id,
        audit_run_id=audit.id,
    )
    review_resp = await submit_for_review(submit_req, ws_id, client_id, cr_ctx, db_session)
    assert review_resp.status == ApprovalStatus.PENDING.value

    bm_ctx = SecurityContext(user_id=bm_user_id, workspace_id=ws_id, workspace_role=UserRole.BRAND_MANAGER, client_id=client_id, client_role=ClientRole.BRAND_MANAGER)
    approved = await decide_review(
        ReviewDecisionRequest(decision=ApprovalStatus.APPROVED, advisory_acknowledgments=[]),
        ws_id,
        client_id,
        review_resp.review_id,
        bm_ctx,
        db_session,
    )
    assert approved.status == ApprovalStatus.APPROVED.value
    assert approved.certificate is not None

    cert = approved.certificate
    payload = cert.certificate_payload
    assert payload.get("certificate_type") == "DEMO_COMPLIANCE_CERTIFICATE"
    assert payload.get("is_demo_only") is True
    assert "disclosures" in payload
    assert any("DEMO ONLY" in d for d in payload["disclosures"])


@pytest.mark.anyio
async def test_offline_demo_critical_deterministic_violations_remain_blocked(db_session: AsyncSession):
    """A4: Deterministic critical violations remain BLOCKED even when demo mode is active."""
    ws_id = uuid.uuid4()
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()

    workspace = AgencyWorkspace(id=ws_id, name="Agency Demo Blocked", slug=f"dblock-{uuid.uuid4().hex[:6]}")
    brand = ClientBrand(id=client_id, workspace_id=ws_id, name="Brand Blocked", code="BB")
    asset = ContentAsset(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, title="Doc", created_by_user_id=user_id)
    version = AssetVersion(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, asset_id=asset.id, version_number=1, sha256_hash="hdblock", created_by_user_id=user_id)
    snapshot = BrandMemorySnapshot(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        memory_version_id=uuid.uuid4(),
        snapshot_hash="snapdblock",
        snapshot_data={
            "terminology_rules": [],
            "factual_rules": [{"category": "FACT", "rule_code": "F-01", "content": {"statement": "Our ingredients are 100% organic."}}],
            "visual_rules": [],
        },
    )
    db_session.add_all([workspace, brand, asset, version, snapshot])
    await db_session.flush()

    settings = clean_settings(allow_offline_demo=True, gemini_api_key=None)
    with patch("app.modules.orchestrator.runner.get_settings", return_value=settings):
        # 'synthetic' explicitly contradicts 'organic' in deterministic contradiction pairs
        audit = await execute_audit(
            workspace_id=ws_id,
            client_id=client_id,
            asset_id=asset.id,
            asset_version_id=version.id,
            snapshot_id=snapshot.id,
            rules=snapshot.snapshot_data.get("factual_rules", []),
            text_content="Our serum uses synthetic compounds.",
            image_bytes=None,
            user_id=user_id,
            db=db_session,
        )

    # In demo mode, status is COMPLETED, but overall verdict remains BLOCKED
    assert audit.status == AuditRunStatus.COMPLETED.value
    assert audit.overall_verdict == AuditVerdict.BLOCKED.value

    # Submission for review MUST be blocked
    cr_ctx = SecurityContext(user_id=user_id, workspace_id=ws_id, workspace_role=UserRole.CONTENT_CREATOR, client_id=client_id, client_role=ClientRole.CONTENT_CREATOR)
    submit_req = ReviewSubmitRequest(
        asset_id=asset.id,
        asset_version_id=version.id,
        audit_run_id=audit.id,
    )
    with pytest.raises(ProblemException) as exc_info:
        await submit_for_review(submit_req, ws_id, client_id, cr_ctx, db_session)
    assert exc_info.value.status == 422
    assert exc_info.value.code == "AUDIT_BLOCKED"


# ==============================================================================
# B1: Review Concurrency & Certificate Uniqueness
# ==============================================================================

@pytest.mark.anyio
async def test_duplicate_review_decision_returns_409(db_session: AsyncSession):
    """B1: A second decision attempt on an already decided review returns 409 REVIEW_ALREADY_DECIDED."""
    ws_id = uuid.uuid4()
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()
    bm_user_id = uuid.uuid4()

    workspace = AgencyWorkspace(id=ws_id, name="Agency B1", slug=f"b1-{uuid.uuid4().hex[:6]}")
    brand = ClientBrand(id=client_id, workspace_id=ws_id, name="Brand B1", code="BB1")
    asset = ContentAsset(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, title="Doc", created_by_user_id=user_id)
    version = AssetVersion(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, asset_id=asset.id, version_number=1, sha256_hash="hb1", created_by_user_id=user_id)
    snapshot = BrandMemorySnapshot(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, memory_version_id=uuid.uuid4(), snapshot_hash="snapb1", snapshot_data={})

    audit = AuditRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        asset_id=asset.id,
        asset_version_id=version.id,
        snapshot_id=snapshot.id,
        status=AuditRunStatus.COMPLETED.value,
        overall_verdict=AuditVerdict.PASS.value,
        triggered_by_user_id=user_id,
    )
    db_session.add_all([workspace, brand, asset, version, snapshot, audit])
    await db_session.flush()

    cr_ctx = SecurityContext(user_id=user_id, workspace_id=ws_id, workspace_role=UserRole.CONTENT_CREATOR, client_id=client_id, client_role=ClientRole.CONTENT_CREATOR)
    submit_req = ReviewSubmitRequest(asset_id=asset.id, asset_version_id=version.id, audit_run_id=audit.id)
    review_resp = await submit_for_review(submit_req, ws_id, client_id, cr_ctx, db_session)

    bm_ctx = SecurityContext(user_id=bm_user_id, workspace_id=ws_id, workspace_role=UserRole.BRAND_MANAGER, client_id=client_id, client_role=ClientRole.BRAND_MANAGER)

    # First decision: APPROVED
    dec1 = await decide_review(
        ReviewDecisionRequest(decision=ApprovalStatus.APPROVED, advisory_acknowledgments=[]),
        ws_id,
        client_id,
        review_resp.review_id,
        bm_ctx,
        db_session,
    )
    assert dec1.status == ApprovalStatus.APPROVED.value

    # Second decision attempt: raises 409 REVIEW_ALREADY_DECIDED
    with pytest.raises(ProblemException) as exc_info:
        await decide_review(
            ReviewDecisionRequest(decision=ApprovalStatus.REJECTED, advisory_acknowledgments=[]),
            ws_id,
            client_id,
            review_resp.review_id,
            bm_ctx,
            db_session,
        )
    assert exc_info.value.status == 409
    assert exc_info.value.code == "REVIEW_ALREADY_DECIDED"


@pytest.mark.anyio
async def test_duplicate_certificate_creation_prevented(db_session: AsyncSession):
    """B1: Attempting to create duplicate certificate for same approval request returns 409."""
    ws_id = uuid.uuid4()
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()
    bm_user_id = uuid.uuid4()

    workspace = AgencyWorkspace(id=ws_id, name="Agency B1 Cert", slug=f"b1cert-{uuid.uuid4().hex[:6]}")
    brand = ClientBrand(id=client_id, workspace_id=ws_id, name="Brand B1 Cert", code="BB1C")
    asset = ContentAsset(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, title="Doc", created_by_user_id=user_id)
    version = AssetVersion(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, asset_id=asset.id, version_number=1, sha256_hash="hb1cert", created_by_user_id=user_id)
    snapshot = BrandMemorySnapshot(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, memory_version_id=uuid.uuid4(), snapshot_hash="snapb1cert", snapshot_data={})

    audit = AuditRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        asset_id=asset.id,
        asset_version_id=version.id,
        snapshot_id=snapshot.id,
        status=AuditRunStatus.COMPLETED.value,
        overall_verdict=AuditVerdict.PASS.value,
        triggered_by_user_id=user_id,
    )
    approval_req = ApprovalRequest(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        asset_id=asset.id,
        asset_version_id=version.id,
        audit_run_id=audit.id,
        submitted_by_user_id=user_id,
        status=ApprovalStatus.PENDING.value,
    )
    # Pre-existing certificate for this approval_request_id
    existing_cert = ComplianceCertificate(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        approval_request_id=approval_req.id,
        asset_version_id=version.id,
        snapshot_hash="snapb1cert",
        certificate_hash="abc" * 21 + "a",
        certificate_payload={},
    )
    db_session.add_all([workspace, brand, asset, version, snapshot, audit, approval_req, existing_cert])
    await db_session.flush()

    bm_ctx = SecurityContext(user_id=bm_user_id, workspace_id=ws_id, workspace_role=UserRole.BRAND_MANAGER, client_id=client_id, client_role=ClientRole.BRAND_MANAGER)

    with pytest.raises(ProblemException) as exc_info:
        await decide_review(
            ReviewDecisionRequest(decision=ApprovalStatus.APPROVED, advisory_acknowledgments=[]),
            ws_id,
            client_id,
            approval_req.id,
            bm_ctx,
            db_session,
        )
    assert exc_info.value.status == 409
    assert exc_info.value.code == "CERTIFICATE_ALREADY_ISSUED"


# ==============================================================================
# B2 & B3: SQL Migration RLS Verification
# ==============================================================================

def test_migration_001_rls_on_users_and_client_brands():
    """B2 & B3: Verify SQL migration contains required RLS policies."""
    sql_path = Path("..") / "supabase" / "migrations" / "001_initial_schema.sql"
    if not sql_path.exists():
        sql_path = Path("supabase") / "migrations" / "001_initial_schema.sql"
    sql = sql_path.read_text(encoding="utf-8")

    # B2: RLS on public.users
    assert "ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;" in sql
    assert "ALTER TABLE public.users FORCE ROW LEVEL SECURITY;" in sql
    assert "CREATE POLICY tenant_isolation_users ON public.users" in sql

    # B3: Cross-workspace brand isolation
    assert "public.current_app_workspace_id() IS NULL" in sql
    assert "workspace_id = public.current_app_workspace_id()" in sql


def test_migration_004_certificate_unique_constraint():
    """B1: Verify SQL migration contains unique constraint for certificates."""
    sql_path = Path("..") / "supabase" / "migrations" / "004_human_review.sql"
    if not sql_path.exists():
        sql_path = Path("supabase") / "migrations" / "004_human_review.sql"
    sql = sql_path.read_text(encoding="utf-8")

    assert "uq_compliance_cert_approval_request" in sql
    assert "UNIQUE (approval_request_id)" in sql
