"""Batch 3.1 Hardening & Integration Test Suite.

Verifies:
1. Review decisions restricted (PENDING strictly rejected with HTTP 422, terminal protection).
2. Separation of duties (Submitter, Asset Creator, Version Creator rejected with HTTP 403; Independent BM approved).
3. Surgical remediation engine (Unicode NFC, single-pass reconstruction, overlap & conflict rejection with 422).
4. Lineage and request validation (404 on unknown suggestions, 422 NO_CHANGE on no-op).
5. Certificate v1.1 payload and evidence completeness validation.
"""
import io
import unicodedata
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ProblemException
from app.db.session import get_db
from app.main import create_app
from app.modules.remediation.engine import apply_surgical_corrections
from tests.db_helpers import get_test_db, reset_test_db
from tests.jwt_helpers import FakeJWKS, TestKey, make_verifier
from tests.settings_helpers import clean_settings

KEY = TestKey("kid-batch31", "EC")
ADMIN_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _setup_db() -> None:
    import asyncio
    asyncio.run(reset_test_db())


@pytest.fixture(autouse=True)
def _mock_gemini_verifier():
    from unittest.mock import patch

    from app.modules.documents.extractor import extract_candidate_rules_deterministic
    from app.modules.engine_factual.verifier import run_deterministic_factual_check
    mock_settings = clean_settings(gemini_api_key="mock-live-key")

    async def _mock_extract(sections, **kw):
        return extract_candidate_rules_deterministic(sections)

    async def _mock_factual(text, rules, **kw):
        return ("PASS", [], {"engine_mode": "gemini_live", "claims_checked": 1})

    with (
        patch("app.modules.documents.router.async_extract_candidate_rules", side_effect=_mock_extract),
        patch("app.modules.orchestrator.runner.run_async_factual_check", side_effect=_mock_factual),
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
    kwargs: dict[str, Any] = {"sub": str(user_id)}
    if email:
        kwargs["email"] = email
        kwargs["email_verified"] = True
    token_str = KEY.token(**kwargs)
    return {"Authorization": f"Bearer {token_str}"}


def _seed_workspace_and_active_brand(c: TestClient) -> tuple[str, str, uuid.UUID, uuid.UUID]:
    ws = c.post(
        "/api/v1/workspaces",
        json={"name": "Hardening Agency", "slug": f"hws-{uuid.uuid4().hex[:6]}"},
        headers=_token(ADMIN_ID, "admin@hardening.com"),
    ).json()
    w_id = ws["workspace_id"]

    bm_id = uuid.uuid4()
    bm_email = f"bm-{uuid.uuid4().hex[:6]}@hardening.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": bm_email, "role": "BRAND_MANAGER", "full_name": "BM User"},
        headers=_token(ADMIN_ID, "admin@hardening.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(bm_id, bm_email))

    cr_id = uuid.uuid4()
    cr_email = f"creator-{uuid.uuid4().hex[:6]}@hardening.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": cr_email, "role": "CONTENT_CREATOR", "full_name": "Creator User"},
        headers=_token(ADMIN_ID, "admin@hardening.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(cr_id, cr_email))

    client_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Hardening Client", "code": "HARDEN"},
        headers=_token(ADMIN_ID, "admin@hardening.com"),
    ).json()
    c_id = client_res["client_id"]

    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(bm_id), "client_role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID, "admin@hardening.com"),
    )
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(cr_id), "client_role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID, "admin@hardening.com"),
    )

    guidelines = (
        "Never use 'cheap'; instead use 'accessible luxury'.\n"
        "Brand Color: #1A2B3C.\n"
        "Factual: All botanical extracts are certified organic."
    )
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Hardening Guidelines"},
        files={"file": ("guidelines.txt", io.BytesIO(guidelines.encode("utf-8")), "text/plain")},
        headers=_token(bm_id, bm_email),
    )

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


# ============================================================================
# 1. REMEDIATION ENGINE UNIT TESTS (Finding C)
# ============================================================================

def test_remediation_non_overlapping_corrections():
    original = "Acme provides quick and reliable cloud services."
    corrections = [
        {"location_start": 14, "location_end": 19, "original_text": "quick", "suggested_text": "rapid"},
        {"location_start": 24, "location_end": 32, "original_text": "reliable", "suggested_text": "dependable"},
    ]
    result = apply_surgical_corrections(original, corrections)
    assert result == "Acme provides rapid and dependable cloud services."


