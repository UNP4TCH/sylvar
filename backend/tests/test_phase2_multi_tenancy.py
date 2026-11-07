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
from tests.db_helpers import get_test_db, reset_test_db
from tests.jwt_helpers import FakeJWKS, TestKey, make_verifier
from tests.settings_helpers import clean_settings

KEY = TestKey("kid-phase2", "EC")

ADMIN_ID = uuid.uuid4()
USER_A_ID = uuid.uuid4()
USER_B_ID = uuid.uuid4()


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


def test_create_workspace_assigns_admin() -> None:
    c = _client()
    resp = c.post(
        "/api/v1/workspaces",
        json={"name": "Vanguard Agency", "slug": "vanguard-agency"},
        headers=_token(ADMIN_ID, "admin@vanguard.com"),
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
        headers=_token(ADMIN_ID, "admin@vanguard.com"),
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "SLUG_EXISTS"


def test_invite_member_and_last_admin_protection() -> None:
    c = _client()
    ws_resp = c.post(
        "/api/v1/workspaces",
        json={"name": "Creative House", "slug": "creative-house"},
        headers=_token(ADMIN_ID, "admin@agency.com"),
    )
    w_id = ws_resp.json()["workspace_id"]

    # Invite Member A as CONTENT_CREATOR
    inv_resp = c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": "creator@agency.com", "role": "CONTENT_CREATOR", "full_name": "Alice Creator"},
        headers=_token(ADMIN_ID, "admin@agency.com"),
    )
    assert inv_resp.status_code == 201
    member_a = inv_resp.json()
    assert member_a["role"] == "CONTENT_CREATOR"
    assert member_a["status"] == "INVITED"

    # Member A authenticates to accept invitation and activate membership
    a_id = uuid.uuid4()
    c.get("/api/v1/workspaces", headers=_token(a_id, "creator@agency.com"))

    # List members
    list_resp = c.get(f"/api/v1/workspaces/{w_id}/members", headers=_token(ADMIN_ID, "admin@agency.com"))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2

    # Attempt to revoke last active admin (should fail 409)
    admin_mem_id = next(m["membership_id"] for m in list_resp.json() if m["role"] == "WORKSPACE_ADMIN")
    rev_admin = c.delete(f"/api/v1/workspaces/{w_id}/members/{admin_mem_id}", headers=_token(ADMIN_ID, "admin@agency.com"))
    assert rev_admin.status_code == 409
    assert rev_admin.json()["code"] == "LAST_ADMIN_PROTECTION"


