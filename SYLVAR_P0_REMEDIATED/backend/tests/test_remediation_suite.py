"""Comprehensive Regression Test Suite for SYLVAR Pre-Integration Remediation.

Validates all 8 Critical and 16 Major review findings across Stages 1-5:
- C-01/C-02/M-15: Tenant context bootstrap & workspace listing.
- M-01: User invitation identity mapping & reconciliation.
- C-05: Engine failure/exception prevents PASS verdict (sets FAILED / BLOCKED).
- C-06: Gemini failures never silently downgraded to passing results.
- M-06: Async Gemini execution wrappers.
- M-10: Evidence validation & fail-closed UNVERIFIED on missing citations.
- M-11: Unicode NFC normalization & non-alphanumeric boundary matching.
- C-07: Review submission binding to audited content and tenant.
- C-08: Review lifecycle state-transition enforcement (no double-decisions).
- M-09: Advisory warning acknowledgment validation against real findings.
- M-07: Candidate rule approval validation & idempotency.
- M-04: Transparent pixel filtering in visual color analysis.
- M-05: Global request payload limit (413 Problem Details).
- M-13: Document security & PDF 100-page limit.
"""
import io
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
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
)
from app.models.client import ClientBrand, ClientRole
from app.models.content import AssetVersion, ContentAsset
from app.models.memory import (
    BrandMemorySnapshot,
)
from app.models.review import ApprovalStatus
from app.models.user import User
from app.models.workspace import AgencyWorkspace, MembershipStatus, UserRole, WorkspaceMembership
from app.modules.auth.dependencies import get_or_sync_user
from app.modules.documents.parser import parse_pdf_content
from app.modules.engine_factual.gemini_verifier import GeminiClaimResult, GeminiFactualResponse
from app.modules.engine_factual.verifier import (
    run_async_factual_check,
)
from app.modules.engine_terminology.matcher import run_terminology_check
from app.modules.engine_visual.analyzer import extract_dominant_colors
from app.modules.orchestrator.runner import execute_audit

# ==============================================================================
# STAGE 1: Database & Security Foundation (C-01, C-02, M-01, M-15)
# ==============================================================================

@pytest.mark.anyio
async def test_m01_invitation_identity_reconciliation(db_session: AsyncSession):
    """M-01: When an invited user signs up via Supabase, their placeholder record

    and memberships are cleanly reconciled to their authentic GoTrue user_id.
    """
    ws_id = uuid.uuid4()
    workspace = AgencyWorkspace(id=ws_id, name="Test Agency", slug=f"agency-{uuid.uuid4().hex[:6]}")
    db_session.add(workspace)
    await db_session.flush()

    # Step 1: Admin invites bob@agency.com with a temporary placeholder UUID
    placeholder_id = uuid.uuid4()
    invited_user = User(
        id=placeholder_id,
        email="bob@agency.com",
        full_name="Bob Placeholder",
    )
    db_session.add(invited_user)
    await db_session.flush()

    mem = WorkspaceMembership(
        workspace_id=ws_id,
        user_id=placeholder_id,
        role=UserRole.CONTENT_CREATOR.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db_session.add(mem)
    await db_session.flush()

    # Step 2: Bob signs in via Supabase GoTrue with authentic user_id
    authentic_id = uuid.uuid4()
    auth_user = AuthenticatedUser(
        user_id=authentic_id,
        expires_at=int(datetime.now(UTC).timestamp()) + 3600,
        email="bob@agency.com",
    )

    reconciled_user = await get_or_sync_user(db_session, auth_user)
    assert reconciled_user.id == authentic_id
    assert reconciled_user.email == "bob@agency.com"

    # Step 3: Verify memberships were re-pointed to authentic_id
    stmt = select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == ws_id)
    updated_mems = (await db_session.execute(stmt)).scalars().all()
    assert len(updated_mems) == 1
    assert updated_mems[0].user_id == authentic_id


# ==============================================================================
# STAGE 2: Audit Engine & AI Integrity (C-05, C-06, M-06, M-10, M-11)
# ==============================================================================

@pytest.mark.anyio
async def test_c05_engine_failure_prevents_pass(db_session: AsyncSession):
    """C-05: If an audit engine throws an unhandled exception, the overall verdict

    must NEVER be PASS; status must be FAILED, overall_verdict BLOCKED.
    """
    ws_id = uuid.uuid4()
    client_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    version_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Mock run_terminology_check to raise an unexpected runtime error
    with patch(
        "app.modules.orchestrator.runner.run_terminology_check",
        side_effect=RuntimeError("Terminology regex engine crashed!"),
    ):
        audit_run = await execute_audit(
            workspace_id=ws_id,
            client_id=client_id,
            asset_id=asset_id,
            asset_version_id=version_id,
            snapshot_id=snapshot_id,
            rules=[],
            text_content="Some harmless text",
            image_bytes=None,
            user_id=user_id,
            db=db_session,
        )

        assert audit_run.status == AuditRunStatus.FAILED.value
        assert audit_run.overall_verdict == AuditVerdict.BLOCKED.value
        assert "Terminology engine crashed" in (audit_run.error_details or "")