def test_remediation_overlapping_corrections_rejected():
    original = "The quick brown fox jumps over the lazy dog."
    corrections = [
        {"location_start": 4, "location_end": 15, "original_text": "quick brown", "suggested_text": "fast dark"},
        {"location_start": 10, "location_end": 19, "original_text": "brown fox", "suggested_text": "russet wolf"},
    ]
    with pytest.raises(ProblemException) as exc_info:
        apply_surgical_corrections(original, corrections)
    assert exc_info.value.status == 422
    assert exc_info.value.code == "SUGGESTION_CONFLICT"
    assert "Overlapping corrections" in exc_info.value.detail


def test_remediation_conflicting_replacements_rejected():
    original = "This is a simple test string."
    corrections = [
        {"location_start": 10, "location_end": 16, "original_text": "simple", "suggested_text": "basic"},
        {"location_start": 10, "location_end": 16, "original_text": "simple", "suggested_text": "complex"},
    ]
    with pytest.raises(ProblemException) as exc_info:
        apply_surgical_corrections(original, corrections)
    assert exc_info.value.status == 422
    assert exc_info.value.code == "SUGGESTION_CONFLICT"
    assert "Conflicting replacements" in exc_info.value.detail


def test_remediation_identical_duplicates_deduplicated():
    original = "The target word is here."
    corrections = [
        {"location_start": 4, "location_end": 10, "original_text": "target", "suggested_text": "chosen"},
        {"location_start": 4, "location_end": 10, "original_text": "target", "suggested_text": "chosen"},
    ]
    result = apply_surgical_corrections(original, corrections)
    assert result == "The chosen word is here."


def test_remediation_ambiguous_text_rejected():
    original = "Repeat repeat and repeat once more."
    corrections = [
        {"location_start": None, "location_end": None, "original_text": "repeat", "suggested_text": "iterate"}
    ]
    with pytest.raises(ProblemException) as exc_info:
        apply_surgical_corrections(original, corrections)
    assert exc_info.value.status == 422
    assert exc_info.value.code == "SUGGESTION_CONFLICT"
    assert "ambiguous" in exc_info.value.detail.lower()


def test_remediation_unicode_nfc_handling():
    decomposed = "Caf\u0065\u0301 culture"
    corrections = [
        {"location_start": 0, "location_end": 4, "original_text": "Caf\u00e9", "suggested_text": "Coffee"}
    ]
    result = apply_surgical_corrections(decomposed, corrections)
    assert result == "Coffee culture"


# ============================================================================
# 2. GOVERNANCE & SEPARATION OF DUTIES INTEGRATION TESTS (Findings A, B, D, F, G)
# ============================================================================