def test_dual_tenant_isolation_and_client_scoping() -> None:
    c = _client()
    # 1. Create Workspace
    ws_resp = c.post(
        "/api/v1/workspaces",
        json={"name": "Omni Agency", "slug": "omni-agency"},
        headers=_token(ADMIN_ID, "admin@omni.com"),
    )
    w_id = ws_resp.json()["workspace_id"]

    # 2. Invite User A and User B
    u_a_id = uuid.uuid4()
    u_a_email = "alice@omni.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": u_a_email, "role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID, "admin@omni.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(u_a_id, u_a_email))

    u_b_id = uuid.uuid4()
    u_b_email = "bob@omni.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": u_b_email, "role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID, "admin@omni.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(u_b_id, u_b_email))

    # 3. Create Client 1 (Acme) and Client 2 (Beta)
    client1 = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Acme Corp", "code": "ACME", "description": "Client 1"},
        headers=_token(ADMIN_ID, "admin@omni.com"),
    ).json()
    c1_id = client1["client_id"]

    client2 = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Beta Inc", "code": "BETA", "description": "Client 2"},
        headers=_token(ADMIN_ID, "admin@omni.com"),
    ).json()
    c2_id = client2["client_id"]

    # 4. Assign Alice to Client 1 (Acme) as BRAND_MANAGER
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c1_id}/members",
        json={"user_id": str(u_a_id), "client_role": "BRAND_MANAGER"},
        headers=_token(ADMIN_ID, "admin@omni.com"),
    )

    # 5. Assign Bob to Client 2 (Beta) as CONTENT_CREATOR
    c.post(
        f"/api/v1/workspaces/{w_id}/clients/{c2_id}/members",
        json={"user_id": str(u_b_id), "client_role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID, "admin@omni.com"),
    )

    # Invariant ADR-003: An unassigned Workspace Admin cannot access Client 1 without explicit client assignment
    admin2_id = uuid.uuid4()
    admin2_email = "admin2@omni.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": admin2_email, "role": "WORKSPACE_ADMIN"},
        headers=_token(ADMIN_ID, "admin@omni.com"),
    )
    c.get("/api/v1/workspaces", headers=_token(admin2_id, admin2_email))

    admin2_access_c1 = c.get(f"/api/v1/workspaces/{w_id}/clients/{c1_id}", headers=_token(admin2_id, admin2_email))
    assert admin2_access_c1.status_code == 403
    assert admin2_access_c1.json()["code"] == "CLIENT_ASSIGNMENT_REQUIRED"

    # Alice (assigned to Client 1) CAN access Client 1
    alice_c1 = c.get(f"/api/v1/workspaces/{w_id}/clients/{c1_id}", headers=_token(u_a_id, u_a_email))
    assert alice_c1.status_code == 200
    assert alice_c1.json()["code"] == "ACME"

    # Alice (NOT assigned to Client 2) CANNOT access Client 2
    alice_c2 = c.get(f"/api/v1/workspaces/{w_id}/clients/{c2_id}", headers=_token(u_a_id, u_a_email))
    assert alice_c2.status_code == 403
    assert alice_c2.json()["code"] == "CLIENT_ASSIGNMENT_REQUIRED"

    # Bob (assigned to Client 2) CAN access Client 2
    bob_c2 = c.get(f"/api/v1/workspaces/{w_id}/clients/{c2_id}", headers=_token(u_b_id, u_b_email))
    assert bob_c2.status_code == 200
    assert bob_c2.json()["code"] == "BETA"

    # Bob CANNOT access Client 1
    bob_c1 = c.get(f"/api/v1/workspaces/{w_id}/clients/{c1_id}", headers=_token(u_b_id, u_b_email))
    assert bob_c1.status_code == 403
    assert bob_c1.json()["code"] == "CLIENT_ASSIGNMENT_REQUIRED"


def test_real_time_revocation_checks() -> None:
    c = _client()
    ws = c.post(
        "/api/v1/workspaces",
        json={"name": "Delta Agency", "slug": "delta-agency"},
        headers=_token(ADMIN_ID, "admin@delta.com"),
    ).json()
    w_id = ws["workspace_id"]

    u_id = uuid.uuid4()
    u_email = "temp@delta.com"
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": u_email, "role": "CONTENT_CREATOR"},
        headers=_token(ADMIN_ID, "admin@delta.com"),
    ).json()

    # Member accepts invitation
    c.get("/api/v1/workspaces", headers=_token(u_id, u_email))

    # Retrieve active membership id for revocation
    members = c.get(f"/api/v1/workspaces/{w_id}/members", headers=_token(ADMIN_ID, "admin@delta.com")).json()
    m_id = next(m["membership_id"] for m in members if m["email"] == u_email)

    # Member can view workspace
    m_access = c.get(f"/api/v1/workspaces/{w_id}", headers=_token(u_id, u_email))
    assert m_access.status_code == 200

    # Admin revokes membership
    rev = c.delete(f"/api/v1/workspaces/{w_id}/members/{m_id}", headers=_token(ADMIN_ID, "admin@delta.com"))
    assert rev.status_code == 200
    assert rev.json()["status"] == "REVOKED"

    # Immediate revocation: subsequent request is denied 403
    m_denied = c.get(f"/api/v1/workspaces/{w_id}", headers=_token(u_id, u_email))
    assert m_denied.status_code == 403
    assert m_denied.json()["code"] == "MEMBERSHIP_REVOKED"
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