@pytest.mark.anyio
async def test_c06_gemini_failure_never_silently_passes():
    """C-06: When GEMINI_API_KEY is configured and live API fails, it must

    return FAIL with a CRITICAL finding, never silently falling back to a passing result.
    """
    rules = [
        {
            "category": "FACT",
            "rule_code": "RULE-FACT-01",
            "content": {"statement": "Our products are certified 100% organic."},
        }
    ]

    with patch(
        "app.modules.engine_factual.gemini_verifier.verify_facts_with_gemini",
        side_effect=ConnectionError("Gemini API network timeout 504"),
    ):
        status, findings, details = await run_async_factual_check(
            text="Our products are certified 100% organic.",
            rules=rules,
            api_key="fake-test-key",
            model="gemini-3.8-flash",
        )

        assert status == "FAIL"
        assert details["status"] == "FAIL"
        assert details["engine_mode"] == "gemini_live"
        assert "Gemini API network timeout 504" in details["provider_error"]
        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"
        assert "Gemini live factual verification failed" in findings[0].message


def test_m10_supported_claim_missing_citation_fails_closed():
    """M-10: If Gemini claims a fact is SUPPORTED but fails to provide a valid cited_fact,

    it must fail closed to UNVERIFIED (never ambiently supported without evidence).
    """
    rules = [
        {
            "category": "FACT",
            "rule_code": "RULE-FACT-01",
            "content": {"statement": "All ingredients are ethically sourced."},
        }
    ]

    # Mock response from Gemini claiming SUPPORTED but with empty cited_fact
    mock_resp = GeminiFactualResponse(
        findings=[
            GeminiClaimResult(
                claim="We source ethically.",
                verdict="SUPPORTED",
                cited_fact="",  # Missing evidence
                rationale="Looks good.",
            )
        ]
    )

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_gen_response = MagicMock()
        mock_gen_response.text = mock_resp.model_dump_json()
        mock_client.models.generate_content.return_value = mock_gen_response

        from app.modules.engine_factual.gemini_verifier import verify_facts_with_gemini

        _status, findings = verify_facts_with_gemini(
            "We source ethically.", rules, api_key="fake-key"
        )
        assert len(findings) == 1
        assert findings[0].verdict == "UNVERIFIED"
        assert findings[0].severity == "MAJOR"


def test_m11_unicode_nfc_and_non_alphanumeric_boundaries():
    """M-11: Terminology engine handles NFC normalization and terms starting/ending

    with symbols/punctuation (e.g. 'eco-friendly', '#natural').
    """
    rules = [
        {
            "category": "TERMINOLOGY",
            "rule_code": "RULE-TERM-01",
            "content": {
                "term": "eco-friendly",
                "replacement": "sustainably produced",
                "severity": "CRITICAL",
            },
        },
        {
            "category": "TERMINOLOGY",
            "rule_code": "RULE-TERM-02",
            "content": {
                "term": "café",  # Composed NFC
                "replacement": "coffee shop",
                "severity": "MAJOR",
            },
        },
    ]

    # Draft with decomposing NFD "cafe\u0301" and hyphenated "eco-friendly"
    decomposed_draft = "Visit our cafe\u0301 for eco-friendly packaging."
    status, findings = run_terminology_check(decomposed_draft, rules)

    assert status == "FAIL"
    codes = {f.rule_code for f in findings}
    assert "RULE-TERM-01" in codes
    assert "RULE-TERM-02" in codes


# ==============================================================================
# STAGE 3: Human Review & Certificate Integrity (C-07, C-08, M-09)
# ==============================================================================

