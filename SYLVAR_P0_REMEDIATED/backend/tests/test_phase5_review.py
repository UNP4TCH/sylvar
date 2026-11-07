"""Phase 5 Integration Test Suite: Human Review & Compliance Certificate Export.

Verifies:
- Content submission to Brand Manager review queue (TASK-026).
- BLOCKED audit runs cannot be submitted for approval (HTTP 422).
- Non-Brand Manager RBAC protection (CONTENT_CREATOR cannot approve, gets HTTP 403).
- Brand Manager approval with advisory acknowledgments.
- Generation of immutable verifiable ComplianceCertificate with SHA-256 hash.
- Export of compliance certificate manifest.
"""
import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app
from tests.db_helpers import get_test_db, reset_test_db
from tests.jwt_helpers import FakeJWKS, TestKey, make_verifier
from tests.settings_helpers import clean_settings

KEY = TestKey("kid-phase5", "EC")

ADMIN_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _setup_db() -> None:
    import asyncio
    asyncio.run(reset_test_db())


@pytest.fixture(autouse=True)
def _mock_gemini_verifier():
    from unittest.mock import patch

    from app.modules.engine_factual.verifier import run_deterministic_factual_check
    mock_settings = clean_settings(gemini_api_key="mock-live-key")
    with (
        patch(
            "app.modules.engine_factual.gemini_verifier.verify_facts_with_gemini",
            side_effect=lambda text, rules, **kw: run_deterministic_factual_check(text, rules),
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


def _seed_workspace_and_active_brand(c: TestClient) -> tuple[str, str, uuid.UUID, uuid.UUID]:
    """Seed workspace, client brand, members, ingest guidelines, and activate brand memory."""
    # 1. Create Workspace
    ws = c.post(
        "/api/v1/workspaces",
        json={"name": "Horizon Agency", "slug": f"horizon-{uuid.uuid4().hex[:6]}"},
        headers=_token(ADMIN_ID, "admin@horizon.com"),
    ).json()
    w_id = ws["workspace_id"]

    # 2. Invite Brand Manager and Content Creator
    bm_id = uuid.uuid4()
    bm_email = f"bm-{uuid.uuid4().hex[:6]}@horizon.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": bm_email, "role": "BRAND_MANAGER", "full_name": "BM User"},
        headers=_token(ADMIN_ID, "admin@horizon.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(bm_id, bm_email))

    cr_id = uuid.uuid4()
    cr_email = f"creator-{uuid.uuid4().hex[:6]}@horizon.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": cr_email, "role": "CONTENT_CREATOR", "full_name": "Creator User"},
        headers=_token(ADMIN_ID, "admin@horizon.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(cr_id, cr_email))

    # 3. Create Client Brand
    client_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Lumina Skincare", "code": "LUMINA"},
        headers=_token(ADMIN_ID, "admin@horizon.com"),
    ).json()
    c_id = client_res["client_id"]

    # 4. Assign Members to Client Brand
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(bm_id), "client_role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID, "admin@horizon.com"),
    )
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(cr_id), "client_role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID, "admin@horizon.com"),
    )

    # 5. Ingest Guidelines
    guidelines = (
        "Never use 'cheap'; instead use 'accessible luxury'.\n"
        "Brand Color: #1A2B3C.\n"
        "Factual: All botanical extracts are certified organic."
    )
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Lumina Guidelines"},
        files={"file": ("guidelines.txt", io.BytesIO(guidelines.encode("utf-8")), "text/plain")},
        headers=_token(bm_id, bm_email),
    )

    # 6. Approve Candidates & Activate Memory
    candidates = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/candidates",
        headers=_token(bm_id, bm_email),
    ).json()

    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/knowledge/approve",
        json={"candidate_ids": [cand["candidate_id"] for cand in candidates]},
        headers=_token(bm_id, bm_email),
    )

    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/memory/activate",
        json={"version_tag": "v1.0.0"},
        headers=_token(bm_id, bm_email),
    )

    return w_id, c_id, bm_id, cr_id


def test_review_submission_blocks_unremediated_content() -> None:
    c = _client()
    w_id, c_id, _, cr_id = _seed_workspace_and_active_brand(c)

    # Contradicts brand facts: "synthetic" contradicts "certified organic"
    blocked_text = "Our cheap serum is formulated with a synthetic base."
    asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Blocked Asset", "content_type": "TEXT", "text_content": blocked_text},
        headers=_token(cr_id),
    ).json()

    a_id = asset["asset_id"]
    v_id = asset["latest_version"]["version_id"]

    audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(cr_id),
    ).json()
    assert audit["overall_verdict"] == "BLOCKED"

    # Attempting to submit blocked content raises 422
    submit_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews",
        json={
            "asset_id": a_id,
            "asset_version_id": v_id,
            "audit_run_id": audit["audit_run_id"],
            "submission_notes": "Please approve anyway.",
        },
        headers=_token(cr_id),
    )
    assert submit_res.status_code == 422
    assert submit_res.json()["code"] == "AUDIT_BLOCKED"


