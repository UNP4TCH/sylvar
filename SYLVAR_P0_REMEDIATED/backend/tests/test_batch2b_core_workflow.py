"""Batch 2B End-to-End Core Functional Workflow Integration Tests.

Validates all 6 Batch 2B objectives:
TASK 1: Atomic Client Brand creation and BRAND_MANAGER assignment, scoping enforcement.
TASK 2: Draft Version State resetting and fresh asset/version auditing without stale references.
TASK 3: Dynamic memory versioning, conflict avoidance, and pending candidate filtering.
TASK 4: Guideline upload, validation, and rule extraction.
TASK 5: Pre-publication audit execution, snapshot requirement enforcement, and safe verdicts.
TASK 6: Review handoff, Separation of Duties (creator cannot approve), and Compliance Certificate issuance.
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

KEY = TestKey("kid-batch2b", "EC")
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


def test_batch2b_task1_client_creation_and_scoping():
    """TASK 1: Client brand creation atomically assigns BRAND_MANAGER role; scoping restricts access."""
    c = _client()

    # 1. Create Workspace
    ws_res = c.post(
        "/api/v1/workspaces",
        json={"name": "Verve Agency", "slug": f"verve-{uuid.uuid4().hex[:6]}"},
        headers=_token(ADMIN_ID, "admin@verve.com"),
    )
    assert ws_res.status_code == 201
    w_id = ws_res.json()["workspace_id"]

    # 2. Workspace Admin creates Client Brand
    code = f"VB_{uuid.uuid4().hex[:4].upper()}"
    client_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Verve Botanicals", "code": code, "description": "Clean Skincare"},
        headers=_token(ADMIN_ID, "admin@verve.com"),
    )
    assert client_res.status_code == 201
    c_id = client_res.json()["client_id"]

    # 3. Verify creator can list the client immediately
    listed_clients = c.get(
        f"/api/v1/workspaces/{w_id}/clients",
        headers=_token(ADMIN_ID, "admin@verve.com"),
    ).json()
    assert any(cl["client_id"] == c_id for cl in listed_clients)

    # 4. Another workspace member who is NOT assigned cannot see this client
    other_user = uuid.uuid4()
    other_email = f"other-{uuid.uuid4().hex[:6]}@verve.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": other_email, "role": "CONTENT_CREATOR", "full_name": "Other User"},
        headers=_token(ADMIN_ID, "admin@verve.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(other_user, other_email))

    other_clients = c.get(
        f"/api/v1/workspaces/{w_id}/clients",
        headers=_token(other_user, other_email),
    ).json()
    assert not any(cl["client_id"] == c_id for cl in other_clients)


def test_batch2b_task3_and_task4_guideline_upload_and_dynamic_memory_versioning():
    """TASKS 3 & 4: Guideline upload, rule extraction, and dynamic multi-release memory activation."""
    c = _client()

    # 1. Setup workspace & brand
    ws = c.post(
        "/api/v1/workspaces",
        json={"name": "Aura Agency", "slug": f"aura-{uuid.uuid4().hex[:6]}"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    ).json()
    w_id = ws["workspace_id"]

    client = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Aura Brand", "code": "AURA"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    ).json()
    c_id = client["client_id"]

    # 2. Upload first guideline document (TASK 4)
    g1 = (
        "Never use 'cheap'; instead use 'accessible luxury'.\n"
        "Brand Color: #1A2B3C.\n"
        "Factual: All botanical extracts are certified organic."
    )
    upload_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Aura Guidelines v1"},
        files={"file": ("guidelines_v1.txt", io.BytesIO(g1.encode("utf-8")), "text/plain")},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )
    assert upload_res.status_code == 202
    assert upload_res.json()["candidate_count"] > 0

    # 3. Retrieve candidates and verify pending candidates
    candidates = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/candidates",
        headers=_token(ADMIN_ID, "admin@aura.com"),
    ).json()
    assert len(candidates) >= 3

    # Filter pending candidates
    pending_ids = [cand["candidate_id"] for cand in candidates if cand["review_status"] == "PENDING_REVIEW"]
    assert len(pending_ids) == len(candidates)

    # 4. Approve candidates
    appr_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/knowledge/approve",
        json={"candidate_ids": pending_ids},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["approved_count"] == len(pending_ids)

    # 5. Activate Release 1 (TASK 3: Dynamic Version 1)
    act1 = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/memory/activate",
        json={"version_tag": "v1.1.0", "change_summary": "Initial baseline memory"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )
    assert act1.status_code == 200
    act1_data = act1.json()
    assert act1_data["version_tag"] == "v1.1.0"
    assert act1_data["version_number"] == 1
    assert act1_data["snapshot_hash"] is not None

    # Verify candidates list: previously approved candidates are now APPROVED, not PENDING_REVIEW
    candidates_after_act1 = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/candidates",
        headers=_token(ADMIN_ID, "admin@aura.com"),
    ).json()
    assert all(cand["review_status"] == "APPROVED" for cand in candidates_after_act1)

    # 6. Upload second guideline document
    g2 = "Never use 'synthetic'; instead use 'plant-derived'."
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Aura Guidelines Addendum"},
        files={"file": ("guidelines_addendum.txt", io.BytesIO(g2.encode("utf-8")), "text/plain")},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )

    candidates_v2 = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/candidates",
        headers=_token(ADMIN_ID, "admin@aura.com"),
    ).json()
    new_pending = [cand["candidate_id"] for cand in candidates_v2 if cand["review_status"] == "PENDING_REVIEW"]
    assert len(new_pending) >= 1

    # Approve new pending candidate only
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/knowledge/approve",
        json={"candidate_ids": new_pending},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )

    # 7. Activate Release 2 (TASK 3: Dynamic Version 2)
    act2 = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/memory/activate",
        json={"version_tag": "v1.2.0", "change_summary": "Addendum rules"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )
    assert act2.status_code == 200
    act2_data = act2.json()
    assert act2_data["version_tag"] == "v1.2.0"
    assert act2_data["version_number"] == 2

    # 8. Duplicate version_tag conflict avoidance (Task 3)
    # If the user tries activating with the same tag "v1.2.0", backend appends -v3 without failing
    act3 = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/memory/activate",
        json={"version_tag": "v1.2.0", "change_summary": "Re-activation test"},
        headers=_token(ADMIN_ID, "admin@aura.com"),
    )
    assert act3.status_code == 200
    act3_data = act3.json()
    assert act3_data["version_number"] == 3
    assert act3_data["version_tag"] == "v1.2.0-v3"


def test_batch2b_task2_task5_task6_draft_audit_and_review():
    """TASKS 2, 5 & 6: Draft versioning, pre-publication audit, separation of duties, and compliance certificate."""
    c = _client()

    # 1. Setup workspace & client
    ws = c.post(
        "/api/v1/workspaces",
        json={"name": "Solis Agency", "slug": f"solis-{uuid.uuid4().hex[:6]}"},
        headers=_token(ADMIN_ID, "admin@solis.com"),
    ).json()
    w_id = ws["workspace_id"]

    client = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Solis Skincare", "code": "SOLIS"},
        headers=_token(ADMIN_ID, "admin@solis.com"),
    ).json()
    c_id = client["client_id"]

    # 2. Invite Content Creator and assign to client
    cr_id = uuid.uuid4()
    cr_email = f"creator-{uuid.uuid4().hex[:6]}@solis.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": cr_email, "role": "CONTENT_CREATOR", "full_name": "Content Creator"},
        headers=_token(ADMIN_ID, "admin@solis.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(cr_id, cr_email))
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(cr_id), "client_role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID, "admin@solis.com"),
    )

    # 3. TASK 5 Check: Audit before active memory must fail (HTTP 422 NO_ACTIVE_MEMORY)
    asset_draft = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Draft Asset", "content_type": "TEXT", "text_content": "Initial draft"},
        headers=_token(cr_id),
    ).json()
    audit_no_mem = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{asset_draft['asset_id']}/versions/{asset_draft['latest_version']['version_id']}/audit",
        headers=_token(cr_id),
    )
    assert audit_no_mem.status_code == 422
    assert audit_no_mem.json()["code"] == "NO_ACTIVE_MEMORY"

    # 4. Activate Living Brand Memory
    guidelines = (
        "Never use 'cheap'; instead use 'accessible luxury'.\n"
        "Brand Color: #1A2B3C.\n"
        "Factual: All botanical extracts are certified organic."
    )
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Solis Guidelines"},
        files={"file": ("guidelines.txt", io.BytesIO(guidelines.encode("utf-8")), "text/plain")},
        headers=_token(ADMIN_ID, "admin@solis.com"),
    )
    candidates = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/candidates",
        headers=_token(ADMIN_ID, "admin@solis.com"),
    ).json()
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/knowledge/approve",
        json={"candidate_ids": [cand["candidate_id"] for cand in candidates]},
        headers=_token(ADMIN_ID, "admin@solis.com"),
    )
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/memory/activate",
        json={"version_tag": "v1.1.0"},
        headers=_token(ADMIN_ID, "admin@solis.com"),
    )

    # 5. TASK 2: Non-compliant draft audition
    non_compliant_text = "Our cheap serum is formulated with a synthetic base for glowing skin."
    nc_asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Launch Copy Non-Compliant", "content_type": "TEXT", "text_content": non_compliant_text},
        headers=_token(cr_id),
    ).json()
    nc_aid = nc_asset["asset_id"]
    nc_vid = nc_asset["latest_version"]["version_id"]

    nc_audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{nc_aid}/versions/{nc_vid}/audit",
        headers=_token(cr_id),
    ).json()
    assert nc_audit["overall_verdict"] == "BLOCKED"
    assert len(nc_audit["findings"]) > 0

    # 6. TASK 2: Loading compliant draft resets version state and creates new compliant asset
    compliant_text = "Our accessible luxury serum features certified organic botanical extracts."
    comp_asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Launch Copy Compliant", "content_type": "TEXT", "text_content": compliant_text},
        headers=_token(cr_id),
    ).json()
    comp_aid = comp_asset["asset_id"]
    comp_vid = comp_asset["latest_version"]["version_id"]

    # Ensure compliant version has distinct version and asset ID
    assert comp_aid != nc_aid
    assert comp_vid != nc_vid

    comp_audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{comp_aid}/versions/{comp_vid}/audit",
        headers=_token(cr_id),
    ).json()
    assert comp_audit["overall_verdict"] == "PASS"

    # 7. TASK 6: Submit clean version for review
    sub_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews",
        json={
            "asset_id": comp_aid,
            "asset_version_id": comp_vid,
            "audit_run_id": comp_audit["audit_run_id"],
            "submission_notes": "Submitted by Content Creator for Brand Manager review.",
        },
        headers=_token(cr_id),
    )
    assert sub_res.status_code == 201
    review = sub_res.json()
    assert review["status"] == "PENDING"
    assert review["submitted_by_user_id"] == str(cr_id)
    rev_id = review["review_id"]

    # 8. TASK 6: Separation of Duties: Content Creator CANNOT self-approve (HTTP 403)
    creator_attempt = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{rev_id}/decision",
        json={"decision": "APPROVED", "decision_notes": "Attempting creator self-approval"},
        headers=_token(cr_id),
    )
    assert creator_attempt.status_code == 403

    # 9. TASK 6: Brand Manager approves and issues Compliance Certificate
    bm_approval = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{rev_id}/decision",
        json={
            "decision": "APPROVED",
            "decision_notes": "Approved by Brand Manager after reviewing scorecard.",
            "advisory_acknowledgments": [],
        },
        headers=_token(ADMIN_ID),
    )
    assert bm_approval.status_code == 200
    decided = bm_approval.json()
    assert decided["status"] == "APPROVED"
    assert decided["certificate"] is not None
    assert decided["certificate"]["certificate_hash"] is not None
    assert len(decided["certificate"]["certificate_hash"]) == 64