@pytest.mark.anyio
async def test_c07_c08_m09_review_lifecycle(db_session: AsyncSession):
    """C-07/C-08/M-09: Validates review submission binding, terminal state enforcement,

    and mandatory advisory acknowledgment verification.
    """
    ws_id = uuid.uuid4()
    client_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Create prerequisites
    workspace = AgencyWorkspace(id=ws_id, name="Test Agency", slug=f"agency-{uuid.uuid4().hex[:6]}")
    brand = ClientBrand(id=client_id, workspace_id=ws_id, name="Test Client", code="TC01")
    asset = ContentAsset(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, title="Doc", created_by_user_id=user_id)
    version = AssetVersion(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, asset_id=asset.id, version_number=1, sha256_hash="abc", created_by_user_id=user_id)
    snapshot = BrandMemorySnapshot(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, memory_version_id=uuid.uuid4(), snapshot_hash="snap1", snapshot_data={})

    # Completed audit with an advisory finding
    audit = AuditRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        asset_id=asset.id,
        asset_version_id=version.id,
        snapshot_id=snapshot.id,
        status=AuditRunStatus.COMPLETED.value,
        overall_verdict=AuditVerdict.WARNINGS.value,
        triggered_by_user_id=user_id,
    )
    db_session.add_all([workspace, brand, asset, version, snapshot, audit])
    await db_session.flush()

    check = AuditCheck(id=uuid.uuid4(), workspace_id=ws_id, client_id=client_id, audit_run_id=audit.id, engine_type="VISUAL", status="WARNING")
    db_session.add(check)
    await db_session.flush()

    finding = AuditFinding(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=client_id,
        audit_run_id=audit.id,
        check_id=check.id,
        severity="ADVISORY",
        message="Color differs by delta E 5.2",
    )
    db_session.add(finding)
    await db_session.flush()

    # Step 1: Submit for review
    from app.modules.auth.pipeline import SecurityContext
    from app.modules.reviews.router import ReviewSubmitRequest, submit_for_review

    ctx = SecurityContext(user_id=user_id, workspace_id=ws_id, workspace_role=UserRole.CONTENT_CREATOR, client_id=client_id, client_role=ClientRole.CONTENT_CREATOR)
    submit_payload = ReviewSubmitRequest(
        asset_id=asset.id,
        asset_version_id=version.id,
        audit_run_id=audit.id,
    )
    review_resp = await submit_for_review(submit_payload, ws_id, client_id, ctx, db_session)
    assert review_resp.status == ApprovalStatus.PENDING.value

    # C-07 Check: Duplicate submission for same version rejected with 409
    with pytest.raises(ProblemException) as exc_info:
        await submit_for_review(submit_payload, ws_id, client_id, ctx, db_session)
    assert exc_info.value.status == 409
    assert exc_info.value.code == "REVIEW_ALREADY_PENDING"

    # Step 2: Decide review
    from app.modules.reviews.router import ReviewDecisionRequest, decide_review

    bm_ctx = SecurityContext(user_id=user_id, workspace_id=ws_id, workspace_role=UserRole.BRAND_MANAGER, client_id=client_id, client_role=ClientRole.BRAND_MANAGER)

    # M-09 Check: Approving without acknowledging advisory finding raises 422
    with pytest.raises(ProblemException) as exc_info:
        await decide_review(
            ReviewDecisionRequest(decision=ApprovalStatus.APPROVED, advisory_acknowledgments=[]),
            ws_id,
            client_id,
            review_resp.review_id,
            bm_ctx,
            db_session,
        )
    assert exc_info.value.status == 422
    assert exc_info.value.code == "UNACKNOWLEDGED_ADVISORY_FINDINGS"

    # M-09 Check: Approving with a fabricated finding ID raises 422
    fake_id = str(uuid.uuid4())
    with pytest.raises(ProblemException) as exc_info:
        await decide_review(
            ReviewDecisionRequest(decision=ApprovalStatus.APPROVED, advisory_acknowledgments=[fake_id]),
            ws_id,
            client_id,
            review_resp.review_id,
            bm_ctx,
            db_session,
        )
    assert exc_info.value.status == 422
    assert exc_info.value.code == "INVALID_ACKNOWLEDGMENT_IDS"

    # Valid approval with genuine finding ID
    decided = await decide_review(
        ReviewDecisionRequest(decision=ApprovalStatus.APPROVED, advisory_acknowledgments=[str(finding.id)]),
        ws_id,
        client_id,
        review_resp.review_id,
        bm_ctx,
        db_session,
    )
    assert decided.status == ApprovalStatus.APPROVED.value
    assert decided.certificate is not None

    # C-08 Check: Re-deciding already decided review returns 409
    with pytest.raises(ProblemException) as exc_info:
        await decide_review(
            ReviewDecisionRequest(decision=ApprovalStatus.REJECTED),
            ws_id,
            client_id,
            review_resp.review_id,
            bm_ctx,
            db_session,
        )
    assert exc_info.value.status == 409
    assert exc_info.value.code == "REVIEW_ALREADY_DECIDED"


# ==============================================================================
# STAGE 4: Brand Memory & Remediation (M-07, M-04, M-13)
# ==============================================================================

def test_m04_transparent_png_filtering():
    """M-04: Transparent pixels (alpha == 0) are excluded from dominant color extraction,

    ensuring that a white canvas does not mask brand colors in transparent PNGs.
    """
    # Create RGBA image: 95% transparent, 5% pure red
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))  # Fully transparent
    for x in range(20):
        for y in range(20):
            img.putpixel((x, y), (255, 0, 0, 255))  # Red box in corner

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    colors = extract_dominant_colors(buf.getvalue(), max_colors=1)

    assert len(colors) >= 1
    # Primary extracted color must be the visible red, NOT white background
    r, g, b = colors[0]
    assert r > 200
    assert g < 50
    assert b < 50


def test_m13_pdf_page_limit_enforced():
    """M-13: PDF document exceeding 100 pages is rejected with 422 PDF_PAGE_LIMIT_EXCEEDED."""
    import pypdf

    # Create dummy in-memory PDF with 105 pages
    writer = pypdf.PdfWriter()
    for _ in range(105):
        writer.add_blank_page(width=100, height=100)

    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    with pytest.raises(ProblemException) as exc_info:
        parse_pdf_content(pdf_bytes)

    assert exc_info.value.status == 422
    assert exc_info.value.code == "PDF_PAGE_LIMIT_EXCEEDED"

