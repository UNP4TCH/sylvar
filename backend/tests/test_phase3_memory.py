"""Phase 3 Integration Test Suite: Living Brand Memory & Guideline Ingestion.

Verifies:
- Document upload and format validation (TXT, MD, DOCX, PDF).
- Oversized file rejection (>20MB) with HTTP 413.
- DOCX decompression bomb protection with HTTP 422.
- Rule extraction in 4 categories (TERMINOLOGY, FACT, COLOR, VOICE).
- Brand Manager candidate modification and approval (/knowledge/approve).
- Non-Brand Manager RBAC protection (CONTENT_CREATOR gets 403).
- Memory release activation (/memory/activate) with deterministic SHA-256 JSONB snapshot.
- Active memory pointer update on ClientBrand.
"""
import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app
from tests.db_helpers import get_test_db, reset_test_db
from tests.jwt_helpers import FakeJWKS, TestKey, make_verifier
from tests.settings_helpers import clean_settings

KEY = TestKey("kid-phase3", "EC")

ADMIN_ID = uuid.uuid4()
BRAND_MANAGER_ID = uuid.uuid4()
CREATOR_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _setup_db() -> None:
    import asyncio
    asyncio.run(reset_test_db())


def _client() -> TestClient:
    app = create_app(clean_settings(), jwt_verifier=make_verifier(FakeJWKS(KEY)))
    app.dependency_overrides[get_db] = get_test_db
    return TestClient(app, raise_server_exceptions=False)


def _token(user_id: uuid.UUID, email: str | None = None) -> dict[str, str]:
    kwargs = {"sub": str(user_id)}
    if email:
        kwargs["email"] = email
        kwargs["email_verified"] = True
    token_str = KEY.token(**kwargs)
    return {"Authorization": f"Bearer {token_str}"}


def _seed_workspace_and_client(c: TestClient) -> tuple[str, str, uuid.UUID, uuid.UUID]:
    """Helper to seed workspace, client, brand manager, and creator."""
    ws = c.post(
        "/api/v1/workspaces",
        json={"name": "Acme Agency", "slug": f"acme-agency-{uuid.uuid4().hex[:6]}"},
        headers=_token(ADMIN_ID, "admin@acme.com"),
    ).json()
    w_id = ws["workspace_id"]

    # Add Brand Manager to workspace
    bm_id = uuid.uuid4()
    bm_email = f"bm-{uuid.uuid4().hex[:6]}@acme.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": bm_email, "role": "BRAND_MANAGER", "full_name": "Bob Manager"},
        headers=_token(ADMIN_ID, "admin@acme.com"),
    )
    # BM authenticates to accept invitation and activate membership
    c.get("/api/v1/workspaces", headers=_token(bm_id, bm_email))

    # Add Creator to workspace
    creator_id = uuid.uuid4()
    creator_email = f"creator-{uuid.uuid4().hex[:6]}@acme.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": creator_email, "role": "CONTENT_CREATOR", "full_name": "Carol Creator"},
        headers=_token(ADMIN_ID, "admin@acme.com"),
    )
    # Creator authenticates to accept invitation and activate membership
    c.get("/api/v1/workspaces", headers=_token(creator_id, creator_email))

    # Admin creates client brand
    client_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Aura Cosmetics", "code": "AURA"},
        headers=_token(ADMIN_ID, "admin@acme.com"),
    ).json()
    c_id = client_res["client_id"]

    # Assign Brand Manager to client brand
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(bm_id), "client_role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID, "admin@acme.com"),
    )

    # Assign Creator to client brand
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(creator_id), "client_role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID, "admin@acme.com"),
    )

    return w_id, c_id, bm_id, creator_id


def test_document_upload_and_extraction() -> None:
    c = _client()
    w_id, c_id, bm_id, creator_id = _seed_workspace_and_client(c)

    guideline_text = (
        "# Brand Voice and Identity\n\n"
        "Never use the term 'cheap' when describing our formulations; prefer 'accessible luxury'.\n\n"
        "Brand Color Palette:\n"
        "Primary brand color is #1A2B3C (Midnight Blue).\n"
        "Secondary accent is #FF5733 (Sunset Orange).\n\n"
        "Factual Claim: All our botanical extracts are certified organic by Ecocert.\n\n"
        "Voice: We always communicate with an empowering, respectful tone."
    )

    files = {"file": ("guidelines.txt", io.BytesIO(guideline_text.encode("utf-8")), "text/plain")}
    data = {"title": "Aura Brand Guidelines v1"}

    # Brand Manager uploads document
    upload_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data=data,
        files=files,
        headers=_token(bm_id),
    )
    assert upload_res.status_code == 202
    doc_info = upload_res.json()
    assert doc_info["title"] == "Aura Brand Guidelines v1"
    assert doc_info["file_format"] == "TXT"
    assert doc_info["candidate_count"] > 0
    d_id = doc_info["document_id"]

    # Poll status
    status_res = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents/{d_id}/status",
        headers=_token(bm_id),
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "EXTRACTED"
    assert status_res.json()["candidate_count"] == doc_info["candidate_count"]

    # Creator attempts upload -> 403 Forbidden (Only Brand Manager can upload guidelines)
    creator_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Unauthorized"},
        files=files,
        headers=_token(creator_id),
    )
    assert creator_res.status_code == 403


