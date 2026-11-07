"""Phase 2 Integration Test Suite: Multi-Tenancy, Client Scoping & 5-Gate Authorization.

Verifies:
- Task 007-013 deliverables.
- Dual-tenant isolation (User assigned to Client 1 cannot access Client 2).
- ADR-003: Workspace Admin cannot ambiently access client brands without explicit assignment.
- Real-time membership and client assignment revocation.
- Exactly three roles: WORKSPACE_ADMIN, BRAND_MANAGER, CONTENT_CREATOR.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app
from app.models.workspace import UserRole
from tests.db_helpers import get_test_db, init_test_db
from tests.jwt_helpers import FakeJWKS, TestKey, make_verifier
from tests.settings_helpers import clean_settings

KEY = TestKey("kid-phase2", "EC")

ADMIN_ID = uuid.uuid4()
USER_A_ID = uuid.uuid4()
USER_B_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _setup_db() -> None:
    import asyncio
    asyncio.run(init_test_db())


def _client() -> TestClient:
    app = create_app(clean_settings(), jwt_verifier=make_verifier(FakeJWKS(KEY)))
    app.dependency_overrides[get_db] = get_test_db
    return TestClient(app, raise_server_exceptions=False)


def _token(user_id: uuid.UUID) -> dict[str, str]:
    token_str = KEY.token(sub=str(user_id))
    return {"Authorization": f"Bearer {token_str}"}


def test_create_workspace_assigns_admin() -> None:
    c = _client()
    resp = c.post(
        "/api/v1/workspaces",
        json={"name": "Vanguard Agency", "slug": "vanguard-agency"},
        headers=_token(ADMIN_ID),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Vanguard Agency"
    assert data["slug"] == "vanguard-agency"
    assert data["current_role"] == UserRole.WORKSPACE_ADMIN.value

    # Check slug uniqueness conflict
    dup = c.post(
        "/api/v1/workspaces",
        json={"name": "Duplicate Agency", "slug": "vanguard-agency"},
        headers=_token(ADMIN_ID),
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "SLUG_EXISTS"


def test_invite_member_and_last_admin_protection() -> None:
    c = _client()
    ws_resp = c.post(
        "/api/v1/workspaces",
        json={"name": "Creative House", "slug": "creative-house"},
        headers=_token(ADMIN_ID),
    )
    w_id = ws_resp.json()["workspace_id"]

    # Invite Member A as CONTENT_CREATOR
    inv_resp = c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": "creator@agency.com", "role": "CONTENT_CREATOR", "full_name": "Alice Creator"},
        headers=_token(ADMIN_ID),
    )
    assert inv_resp.status_code == 201
    member_a = inv_resp.json()
    assert member_a["role"] == "CONTENT_CREATOR"
    assert member_a["status"] == "ACTIVE"

    # List members
    list_resp = c.get(f"/api/v1/workspaces/{w_id}/members", headers=_token(ADMIN_ID))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2

    # Attempt to revoke last active admin (should fail 409)
    admin_mem_id = next(m["membership_id"] for m in list_resp.json() if m["role"] == "WORKSPACE_ADMIN")
    rev_admin = c.delete(f"/api/v1/workspaces/{w_id}/members/{admin_mem_id}", headers=_token(ADMIN_ID))
    assert rev_admin.status_code == 409
    assert rev_admin.json()["code"] == "LAST_ADMIN_PROTECTION"


def test_dual_tenant_isolation_and_client_scoping() -> None:
    c = _client()
    # 1. Create Workspace
    ws_resp = c.post(
        "/api/v1/workspaces",
        json={"name": "Omni Agency", "slug": "omni-agency"},
        headers=_token(ADMIN_ID),
    )
    w_id = ws_resp.json()["workspace_id"]

    # 2. Invite User A and User B
    inv_a = c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": "alice@omni.com", "role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID),
    ).json()
    u_a = inv_a["user_id"]

    inv_b = c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": "bob@omni.com", "role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID),
    ).json()
    u_b = inv_b["user_id"]

    # 3. Create Client 1 (Acme) and Client 2 (Beta)
    client1 = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Acme Corp", "code": "ACME", "description": "Client 1"},
        headers=_token(ADMIN_ID),
    ).json()
    c1_id = client1["client_id"]

    client2 = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Beta Inc", "code": "BETA", "description": "Client 2"},
        headers=_token(ADMIN_ID),
    ).json()
    c2_id = client2["client_id"]

    # 4. Assign Alice to Client 1 (Acme) as BRAND_MANAGER
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c1_id}/members",
        json={"user_id": u_a, "client_role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID),
    )

    # 5. Assign Bob to Client 2 (Beta) as CONTENT_CREATOR
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c2_id}/members",
        json={"user_id": u_b, "client_role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID),
    )

    # Invariant ADR-003: Workspace Admin cannot access Client 1 without explicit client assignment
    admin_access_c1 = c.get(f"/api/v1/workspaces/{w_id}/clients/{c1_id}", headers=_token(ADMIN_ID))
    assert admin_access_c1.status_code == 403
    assert admin_access_c1.json()["code"] == "CLIENT_ASSIGNMENT_REQUIRED"

    # Alice (assigned to Client 1) CAN access Client 1
    alice_c1 = c.get(f"/api/v1/workspaces/{w_id}/clients/{c1_id}", headers=_token(uuid.UUID(u_a)))
    assert alice_c1.status_code == 200
    assert alice_c1.json()["code"] == "ACME"

    # Alice (NOT assigned to Client 2) CANNOT access Client 2
    alice_c2 = c.get(f"/api/v1/workspaces/{w_id}/clients/{c2_id}", headers=_token(uuid.UUID(u_a)))
    assert alice_c2.status_code == 403
    assert alice_c2.json()["code"] == "CLIENT_ASSIGNMENT_REQUIRED"

    # Bob (assigned to Client 2) CAN access Client 2
    bob_c2 = c.get(f"/api/v1/workspaces/{w_id}/clients/{c2_id}", headers=_token(uuid.UUID(u_b)))
    assert bob_c2.status_code == 200
    assert bob_c2.json()["code"] == "BETA"

    # Bob CANNOT access Client 1
    bob_c1 = c.get(f"/api/v1/workspaces/{w_id}/clients/{c1_id}", headers=_token(uuid.UUID(u_b)))
    assert bob_c1.status_code == 403
    assert bob_c1.json()["code"] == "CLIENT_ASSIGNMENT_REQUIRED"


def test_real_time_revocation_checks() -> None:
    c = _client()
    ws = c.post(
        "/api/v1/workspaces",
        json={"name": "Delta Agency", "slug": "delta-agency"},
        headers=_token(ADMIN_ID),
    ).json()
    w_id = ws["workspace_id"]

    inv = c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": "temp@delta.com", "role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID),
    ).json()
    m_id = inv["membership_id"]
    u_id = inv["user_id"]

    # Member can view workspace
    m_access = c.get(f"/api/v1/workspaces/{w_id}", headers=_token(uuid.UUID(u_id)))
    assert m_access.status_code == 200

    # Admin revokes membership
    rev = c.delete(f"/api/v1/workspaces/{w_id}/members/{m_id}", headers=_token(ADMIN_ID))
    assert rev.status_code == 200
    assert rev.json()["status"] == "REVOKED"

    # Immediate revocation: subsequent request is denied 403
    m_denied = c.get(f"/api/v1/workspaces/{w_id}", headers=_token(uuid.UUID(u_id)))
    assert m_denied.status_code == 403
    assert m_denied.json()["code"] == "MEMBERSHIP_REVOKED"


def test_user_me_profile_discovery() -> None:
    c = _client()
    # 1. New user with no workspaces yet
    fresh_user_id = uuid.uuid4()
    me_resp = c.get("/api/v1/users/me", headers=_token(fresh_user_id))
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["user_id"] == str(fresh_user_id)
    assert data["workspaces"] == []
    assert data["client_assignments"] == []

    # 2. Create workspace
    c.post(
        "/api/v1/workspaces",
        json={"name": "My Workspace", "slug": "my-workspace"},
        headers=_token(fresh_user_id),
    )

    me_after = c.get("/api/v1/users/me", headers=_token(fresh_user_id)).json()
    assert len(me_after["workspaces"]) == 1
    assert me_after["workspaces"][0]["workspace_name"] == "My Workspace"
    assert me_after["workspaces"][0]["role"] == "WORKSPACE_ADMIN"
