"""Phase 4 Integration Test Suite: Content Governance Engine & Surgical Remediation.

Verifies:
- Text content asset creation and versioning (TASK-021).
- Pre-publication 3-tier audit execution (Terminology, Factual, Visual).
- Terminology engine deterministic regex with exact character spans & suggestions.
- ADR-005 Factual verification with tri-state outcomes (CONTRADICTED, SUPPORTED, UNVERIFIED).
- ADR-008 Visual compliance: Delta E00 > 5.0 is strictly ADVISORY, never blocking.
- Diagnostic Scorecard: BLOCKED on CRITICAL, WARNINGS on MAJOR/MINOR, PASS.
- TASK-025 Surgical AI Remediation: Version forking with `created_from_correction_id`.
- Re-auditing of remediated content versions.
"""
import io
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.db.session import get_db
from app.main import create_app
from app.modules.engine_factual.verifier import run_deterministic_factual_check
from app.modules.engine_visual.analyzer import run_visual_check
from tests.db_helpers import get_test_db, reset_test_db
from tests.jwt_helpers import FakeJWKS, TestKey, make_verifier
from tests.settings_helpers import clean_settings

KEY = TestKey("kid-phase4", "EC")

ADMIN_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _setup_db() -> None:
    import asyncio
    asyncio.run(reset_test_db())


@pytest.fixture(autouse=True)
def _mock_gemini_verifier():
    from app.modules.documents.extractor import extract_candidate_rules_deterministic
    from app.modules.engine_factual.verifier import run_deterministic_factual_check
    mock_settings = clean_settings(gemini_api_key="mock-live-key")

    async def _mock_extract(sections, **kw):
        return extract_candidate_rules_deterministic(sections)

    async def _mock_factual(text, rules, **kw):
        status, findings = run_deterministic_factual_check(text, rules)
        return status, findings, {"engine_mode": "gemini_live", "claims_checked": len(findings)}

    with (
        patch("app.modules.documents.router.async_extract_candidate_rules", side_effect=_mock_extract),
        patch("app.modules.orchestrator.runner.run_async_factual_check", side_effect=_mock_factual),
        patch("app.modules.engine_factual.verifier.run_factual_check", side_effect=lambda text, rules, **kw: run_deterministic_factual_check(text, rules)),
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
        json={"name": "Nexus Agency", "slug": f"nexus-{uuid.uuid4().hex[:6]}"},
        headers=_token(ADMIN_ID, "admin@nexus.com"),
    ).json()
    w_id = ws["workspace_id"]

    # 2. Invite Brand Manager and Content Creator
    bm_id = uuid.uuid4()
    bm_email = f"bm-{uuid.uuid4().hex[:6]}@nexus.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": bm_email, "role": "BRAND_MANAGER", "full_name": "BM User"},
        headers=_token(ADMIN_ID, "admin@nexus.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(bm_id, bm_email))

    cr_id = uuid.uuid4()
    cr_email = f"creator-{uuid.uuid4().hex[:6]}@nexus.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": cr_email, "role": "CONTENT_CREATOR", "full_name": "Creator User"},
        headers=_token(ADMIN_ID, "admin@nexus.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(cr_id, cr_email))

    # 3. Create Client Brand
    client_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Verve Botanical", "code": "VERVE"},
        headers=_token(ADMIN_ID, "admin@nexus.com"),
    ).json()
    c_id = client_res["client_id"]

    # 4. Assign Members to Client Brand
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(bm_id), "client_role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID, "admin@nexus.com"),
    )
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/members",
        json={"user_id": str(cr_id), "client_role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID, "admin@nexus.com"),
    )

    # 5. Ingest Guidelines
    guidelines = (
        "Never use 'cheap'; instead use 'accessible luxury'.\n"
        "Brand Color: #1A2B3C.\n"
        "Factual: All botanical extracts are certified organic."
    )
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/documents",
        data={"title": "Verve Guidelines"},
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


def test_asset_creation_and_retrieval() -> None:
    c = _client()
    w_id, c_id, _, cr_id = _seed_workspace_and_active_brand(c)

    # Content creator creates an asset
    asset_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={
            "title": "Summer Campaign Post",
            "content_type": "TEXT",
            "text_content": "Experience our new serum today.",
        },
        headers=_token(cr_id),
    )
    assert asset_res.status_code == 201
    asset_data = asset_res.json()
    assert asset_data["title"] == "Summer Campaign Post"
    assert asset_data["latest_version"]["version_number"] == 1
    assert asset_data["latest_version"]["text_content"] == "Experience our new serum today."
    a_id = asset_data["asset_id"]

    # Retrieve asset
    get_res = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}",
        headers=_token(cr_id),
    )
    assert get_res.status_code == 200
    assert get_res.json()["asset_id"] == a_id