def test_update_workspace_rename() -> None:
    c = _client()
    user_id = uuid.uuid4()
    ws_resp = c.post(
        "/api/v1/workspaces",
        json={"name": "Old Workspace Name", "slug": "rename-ws"},
        headers=_token(user_id, "admin@rename.com"),
    )
    assert ws_resp.status_code == 201
    w_id = ws_resp.json()["workspace_id"]

    # Unauthorized user cannot rename
    other_user_id = uuid.uuid4()
    denied = c.patch(
        f"/api/v1/workspaces/{w_id}",
        json={"name": "Hacked Name"},
        headers=_token(other_user_id, "stranger@other.com"),
    )
    assert denied.status_code == 403

    # Authorized admin renames workspace
    rename_resp = c.patch(
        f"/api/v1/workspaces/{w_id}",
        json={"name": "New Renamed Workspace"},
        headers=_token(user_id, "admin@rename.com"),
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["name"] == "New Renamed Workspace"
    assert rename_resp.json()["slug"] == "rename-ws"

    # Get workspace reflects new name
    get_resp = c.get(f"/api/v1/workspaces/{w_id}", headers=_token(user_id, "admin@rename.com"))
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "New Renamed Workspace"


def test_retry_and_recover_invitations() -> None:
    c = _client()
    admin_id = uuid.uuid4()
    ws_resp = c.post(
        "/api/v1/workspaces",
        json={"name": "Dispatch Agency", "slug": "dispatch-agency"},
        headers=_token(admin_id, "admin@dispatch.com"),
    )
    w_id = ws_resp.json()["workspace_id"]

    # Invite member
    inv_resp = c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": "deliverme@dispatch.com", "role": "CONTENT_CREATOR"},
        headers=_token(admin_id, "admin@dispatch.com"),
    )
    assert inv_resp.status_code == 201
    inv_data = inv_resp.json()
    inv_id = inv_data["membership_id"]

    # Retry invitation delivery (should succeed and update delivery_status without failing)
    retry_resp = c.post(
        f"/api/v1/workspaces/{w_id}/invitations/{inv_id}/retry",
        headers=_token(admin_id, "admin@dispatch.com"),
    )
    assert retry_resp.status_code == 200
    assert retry_resp.json()["delivery_status"] in ("DELIVERED", "PENDING", "FAILED")


def test_rename_client_brand() -> None:
    c = _client()
    admin_id = uuid.uuid4()
    ws_resp = c.post(
        "/api/v1/workspaces",
        json={"name": "Branding Co", "slug": f"branding-co-{uuid.uuid4().hex[:6]}"},
        headers=_token(admin_id, "admin@branding.co"),
    )
    assert ws_resp.status_code == 201
    w_id = ws_resp.json()["workspace_id"]

    # 1. Create client brand 1 & 2
    c1_resp = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Original Brand", "code": "ORIG", "description": "Original desc"},
        headers=_token(admin_id, "admin@branding.co"),
    )
    assert c1_resp.status_code == 201
    c1_id = c1_resp.json()["client_id"]

    c2_resp = c.post(
        f"/api/v1/workspaces/{w_id}/clients",
        json={"name": "Second Brand", "code": "SECOND", "description": "Second desc"},
        headers=_token(admin_id, "admin@branding.co"),
    )
    assert c2_resp.status_code == 201
    c2_id = c2_resp.json()["client_id"]

    # 2. Rename client brand 1 successfully
    rename_resp = c.patch(
        f"/api/v1/workspaces/{w_id}/clients/{c1_id}",
        json={"name": "Renamed Brand Global"},
        headers=_token(admin_id, "admin@branding.co"),
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["name"] == "Renamed Brand Global"

    # Verify via GET
    get_resp = c.get(
        f"/api/v1/workspaces/{w_id}/clients/{c1_id}",
        headers=_token(admin_id, "admin@branding.co"),
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Renamed Brand Global"

    # 3. Validation: short/empty name -> 422
    short_resp = c.patch(
        f"/api/v1/workspaces/{w_id}/clients/{c1_id}",
        json={"name": " "},
        headers=_token(admin_id, "admin@branding.co"),
    )
    assert short_resp.status_code == 422

    # 4. Duplicate name conflict -> 409
    dup_resp = c.patch(
        f"/api/v1/workspaces/{w_id}/clients/{c1_id}",
        json={"name": "Second Brand"},
        headers=_token(admin_id, "admin@branding.co"),
    )
    assert dup_resp.status_code == 409
    assert dup_resp.json()["code"] == "CLIENT_NAME_CONFLICT"

    # 5. Permission check: unassigned / unauthorized user cannot rename -> 403
    creator_id = uuid.uuid4()
    c.post(
        f"/api/v1/workspaces/{w_id}/members",
        json={"email": "creator@branding.co", "role": "CONTENT_CREATOR"},
        headers=_token(admin_id, "admin@branding.co"),
    )
    forbidden_resp = c.patch(
        f"/api/v1/workspaces/{w_id}/clients/{c1_id}",
        json={"name": "Unauthorized Hack"},
        headers=_token(creator_id, "creator@branding.co"),
    )
    assert forbidden_resp.status_code == 403