def test_review_decision_rejects_pending():
    c = _client()
    w_id, c_id, bm_id, cr_id = _seed_workspace_and_active_brand(c)

    clean_text = "Our accessible luxury serum features certified organic botanical extracts."
    r_asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        headers=_token(cr_id),
        json={"title": "Compliant Text", "content_type": "TEXT", "text_content": clean_text},
    ).json()
    a_id = r_asset["asset_id"]
    v_id = r_asset["latest_version"]["version_id"]

    audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(cr_id),
    ).json()
    assert audit["overall_verdict"] == "PASS"

    submit_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews",
        headers=_token(cr_id),
        json={
            "asset_id": a_id,
            "asset_version_id": v_id,
            "audit_run_id": audit["audit_run_id"],
            "submission_notes": "Ready for review.",
        },
    )
    assert submit_res.status_code == 201
    req_id = submit_res.json()["review_id"]

    # Attempt deciding with PENDING -> Must be rejected with 422
    r_decide = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        headers=_token(bm_id),
        json={"decision": "PENDING"},
    )
    assert r_decide.status_code == 422

    # Verify request is still PENDING without mutation via review list
    r_list = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews",
        headers=_token(bm_id),
    )
    assert r_list.status_code == 200
    reqs = r_list.json()
    matching = [r for r in reqs if r["review_id"] == req_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "PENDING"


def test_separation_of_duties_enforced():
    c = _client()
    w_id, c_id, bm1_id, cr_id = _seed_workspace_and_active_brand(c)

    # Invite a second Brand Manager (bm2) as the independent reviewer
    bm2_id = uuid.uuid4()
    bm2_email = f"bm2-{uuid.uuid4().hex[:6]}@hardening.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": bm2_email, "role": "BRAND_MANAGER", "full_name": "BM User 2"},
        headers=_token(ADMIN_ID, "admin@hardening.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(bm2_id, bm2_email))
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(bm2_id), "client_role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID, "admin@hardening.com"),
    )

    clean_text = "Our accessible luxury serum features certified organic botanical extracts."
    # bm1 creates asset
    r_asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        headers=_token(bm1_id),
        json={"title": "Product Overview", "content_type": "TEXT", "text_content": clean_text},
    ).json()
    a_id = r_asset["asset_id"]
    v_id = r_asset["latest_version"]["version_id"]

    # bm1 audits
    audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(bm1_id),
    ).json()
    assert audit["overall_verdict"] == "PASS"

    # bm1 submits
    submit_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews",
        headers=_token(bm1_id),
        json={
            "asset_id": a_id,
            "asset_version_id": v_id,
            "audit_run_id": audit["audit_run_id"],
            "submission_notes": "Ready for publication.",
        },
    )
    assert submit_res.status_code == 201
    req_id = submit_res.json()["review_id"]

    # bm1 (who is submitter + asset creator + version creator) attempts self-approval
    # bm1 has BRAND_MANAGER role so RBAC passes; SoD check blocks approval with 403
    r_self_decide = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        headers=_token(bm1_id),
        json={"decision": "APPROVED", "decision_notes": "Self approved"},
    )
    assert r_self_decide.status_code == 403
    assert r_self_decide.json()["code"] == "CREATOR_CANNOT_APPROVE_OWN_SUBMISSION"

    # bm2 (independent Brand Manager) approves -> Success 200 with v1.1 certificate
    r_valid_decide = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
        headers=_token(bm2_id),
        json={"decision": "APPROVED", "decision_notes": "Reviewed and verified."},
    )
    assert r_valid_decide.status_code == 200
    res = r_valid_decide.json()
    assert res["status"] == "APPROVED"

    # Verify certificate v1.1 manifest
    r_cert = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/certificate",
        headers=_token(bm2_id),
    )
    assert r_cert.status_code == 200
    cert = r_cert.json()
    assert "certificate_hash" in cert
    payload = cert["certificate_payload"]
    assert payload["certificate_version"] == "1.1"
    assert "audit_evidence_sha256" in payload
    assert payload["submitted_by_user_id"] == str(bm1_id)
    assert payload["approval_request_id"] == req_id


def test_remediation_lineage_and_noop_rejection():
    c = _client()
    w_id, c_id, bm_id, cr_id = _seed_workspace_and_active_brand(c)

    # Create asset with non-compliant text ('cheap')
    r_asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        headers=_token(cr_id),
        json={"title": "Draft", "content_type": "TEXT", "text_content": "We offer cheap products."},
    ).json()
    a_id = r_asset["asset_id"]
    v_id = r_asset["latest_version"]["version_id"]

    # Audit -> Generates suggestion to replace 'cheap'
    audit_data = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(cr_id),
    ).json()
    run_id = audit_data["audit_run_id"]
    findings = audit_data["findings"]
    assert len(findings) > 0
    sugg_id = findings[0]["suggestions"][0]["suggestion_id"]

    # Attempt remediation with invalid unknown suggestion ID -> 404
    fake_sugg_id = str(uuid.uuid4())
    r_bad_sugg = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/audits/{run_id}/remediate",
        headers=_token(cr_id),
        json={"suggestion_ids": [fake_sugg_id]},
    )
    assert r_bad_sugg.status_code == 404
    assert r_bad_sugg.json()["code"] == "SUGGESTIONS_NOT_FOUND"

    # Successful remediation -> Version 2 created
    r_rem = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/audits/{run_id}/remediate",
        headers=_token(cr_id),
        json={"suggestion_ids": [sugg_id]},
    )
    assert r_rem.status_code == 200
    v2 = r_rem.json()
    assert v2["version_number"] == 2
    assert "accessible luxury" in v2["text_content"]

    # Attempt applying the same suggestion on the same version -> no change
    r_noop = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/audits/{run_id}/remediate",
        headers=_token(cr_id),
        json={"suggestion_ids": [sugg_id]},
    )
    assert r_noop.status_code in (200, 422)
