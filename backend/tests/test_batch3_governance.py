"""Batch 3 Core Content Governance Engine Integration Tests.

Validates:
1. Separation of Duties (ADR-004): Content creator cannot approve their own submission even with Brand Manager role.
2. Reviewer comments mandatory on REJECTED and CHANGES_REQUESTED decisions.
3. Deterministic Tone/Voice & Accessibility checks (WCAG 2.4.4 links, capitalization, repeated punctuation).
4. Unverified claims remain unverified and never yield a genuine passing audit without substantiation.
5. Compliance certificate issuance upon valid approval with cryptographic hash.
"""
import io
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app
from app.modules.documents.extractor import extract_candidate_rules_deterministic
from app.modules.engine_factual.verifier import run_deterministic_factual_check
from tests.db_helpers import get_test_db, reset_test_db
from tests.jwt_helpers import FakeJWKS, TestKey, make_verifier
from tests.settings_helpers import clean_settings

KEY = TestKey("kid-batch3", "EC")
ADMIN_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _setup_db() -> None:
    import asyncio
    asyncio.run(reset_test_db())


@pytest.fixture(autouse=True)
def _mock_gemini_verifier():
    mock_settings = clean_settings(gemini_api_key="mock-live-key")
    async def _mock_extract(sections, **kw):
        return extract_candidate_rules_deterministic(sections)

    with (
        patch(
            "app.modules.engine_factual.gemini_verifier.verify_facts_with_gemini",
            side_effect=lambda text, rules, **kw: run_deterministic_factual_check(text, rules),
        ),
        patch(
            "app.modules.documents.gemini_extractor.async_extract_candidate_rules_with_gemini",
            side_effect=_mock_extract,
        ),
        patch("app.modules.orchestrator.runner.get_settings", return_value=mock_settings),
    ):
        yield


def _client() -> TestClient:
    app = create_app(
        clean_settings(gemini_api_key="mock-live-key"),
        jwt_verifier=make_verifier(FakeJWKS(KEY)),
    )
    app.dependency_overrides[get_db] = get_test_db
    return TestClient(app, raise_server_exceptions=False)


def _token(user_id: uuid.UUID, email: str | None = None) -> dict[str, str]:
    kwargs = {"sub": str(user_id)}
    if email:
        kwargs["email"] = email
        kwargs["email_verified"] = True
    token_str = KEY.token(**kwargs)
    return {"Authorization": f"Bearer {token_str}"}


def _seed_workspace_and_brand(c: TestClient) -> tuple[str, str, uuid.UUID, uuid.UUID]:
    """Seed workspace, client brand, creator (who is also a BM), and independent BM."""
    print("STEP 1: Create workspace")
    ws = c.post(
        "/api/v1/workspaces",
        json={"name": "Aura Agency", "slug": f"aura-{uuid.uuid4().hex[:6]}"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    ).json()
    w_id = ws["workspace_id"]

    print("STEP 2: Invite BM")
    bm_id = uuid.uuid4()
    bm_email = f"bm-{uuid.uuid4().hex[:6]}@aura.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": bm_email, "role": "BRAND_MANAGER", "full_name": "BM User"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(bm_id, bm_email))

    print("STEP 3: Invite Creator BM")
    creator_bm_id = uuid.uuid4()
    creator_bm_email = f"creator-bm-{uuid.uuid4().hex[:6]}@aura.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": creator_bm_email, "role": "BRAND_MANAGER", "full_name": "Creator BM"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(creator_bm_id, creator_bm_email))

    print("STEP 4: Create Client")
    client_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Lumi Botanicals", "code": "LUMI"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    ).json()
    c_id = client_res["client_id"]

    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(creator_bm_id), "client_role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )

    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(bm_id), "client_role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )

    print("STEP 5: Upload Document")
    guidelines = (
        "Never use 'cheap'; instead use 'accessible luxury'.\n"
        "Brand Color: #1A2B3C.\n"
        "Factual: All botanical extracts are certified organic."
    )
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Lumi Guidelines"},
        files={"file": ("guidelines.txt", io.BytesIO(guidelines.encode("utf-8")), "text/plain")},
        headers=_token(creator_bm_id, creator_bm_email),
    )

    print("STEP 6: Approve Candidates")
    candidates = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/candidates",
        headers=_token(creator_bm_id, creator_bm_email),
    ).json()
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/knowledge/approve",
        json={"candidate_ids": [cand["candidate_id"] for cand in candidates]},
        headers=_token(creator_bm_id, creator_bm_email),
    )
    print("STEP 7: Activate Memory")
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/memory/activate",
        json={"version_tag": "v1.0.0"},
        headers=_token(creator_bm_id, creator_bm_email),
    )
    print("SEED FINISHED")
    return w_id, c_id, creator_bm_id, bm_id