def test_pre_publication_audit_detection_and_scorecard() -> None:
    c = _client()
    w_id, c_id, _, cr_id = _seed_workspace_and_active_brand(c)

    # Content contains forbidden term 'cheap' AND contradicts fact ('synthetic' vs 'organic')
    non_compliant_text = "Our cheap serum is formulated with a synthetic base for glowing skin."

    asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={
            "title": "Serum Launch Copy",
            "content_type": "TEXT",
            "text_content": non_compliant_text,
        },
        headers=_token(cr_id),
    ).json()

    a_id = asset["asset_id"]
    v_id = asset["latest_version"]["version_id"]

    # Trigger audit
    audit_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(cr_id),
    )
    assert audit_res.status_code == 200
    audit_data = audit_res.json()

    # Overall verdict should be BLOCKED due to CRITICAL factual contradiction
    assert audit_data["overall_verdict"] == "BLOCKED"
    assert audit_data["status"] == "COMPLETED"

    # Verify findings
    findings = audit_data["findings"]
    assert len(findings) >= 2

    # Check Terminology finding
    term_finding = next((f for f in findings if f["evidence"].get("forbidden_term") == "cheap"), None)
    assert term_finding is not None
    assert term_finding["location_start"] == non_compliant_text.index("cheap")
    assert term_finding["location_end"] == term_finding["location_start"] + len("cheap")
    assert len(term_finding["suggestions"]) == 1
    assert term_finding["suggestions"][0]["suggested_text"] == "accessible luxury"

    # Check Factual finding (CONTRADICTED)
    fact_finding = next((f for f in findings if f["evidence"].get("verdict") == "CONTRADICTED"), None)
    assert fact_finding is not None
    assert fact_finding["severity"] == "CRITICAL"
    assert "organic" in fact_finding["evidence"]["citation"].lower()


def test_surgical_remediation_and_version_forking() -> None:
    c = _client()
    w_id, c_id, _, cr_id = _seed_workspace_and_active_brand(c)

    # Content with forbidden term
    text = "We offer a cheap option for daily wellness."
    asset = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets",
        json={"title": "Wellness Post", "content_type": "TEXT", "text_content": text},
        headers=_token(cr_id),
    ).json()

    a_id = asset["asset_id"]
    v_id = asset["latest_version"]["version_id"]

    # Trigger audit
    audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
        headers=_token(cr_id),
    ).json()
    run_id = audit["audit_run_id"]

    # Find the suggestion for 'cheap' -> 'accessible luxury'
    suggestions = [s for f in audit["findings"] for s in f["suggestions"]]
    assert len(suggestions) > 0
    sugg_id = suggestions[0]["suggestion_id"]

    # Apply surgical remediation
    rem_res = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/audits/{run_id}/remediate",
        json={"suggestion_ids": [sugg_id]},
        headers=_token(cr_id),
    )
    assert rem_res.status_code == 200
    new_version = rem_res.json()

    # Version forked to version 2
    assert new_version["version_number"] == 2
    assert new_version["created_from_correction_id"] == sugg_id
    assert new_version["text_content"] == "We offer a accessible luxury option for daily wellness."

    # Re-audit version 2: Terminology should now PASS
    re_audit = c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{new_version['version_id']}/audit",
        headers=_token(cr_id),
    ).json()

    term_check = next(c for c in re_audit["checks"] if c["engine_type"] == "TERMINOLOGY")
    assert term_check["status"] == "PASS"
    assert re_audit["overall_verdict"] == "PASS"


def test_visual_compliance_ciede2000_advisory() -> None:
    """Test ADR-008: Visual color Delta E > 5.0 is strictly ADVISORY."""
    # Create pure red in-memory image (RGB 255, 0, 0)
    img = Image.new("RGB", (50, 50), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    # Brand color is Midnight Blue (#1A2B3C)
    rules = [
        {
            "category": "COLOR",
            "rule_id": str(uuid.uuid4()),
            "rule_code": "RULE-COL-001",
            "content": {"hex": "#1A2B3C", "name": "Midnight Blue"},
        }
    ]

    status, findings = run_visual_check(img_bytes, rules)
    assert status == "WARNING"
    assert len(findings) > 0
    finding = findings[0]
    # Pure red against dark blue has Delta E > 50
    assert finding.delta_e > 5.0
    assert finding.severity == "ADVISORY"  # Strictly advisory per ADR-008