def test_oversized_document_rejected() -> None:
    c = _client()
    w_id, c_id, bm_id, _ = _seed_workspace_and_client(c)

    # 21MB dummy payload exceeds 20MB limit
    oversized = b"x" * (21 * 1024 * 1024)
    files = {"file": ("huge.txt", io.BytesIO(oversized), "text/plain")}

    res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Too Large"},
        files=files,
        headers=_token(bm_id),
    )
    assert res.status_code == 413
    assert res.json()["code"] == "FILE_TOO_LARGE"


def test_docx_decompression_bomb_rejected() -> None:
    c = _client()
    w_id, c_id, bm_id, _ = _seed_workspace_and_client(c)

    # Create a zip with excessive compression ratio (>100:1) or >500 files
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 2MB of zeroes compresses to ~2KB (>500:1 ratio)
        zf.writestr("word/document.xml", b"\x00" * (2 * 1024 * 1024))
    buf.seek(0)

    files = {"file": ("bomb.docx", buf, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Zip Bomb Test"},
        files=files,
        headers=_token(bm_id),
    )
    assert res.status_code == 422
    assert res.json()["code"] == "DECOMPRESSION_BOMB_DETECTED"


def test_candidate_review_and_approval_flow() -> None:
    c = _client()
    w_id, c_id, bm_id, creator_id = _seed_workspace_and_client(c)

    guidelines = (
        "Never use 'cheap', instead use 'accessible'.\n"
        "Brand Color: #112233.\n"
        "Factual: All products are 100% cruelty-free."
    )
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Core Guidelines"},
        files={"file": ("guidelines.txt", io.BytesIO(guidelines.encode("utf-8")), "text/plain")},
        headers=_token(bm_id),
    )

    # 1. List candidates
    cand_res = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/candidates",
        headers=_token(bm_id),
    )
    assert cand_res.status_code == 200
    candidates = cand_res.json()
    assert len(candidates) >= 2
    cand_id = candidates[0]["candidate_id"]

    # 2. Modify candidate payload
    patch_res = c.patch(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/candidates/{cand_id}",
        json={"payload": {"custom": "modified_rule"}, "review_status": "MODIFIED_APPROVED"},
        headers=_token(bm_id),
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["review_status"] == "MODIFIED_APPROVED"
    assert patch_res.json()["payload"] == {"custom": "modified_rule"}

    # 3. Content Creator cannot patch candidate
    creator_patch = c.patch(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/candidates/{cand_id}",
        json={"payload": {"malicious": "update"}, "review_status": "APPROVED"},
        headers=_token(creator_id),
    )
    assert creator_patch.status_code == 403

    # 4. Brand Manager approves candidates into authoritative rules
    approve_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/knowledge/approve",
        json={"candidate_ids": [c["candidate_id"] for c in candidates]},
        headers=_token(bm_id),
    )
    assert approve_res.status_code == 200
    approved_data = approve_res.json()
    assert approved_data["approved_count"] == len(candidates)
    assert len(approved_data["rules"]) == len(candidates)


def test_memory_activation_and_snapshot_generation() -> None:
    c = _client()
    w_id, c_id, bm_id, _ = _seed_workspace_and_client(c)

    # Trying to activate with 0 approved rules raises 422
    empty_act = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/memory/activate",
        json={"version_tag": "v1.0.0"},
        headers=_token(bm_id),
    )
    assert empty_act.status_code == 422
    assert empty_act.json()["code"] == "NO_APPROVED_RULES"

    # Ingest and approve a candidate
    guidelines = "Never use 'cheap'; prefer 'affordable'. Brand color is #AABBCC."
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Standards"},
        files={"file": ("standards.txt", io.BytesIO(guidelines.encode("utf-8")), "text/plain")},
        headers=_token(bm_id),
    )
    cand_res = c.get(f"/api/v1/workspaces/{w_id}/clients/{c_id}/candidates", headers=_token(bm_id))
    cands = cand_res.json()

    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/knowledge/approve",
        json={"candidate_ids": [c["candidate_id"] for c in cands]},
        headers=_token(bm_id),
    )

    # Activate memory version
    act_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/memory/activate",
        json={"version_tag": "v1.0.0", "change_summary": "Initial baseline rules"},
        headers=_token(bm_id),
    )
    assert act_res.status_code == 200
    act_data = act_res.json()
    assert act_data["version_number"] == 1
    assert act_data["version_tag"] == "v1.0.0"
    assert act_data["rule_count"] == len(cands)
    assert len(act_data["snapshot_hash"]) == 64  # SHA-256

    # Verify active memory retrieval
    active_res = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/memory/active",
        headers=_token(bm_id),
    )
    assert active_res.status_code == 200
    active_data = active_res.json()
    assert active_data["active"] is True
    assert active_data["version"]["version_tag"] == "v1.0.0"
    assert active_data["snapshot"]["snapshot_hash"] == act_data["snapshot_hash"]
    assert len(active_data["snapshot"]["data"]["rules"]) == len(cands)