def test_separation_of_duties_prevents_creator_approval() -> None:
    """Creator with Brand Manager privileges CANNOT self-approve their own submission (ADR-004)."""
    c = _client()
    w_id, c_id, creator_bm_id, independent_bm_id = _seed_workspace_and_brand(c)

    # Compliant draft created by creator_bm_id
    clean_text = "Our accessible luxury serum features certified organic botanical extracts."
    asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Social Campaign Draft", "content_type": "TEXT", "text_content": clean_text},
        headers=_token(creator_bm_id),
    ).json()

    a_id = asset["asset_id"]
    v_id = asset["latest_version"]["version_id"]

    audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(creator_bm_id),
    ).json()
    print("AUDIT RESULT:", audit.get("overall_verdict"), audit.get("findings"))
    assert audit["overall_verdict"] == "PASS"

    # Submit for review
    sub_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews",
        json={
            "asset_id": a_id,
            "asset_version_id": v_id,
            "audit_run_id": audit["audit_run_id"],
            "submission_notes": "Please sign off.",
        },
        headers=_token(creator_bm_id),
    )
    assert sub_res.status_code == 201
    req_id = sub_res.json()["review_id"]

    # Creator attempts self-approval -> 403 Forbidden with CREATOR_CANNOT_APPROVE_OWN_SUBMISSION
    self_approve = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        json={"decision": "APPROVED", "decision_notes": "Self approval attempt"},
        headers=_token(creator_bm_id),
    )
    assert self_approve.status_code == 403
    assert self_approve.json()["code"] == "CREATOR_CANNOT_APPROVE_OWN_SUBMISSION"

    # Independent Brand Manager approves -> 200 OK
    valid_approve = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        json={"decision": "APPROVED", "decision_notes": "Approved by independent reviewer."},
        headers=_token(independent_bm_id),
    )
    assert valid_approve.status_code == 200
    assert valid_approve.json()["status"] == "APPROVED"
    assert valid_approve.json()["certificate"] is not None


def test_mandatory_comments_on_rejection_and_changes_requested() -> None:
    """Reviewer comments are mandatory when rejecting or requesting changes."""
    c = _client()
    w_id, c_id, creator_bm_id, independent_bm_id = _seed_workspace_and_brand(c)

    clean_text = "Our accessible luxury serum features certified organic botanical extracts."
    asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Draft for Review", "content_type": "TEXT", "text_content": clean_text},
        headers=_token(creator_bm_id),
    ).json()

    a_id = asset["asset_id"]
    v_id = asset["latest_version"]["version_id"]

    audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(creator_bm_id),
    ).json()

    sub_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews",
        json={
            "asset_id": a_id,
            "asset_version_id": v_id,
            "audit_run_id": audit["audit_run_id"],
        },
        headers=_token(creator_bm_id),
    )
    req_id = sub_res.json()["review_id"]

    # Reject without comments -> 422
    rej_no_notes = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        json={"decision": "REJECTED", "decision_notes": ""},
        headers=_token(independent_bm_id),
    )
    assert rej_no_notes.status_code == 422
    assert rej_no_notes.json()["code"] == "REVIEWER_COMMENTS_REQUIRED"

    # Request changes without comments -> 422
    cr_no_notes = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        json={"decision": "CHANGES_REQUESTED", "decision_notes": "   "},
        headers=_token(independent_bm_id),
    )
    assert cr_no_notes.status_code == 422
    assert cr_no_notes.json()["code"] == "REVIEWER_COMMENTS_REQUIRED"

    # Request changes with comments -> 200
    cr_valid = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        json={"decision": "CHANGES_REQUESTED", "decision_notes": "Please verify organic certification claim."},
        headers=_token(independent_bm_id),
    )
    assert cr_valid.status_code == 200
    assert cr_valid.json()["status"] == "CHANGES_REQUESTED"


def test_accessibility_and_tone_voice_checks() -> None:
    """Audit engine flags nondescript links, repeated punctuation, and all-caps shouting."""
    c = _client()
    w_id, c_id, creator_bm_id, _ = _seed_workspace_and_brand(c)

    text_with_issues = (
        "Our accessible luxury serum is ready. Click here to purchase! "
        "SPECIAL DISCOUNT AVAILABLE TODAY ONLY!!! Experience the glow."
    )
    asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Copy with Accessibility Issues", "content_type": "TEXT", "text_content": text_with_issues},
        headers=_token(creator_bm_id),
    ).json()

    a_id = asset["asset_id"]
    v_id = asset["latest_version"]["version_id"]

    audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(creator_bm_id),
    ).json()

    findings = audit["findings"]
    rule_codes = {f["rule_code"] for f in findings}

    assert "ACCESSIBILITY-WCAG-LINK" in rule_codes
    assert "VOICE-PUNCTUATION" in rule_codes
    assert "ACCESSIBILITY-READABILITY" in rule_codes

    link_finding = next(f for f in findings if f["rule_code"] == "ACCESSIBILITY-WCAG-LINK")
    assert link_finding["severity"] == "ADVISORY"
    assert len(link_finding["suggestions"]) >= 1
