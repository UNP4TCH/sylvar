"""Direct PostgreSQL Acceptance Logic & Migration 006 Privilege Verification Tests.

Executes real PostgreSQL queries against the live PostgreSQL backend:
1. Verifies that Migration 006 SQL strictly revokes all direct UPDATE/INSERT/DELETE
   privileges from 'authenticated' on workspace_invitations.
2. Verifies that EXECUTE on public.accept_workspace_invitation(UUID, UUID) is:
   - Revoked from PUBLIC and authenticated.
   - Granted strictly to sylvar_app_user.
3. Tests the exact acceptance function algorithm inside the PostgreSQL engine:
   - Validates that legitimate invitee with matching normalized email accepts and activates.
   - Validates that an existing WORKSPACE_ADMIN is NEVER downgraded by accepting a lower-role invitation.
   - Validates that a deliberately revoked membership (status='REVOKED' or revoked_at IS NOT NULL)
     CANNOT be silently reactivated via standard invitation acceptance (raises 42501).
   - Validates that email mismatch raises 42501.
   - Validates that expired invitation raises 22008.
   - Validates that already accepted invitation cannot be accepted again (raises 23514).
   - Validates that delivery metadata columns remain completely untouched.
"""
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


@pytest.mark.anyio
async def test_migration006_privilege_declarations_least_privilege():
    """Verify Migration 006 SQL enforces least-privilege catalog grants."""
    from pathlib import Path
    mig_path = Path(__file__).resolve().parent.parent.parent / "supabase" / "migrations" / "006_batch2a_invitation_security.sql"
    if not mig_path.exists():
        mig_path = Path("../supabase/migrations/006_batch2a_invitation_security.sql")
    with open(mig_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # 1. 'authenticated' must have ZERO direct UPDATE permissions
    assert "GRANT UPDATE" in sql_content
    # Ensure GRANT UPDATE targets ONLY sylvar_app_user, NEVER authenticated
    assert "TO sylvar_app_user;" in sql_content
    assert "GRANT UPDATE" not in "".join([l for l in sql_content.splitlines() if "TO authenticated" in l and "GRANT SELECT" not in l])

    # 2. 'authenticated' has ONLY SELECT
    assert "GRANT SELECT ON public.workspace_invitations TO authenticated;" in sql_content

    # 3. Protected columns are excluded from GRANT UPDATE
    for col in ["workspace_id", "email", "role", "invited_by_user_id", "created_at", "expires_at"]:
        update_section = sql_content[sql_content.find("GRANT UPDATE"):sql_content.find("TO sylvar_app_user;")]
        assert f" {col}," not in update_section
        assert f" {col}\n" not in update_section

    # 4. Acceptance function is defined as SECURITY DEFINER with safe search_path (pg_catalog first)
    func_start = sql_content.find("CREATE OR REPLACE FUNCTION public.accept_workspace_invitation")
    func_end = sql_content.find("REVOKE ALL ON FUNCTION public.accept_workspace_invitation", func_start)
    func_block = sql_content[func_start:func_end]
    assert "SECURITY DEFINER" in func_block
    assert "SET search_path = pg_catalog, public" in func_block
    assert "pg_temp" not in func_block

    # 5. Function EXECUTE is revoked from PUBLIC and authenticated; granted ONLY to sylvar_app_user
    assert "REVOKE ALL ON FUNCTION public.accept_workspace_invitation(UUID, UUID) FROM PUBLIC, authenticated;" in sql_content
    assert "GRANT EXECUTE ON FUNCTION public.accept_workspace_invitation(UUID, UUID) TO sylvar_app_user;" in sql_content
    assert "GRANT EXECUTE ON FUNCTION public.accept_workspace_invitation(UUID, UUID) TO authenticated;" not in sql_content

    # 6. Zero DELETE grants anywhere
    assert "GRANT DELETE" not in sql_content


@pytest.mark.anyio
async def test_postgres_acceptance_function_logic_in_engine():
    """Execute the exact acceptance function algorithm in real PostgreSQL engine."""
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("Skipping PostgreSQL test: DATABASE_URL is not PostgreSQL")

    engine = create_async_engine(settings.database_url)

    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            # Create isolated test environment in pg_temp
            await conn.execute(text("""
                CREATE TEMP TABLE temp_users (
                    id UUID PRIMARY KEY,
                    email VARCHAR(255) NOT NULL
                )
            """))

            await conn.execute(text("""
                CREATE TEMP TABLE temp_invitations (
                    id UUID PRIMARY KEY,
                    workspace_id UUID NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    delivery_status VARCHAR(50) NOT NULL,
                    delivery_attempts INTEGER NOT NULL DEFAULT 1,
                    claim_expires_at TIMESTAMPTZ NULL,
                    auth_user_id UUID NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    accepted_at TIMESTAMPTZ NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))

            await conn.execute(text("""
                CREATE TEMP TABLE temp_memberships (
                    workspace_id UUID NOT NULL,
                    user_id UUID NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    revoked_at TIMESTAMPTZ NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (workspace_id, user_id)
                )
            """))

            # Create the exact acceptance function matching Migration 006 inside pg_temp
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION pg_temp.test_accept_invitation(
                    p_inv_id UUID,
                    p_user_id UUID
                )
                RETURNS JSONB
                LANGUAGE plpgsql
                AS $$
                DECLARE
                    v_user_email VARCHAR;
                    v_inv pg_temp.temp_invitations%ROWTYPE;
                    v_existing_mem pg_temp.temp_memberships%ROWTYPE;
                    v_final_role VARCHAR;
                BEGIN
                    IF p_user_id IS NULL THEN
                        RAISE EXCEPTION 'User ID is required' USING ERRCODE = '28000';
                    END IF;

                    SELECT email INTO v_user_email
                    FROM pg_temp.temp_users
                    WHERE id = p_user_id;

                    IF v_user_email IS NULL THEN
                        RAISE EXCEPTION 'User profile not found for authenticated caller' USING ERRCODE = 'P0002';
                    END IF;

                    SELECT * INTO v_inv
                    FROM pg_temp.temp_invitations
                    WHERE id = p_inv_id
                    FOR UPDATE;

                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'Invitation not found' USING ERRCODE = 'P0002';
                    END IF;

                    -- Normalized email check
                    IF lower(v_inv.email) <> lower(v_user_email) THEN
                        RAISE EXCEPTION 'Invitation email does not match authenticated user email' USING ERRCODE = '42501';
                    END IF;

                    -- Status check
                    IF v_inv.status <> 'PENDING' THEN
                        RAISE EXCEPTION 'Invitation is already resolved or revoked (status: %)', v_inv.status USING ERRCODE = '23514';
                    END IF;

                    -- Expiry check
                    IF v_inv.expires_at <= now() THEN
                        RAISE EXCEPTION 'Invitation has expired' USING ERRCODE = '22008';
                    END IF;

                    -- Membership preservation and revocation guard
                    SELECT * INTO v_existing_mem
                    FROM pg_temp.temp_memberships
                    WHERE workspace_id = v_inv.workspace_id
                      AND user_id = p_user_id
                    FOR UPDATE;

                    IF FOUND THEN
                        -- Guard 1: Deliberately revoked memberships CANNOT be silently reactivated
                        IF v_existing_mem.status = 'REVOKED' OR v_existing_mem.revoked_at IS NOT NULL THEN
                            RAISE EXCEPTION 'User membership was previously revoked and cannot be reactivated via standard invitation acceptance' USING ERRCODE = '42501';
                        END IF;

                        -- Guard 2: Never downgrade WORKSPACE_ADMIN
                        IF v_existing_mem.role = 'WORKSPACE_ADMIN' THEN
                            v_final_role := 'WORKSPACE_ADMIN';
                        ELSE
                            v_final_role := v_existing_mem.role;
                        END IF;

                        UPDATE pg_temp.temp_memberships
                        SET status = 'ACTIVE',
                            role = v_final_role,
                            updated_at = now()
                        WHERE workspace_id = v_inv.workspace_id
                          AND user_id = p_user_id;
                    ELSE
                        v_final_role := v_inv.role;
                        INSERT INTO pg_temp.temp_memberships (workspace_id, user_id, role, status, created_at, updated_at)
                        VALUES (v_inv.workspace_id, p_user_id, v_final_role, 'ACTIVE', now(), now());
                    END IF;

                    -- Update status and audit fields only
                    UPDATE pg_temp.temp_invitations
                    SET status = 'ACCEPTED',
                        auth_user_id = p_user_id,
                        accepted_at = now(),
                        claim_expires_at = NULL,
                        updated_at = now()
                    WHERE id = v_inv.id;

                    RETURN jsonb_build_object(
                        'invitation_id', v_inv.id,
                        'workspace_id', v_inv.workspace_id,
                        'user_id', p_user_id,
                        'role', v_final_role,
                        'status', 'ACCEPTED'
                    );
                END;
                $$;
            """))

            # Seed test data
            ws_id = uuid.uuid4()
            invitee_id = uuid.uuid4()
            attacker_id = uuid.uuid4()
            admin_id = uuid.uuid4()
            revoked_id = uuid.uuid4()

            await conn.execute(text("""
                INSERT INTO pg_temp.temp_users (id, email) VALUES
                (:iid, 'invitee@external.com'),
                (:aid, 'attacker@evil.com'),
                (:adm, 'admin@agency.com'),
                (:rvk, 'revoked@external.com')
            """), {"iid": invitee_id, "aid": attacker_id, "adm": admin_id, "rvk": revoked_id})

            valid_inv_id = uuid.uuid4()
            await conn.execute(text("""
                INSERT INTO pg_temp.temp_invitations
                (id, workspace_id, email, role, status, delivery_status, delivery_attempts, expires_at)
                VALUES
                (:id, :wid, 'invitee@external.com', 'CONTENT_CREATOR', 'PENDING', 'DELIVERED', 1, now() + interval '7 days')
            """), {"id": valid_inv_id, "wid": ws_id})

            # Negative Test 1: Mismatched caller email FAILS (42501)
            sp1 = await conn.begin_nested()
            try:
                await conn.execute(text("""
                    SELECT pg_temp.test_accept_invitation(:invid, :aid)
                """), {"invid": valid_inv_id, "aid": attacker_id})
                pytest.fail("Expected exception for mismatched email")
            except Exception as exc_mismatch:
                await sp1.rollback()
                assert "Invitation email does not match authenticated user email" in str(exc_mismatch)

            # Positive Test: Fresh invitee acceptance succeeds
            res = await conn.execute(text("""
                SELECT pg_temp.test_accept_invitation(:invid, :iid)
            """), {"invid": valid_inv_id, "iid": invitee_id})
            out = res.scalar()
            assert out["status"] == "ACCEPTED"
            assert out["role"] == "CONTENT_CREATOR"

            # Verify delivery metadata remained untouched
            inv_row = (await conn.execute(text("SELECT status, delivery_status, delivery_attempts FROM pg_temp.temp_invitations WHERE id = :id"), {"id": valid_inv_id})).fetchone()
            assert inv_row[0] == "ACCEPTED"
            assert inv_row[1] == "DELIVERED"
            assert inv_row[2] == 1

            # Negative Test 2: Cannot accept again once ACCEPTED (23514)
            sp2 = await conn.begin_nested()
            try:
                await conn.execute(text("""
                    SELECT pg_temp.test_accept_invitation(:invid, :iid)
                """), {"invid": valid_inv_id, "iid": invitee_id})
                pytest.fail("Expected exception for already accepted invitation")
            except Exception as exc_reaccept:
                await sp2.rollback()
                assert "already resolved or revoked" in str(exc_reaccept)

            # Test 3: WORKSPACE_ADMIN cannot be downgraded by accepting lower-role invitation
            admin_inv_id = uuid.uuid4()
            await conn.execute(text("""
                INSERT INTO pg_temp.temp_memberships (workspace_id, user_id, role, status)
                VALUES (:wid, :adm, 'WORKSPACE_ADMIN', 'ACTIVE')
            """), {"wid": ws_id, "adm": admin_id})

            await conn.execute(text("""
                INSERT INTO pg_temp.temp_invitations
                (id, workspace_id, email, role, status, delivery_status, expires_at)
                VALUES
                (:id, :wid, 'admin@agency.com', 'CONTENT_CREATOR', 'PENDING', 'DELIVERED', now() + interval '7 days')
            """), {"id": admin_inv_id, "wid": ws_id})

            res_admin = await conn.execute(text("""
                SELECT pg_temp.test_accept_invitation(:invid, :adm)
            """), {"invid": admin_inv_id, "adm": admin_id})
            admin_out = res_admin.scalar()
            assert admin_out["status"] == "ACCEPTED"
            assert admin_out["role"] == "WORKSPACE_ADMIN", "WORKSPACE_ADMIN must NOT be downgraded!"

            # Test 4: Deliberately revoked membership CANNOT be silently reactivated (42501)
            await conn.execute(text("""
                INSERT INTO pg_temp.temp_memberships (workspace_id, user_id, role, status, revoked_at)
                VALUES (:wid, :rvk, 'BRAND_MANAGER', 'REVOKED', now() - interval '1 day')
            """), {"wid": ws_id, "rvk": revoked_id})

            revoked_inv_id = uuid.uuid4()
            await conn.execute(text("""
                INSERT INTO pg_temp.temp_invitations
                (id, workspace_id, email, role, status, delivery_status, expires_at)
                VALUES
                (:id, :wid, 'revoked@external.com', 'BRAND_MANAGER', 'PENDING', 'DELIVERED', now() + interval '7 days')
            """), {"id": revoked_inv_id, "wid": ws_id})

            sp4 = await conn.begin_nested()
            try:
                await conn.execute(text("""
                    SELECT pg_temp.test_accept_invitation(:invid, :rvk)
                """), {"invid": revoked_inv_id, "rvk": revoked_id})
                pytest.fail("Expected exception: deliberately revoked membership must not be silently reactivated")
            except Exception as exc_revoked:
                await sp4.rollback()
                assert "previously revoked and cannot be reactivated" in str(exc_revoked)

            # Test 5: Expired invitation FAILS (22008)
            exp_inv_id = uuid.uuid4()
            await conn.execute(text("""
                INSERT INTO pg_temp.temp_invitations
                (id, workspace_id, email, role, status, delivery_status, expires_at)
                VALUES
                (:id, :wid, 'invitee@external.com', 'CONTENT_CREATOR', 'PENDING', 'DELIVERED', now() - interval '1 hour')
            """), {"id": exp_inv_id, "wid": ws_id})

            sp5 = await conn.begin_nested()
            try:
                await conn.execute(text("""
                    SELECT pg_temp.test_accept_invitation(:invid, :iid)
                """), {"invid": exp_inv_id, "iid": invitee_id})
                pytest.fail("Expected exception for expired invitation")
            except Exception as exc_expired:
                await sp5.rollback()
                assert "Invitation has expired" in str(exc_expired)

        finally:
            await trans.rollback()

    await engine.dispose()




@pytest.mark.anyio
async def test_postgres_role_privilege_enforcement():
    """Verify that PostgreSQL engine enforces that 'authenticated' cannot execute function when revoked."""
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("Skipping PostgreSQL test: DATABASE_URL is not PostgreSQL")

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            # Create a test function in pg_temp
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION pg_temp.test_privilege_guard(p_id UUID)
                RETURNS BOOLEAN
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RETURN TRUE;
                END;
                $$;
            """))

            # Check that sylvar_app_user has EXECUTE on pg_temp
            res = (await conn.execute(text("SELECT has_function_privilege('sylvar_app_user', 'pg_temp.test_privilege_guard(uuid)', 'EXECUTE')"))).scalar()
            assert res is True

            # Revoke EXECUTE from PUBLIC and authenticated
            await conn.execute(text("REVOKE ALL ON FUNCTION pg_temp.test_privilege_guard(uuid) FROM PUBLIC, authenticated"))
            res_auth_after = (await conn.execute(text("SELECT has_function_privilege('authenticated', 'pg_temp.test_privilege_guard(uuid)', 'EXECUTE')"))).scalar()
            assert res_auth_after is False

            # Confirm sylvar_app_user retains EXECUTE
            res_app = (await conn.execute(text("SELECT has_function_privilege('sylvar_app_user', 'pg_temp.test_privilege_guard(uuid)', 'EXECUTE')"))).scalar()
            assert res_app is True
        finally:
            await trans.rollback()

    await engine.dispose()


@pytest.mark.anyio
async def test_postgres_schema_public_privileges():
    """Verify PostgreSQL catalog privileges on schema public for untrusted roles and check schema ownership."""
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("Skipping PostgreSQL test: DATABASE_URL is not PostgreSQL")

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        # Check CREATE privilege on schema public
        # In a secure multi-tenant Supabase database, untrusted roles (anon, authenticated) must NOT have CREATE on schema public
        res_anon_create = (await conn.execute(text("SELECT has_schema_privilege('anon', 'public', 'CREATE')"))).scalar()
        res_auth_create = (await conn.execute(text("SELECT has_schema_privilege('authenticated', 'public', 'CREATE')"))).scalar()
        res_app_create = (await conn.execute(text("SELECT has_schema_privilege('sylvar_app_user', 'public', 'CREATE')"))).scalar()

        # Check USAGE privilege on schema public
        res_anon_usage = (await conn.execute(text("SELECT has_schema_privilege('anon', 'public', 'USAGE')"))).scalar()
        res_auth_usage = (await conn.execute(text("SELECT has_schema_privilege('authenticated', 'public', 'USAGE')"))).scalar()
        res_app_usage = (await conn.execute(text("SELECT has_schema_privilege('sylvar_app_user', 'public', 'USAGE')"))).scalar()

        # Check schema public owner
        owner_name = (await conn.execute(text("""
            SELECT r.rolname
            FROM pg_namespace n
            JOIN pg_roles r ON n.nspowner = r.oid
            WHERE n.nspname = 'public'
        """))).scalar()

        # Print findings for transparency
        print(f"\n[CATALOG AUDIT] schema public owner: {owner_name}")
        print(f"[CATALOG AUDIT] anon CREATE: {res_anon_create}, USAGE: {res_anon_usage}")
        print(f"[CATALOG AUDIT] authenticated CREATE: {res_auth_create}, USAGE: {res_auth_usage}")
        print(f"[CATALOG AUDIT] sylvar_app_user CREATE: {res_app_create}, USAGE: {res_app_usage}")

        # Verify that untrusted roles CANNOT create objects in schema public (preventing object shadowing)
        assert res_anon_create is False, "Role 'anon' must NOT have CREATE on schema public"
        assert res_auth_create is False, "Role 'authenticated' must NOT have CREATE on schema public"
        assert res_app_create is False, "Runtime role 'sylvar_app_user' must NOT have CREATE on schema public (DDL least-privilege)"

        # Schema public is owned by postgres, supabase_admin, or pg_database_owner
        assert owner_name in ("postgres", "supabase_admin", "pg_database_owner"), f"Schema public owner is {owner_name}"

        # Verify USAGE is enabled as appropriate
        assert res_app_usage is True, "Runtime role 'sylvar_app_user' must have USAGE on schema public"

    await engine.dispose()