def test_review_approval_and_compliance_certificate() -> None:
    c = _client()
    w_id, c_id, bm_id, cr_id = _seed_workspace_and_active_brand(c)

    # Compliant content
    clean_text = "Our accessible luxury serum features certified organic botanical extracts."
    asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Approved Asset", "content_type": "TEXT", "text_content": clean_text},
        headers=_token(cr_id),
    ).json()

    a_id = asset["asset_id"]
    v_id = asset["latest_version"]["version_id"]

    audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(cr_id),
    ).json()
    assert audit["overall_verdict"] == "PASS"

    # Submit for review
    submit_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews",
        json={
            "asset_id": a_id,
            "asset_version_id": v_id,
            "audit_run_id": audit["audit_run_id"],
            "submission_notes": "Ready for publication.",
        },
        headers=_token(cr_id),
    )
    assert submit_res.status_code == 201
    review = submit_res.json()
    assert review["status"] == "PENDING"
    req_id = review["review_id"]

    # Creator attempts to approve -> 403 Forbidden
    creator_dec = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        json={"decision": "APPROVED", "decision_notes": "Self-approval"},
        headers=_token(cr_id),
    )
    assert creator_dec.status_code == 403

    # Brand Manager approves
    bm_dec = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        json={
            "decision": "APPROVED",
            "decision_notes": "Approved for marketing deployment.",
            "advisory_acknowledgments": [],
        },
        headers=_token(bm_id),
    )
    assert bm_dec.status_code == 200
    approved_review = bm_dec.json()
    assert approved_review["status"] == "APPROVED"
    assert approved_review["certificate"] is not None

    cert = approved_review["certificate"]
    assert len(cert["certificate_hash"]) == 64  # SHA-256
    assert cert["certificate_payload"]["asset_title"] == "Approved Asset"
    assert cert["certificate_payload"]["audit_verdict"] == "PASS"

    # Fetch certificate independently
    cert_fetch = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/certificate",
        headers=_token(cr_id),
    )
    assert cert_fetch.status_code == 200
    assert cert_fetch.json()["certificate_hash"] == cert["certificate_hash"]


def test_review_rejection_and_changes_requested() -> None:
    c = _client()
    w_id, c_id, bm_id, cr_id = _seed_workspace_and_active_brand(c)

    clean_text = "Our accessible luxury serum features certified organic botanical extracts."
    asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Review Asset", "content_type": "TEXT", "text_content": clean_text},
        headers=_token(cr_id),
    ).json()

    a_id = asset["asset_id"]
    v_id = asset["latest_version"]["version_id"]

    audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(cr_id),
    ).json()

    submit_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews",
        json={
            "asset_id": a_id,
            "asset_version_id": v_id,
            "audit_run_id": audit["audit_run_id"],
            "submission_notes": "Needs review.",
        },
        headers=_token(cr_id),
    )
    req_id = submit_res.json()["review_id"]

    # Brand Manager requests changes
    cr_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        json={"decision": "CHANGES_REQUESTED", "decision_notes": "Please tone down luxury wording."},
        headers=_token(bm_id),
    )
    assert cr_res.status_code == 200
    assert cr_res.json()["status"] == "CHANGES_REQUESTED"

    # Concurrency / state integrity: attempting a second decision on already decided review returns 409
    dup_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        json={"decision": "REJECTED", "decision_notes": "Campaign cancelled."},
        headers=_token(bm_id),
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["code"] == "REVIEW_ALREADY_DECIDED"

    # Brand Manager rejects a separate review request
    asset2 = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Review Asset 2", "content_type": "TEXT", "text_content": clean_text},
        headers=_token(cr_id),
    ).json()
    audit2 = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{asset2['asset_id']}/versions/{asset2['latest_version']['version_id']}/audit",
        headers=_token(cr_id),
    ).json()
    submit2 = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews",
        json={
            "asset_id": asset2["asset_id"],
            "asset_version_id": asset2["latest_version"]["version_id"],
            "audit_run_id": audit2["audit_run_id"],
            "submission_notes": "Needs review 2.",
        },
        headers=_token(cr_id),
    ).json()
    req2_id = submit2["review_id"]

    rej_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req2_id}/decision",
        json={"decision": "REJECTED", "decision_notes": "Campaign cancelled."},
        headers=_token(bm_id),
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"
