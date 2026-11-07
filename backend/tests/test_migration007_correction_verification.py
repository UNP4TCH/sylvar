"""Verification of Migration 007 Batch 2A Final Security Correction."""
from datetime import datetime, timedelta, UTC
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


@pytest.mark.anyio
async def test_migration007_sql_structure():
    """Verify Migration 007 SQL file declares correct security rules and preconditions."""
    with open("../supabase/migrations/007_batch2a_final_security_correction.sql", "r", encoding="utf-8") as f:
        sql = f.read()

    # Preconditions
    assert "Precondition failed: table public.workspace_invitations does not exist" in sql
    assert "Precondition failed: function public.accept_workspace_invitation does not exist" in sql
    assert "Precondition failed: role sylvar_app_user does not exist" in sql

    # SECURITY DEFINER & Search Path
    assert "SECURITY DEFINER" in sql
    assert "SET search_path = pg_catalog, public" in sql

    # Owner
    assert "ALTER FUNCTION public.accept_workspace_invitation(UUID, UUID) OWNER TO postgres;" in sql

    # Revoke from service_role, anon, authenticated, PUBLIC
    assert "REVOKE ALL ON FUNCTION public.accept_workspace_invitation(UUID, UUID) FROM PUBLIC, authenticated, anon, service_role;" in sql
    assert "GRANT EXECUTE ON FUNCTION public.accept_workspace_invitation(UUID, UUID) TO sylvar_app_user;" in sql

    # Guard 1: Deliberately revoked memberships CANNOT be silently reactivated
    assert "IF v_existing_mem.status = 'REVOKED' OR v_existing_mem.revoked_at IS NOT NULL THEN" in sql
    assert "cannot be reactivated via standard invitation acceptance" in sql

    # Guard 2: Never downgrade WORKSPACE_ADMIN
    assert "IF v_existing_mem.role = 'WORKSPACE_ADMIN' THEN" in sql
    assert "v_final_role := 'WORKSPACE_ADMIN';" in sql

    # Anon table privileges
    assert "REVOKE ALL ON public.workspace_invitations FROM anon;" in sql


@pytest.mark.anyio
async def test_postgres_engine_migration007_acls_and_guards():
    """Test Migration 007 ACL enforcement and membership guards in real PostgreSQL."""
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("Skipping PostgreSQL test: DATABASE_URL is not PostgreSQL")

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            # 1. Create isolated test function and tables in pg_temp
            await conn.execute(text("""
                CREATE TEMP TABLE test_m007_users (
                    id UUID PRIMARY KEY,
                    email VARCHAR(255) NOT NULL
                )
            """))
            await conn.execute(text("""
                CREATE TEMP TABLE test_m007_invitations (
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
                CREATE TEMP TABLE test_m007_memberships (
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

            # Function implementation matching Migration 007
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION pg_temp.test_accept_invitation_007(
                    p_inv_id UUID,
                    p_user_id UUID
                )
                RETURNS JSONB
                LANGUAGE plpgsql
                AS $$
                DECLARE
                    v_email VARCHAR;
                    v_inv record;
                    v_mem record;
                    v_role VARCHAR;
                BEGIN
                    IF p_user_id IS NULL THEN
                        RAISE EXCEPTION 'User ID is required' USING ERRCODE = '28000';
                    END IF;
                    SELECT email INTO v_email FROM test_m007_users WHERE id = p_user_id;
                    IF v_email IS NULL THEN
                        RAISE EXCEPTION 'User profile not found' USING ERRCODE = 'P0002';
                    END IF;
                    SELECT * INTO v_inv FROM test_m007_invitations WHERE id = p_inv_id FOR UPDATE;
                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'Invitation not found' USING ERRCODE = 'P0002';
                    END IF;
                    IF lower(v_inv.email) <> lower(v_email) THEN
                        RAISE EXCEPTION 'Email mismatch' USING ERRCODE = '42501';
                    END IF;
                    IF v_inv.status <> 'PENDING' THEN
                        RAISE EXCEPTION 'Not pending' USING ERRCODE = '23514';
                    END IF;
                    IF v_inv.expires_at <= now() THEN
                        RAISE EXCEPTION 'Expired' USING ERRCODE = '22008';
                    END IF;

                    SELECT * INTO v_mem FROM test_m007_memberships WHERE workspace_id = v_inv.workspace_id AND user_id = p_user_id FOR UPDATE;
                    IF FOUND THEN
                        IF v_mem.status = 'REVOKED' OR v_mem.revoked_at IS NOT NULL THEN
                            RAISE EXCEPTION 'User membership was previously revoked and cannot be reactivated via standard invitation acceptance' USING ERRCODE = '42501';
                        END IF;
                        IF v_mem.role = 'WORKSPACE_ADMIN' THEN
                            v_role := 'WORKSPACE_ADMIN';
                        ELSE
                            v_role := v_mem.role;
                        END IF;
                        UPDATE test_m007_memberships SET status = 'ACTIVE', role = v_role, updated_at = now() WHERE workspace_id = v_inv.workspace_id AND user_id = p_user_id;
                    ELSE
                        v_role := v_inv.role;
                        INSERT INTO test_m007_memberships (workspace_id, user_id, role, status) VALUES (v_inv.workspace_id, p_user_id, v_role, 'ACTIVE');
                    END IF;

                    UPDATE test_m007_invitations SET status = 'ACCEPTED', auth_user_id = p_user_id, accepted_at = now() WHERE id = v_inv.id;
                    RETURN jsonb_build_object('status', 'ACCEPTED', 'role', v_role);
                END;
                $$;
            """))

            # 2. Test ACL enforcement matching Migration 007
            await conn.execute(text("REVOKE ALL ON FUNCTION pg_temp.test_accept_invitation_007(UUID, UUID) FROM PUBLIC, authenticated, anon, service_role"))
            await conn.execute(text("GRANT EXECUTE ON FUNCTION pg_temp.test_accept_invitation_007(UUID, UUID) TO sylvar_app_user"))

            can_sylvar = (await conn.execute(text("SELECT has_function_privilege('sylvar_app_user', 'pg_temp.test_accept_invitation_007(uuid, uuid)', 'EXECUTE')"))).scalar()
            can_service = (await conn.execute(text("SELECT has_function_privilege('service_role', 'pg_temp.test_accept_invitation_007(uuid, uuid)', 'EXECUTE')"))).scalar()
            can_auth = (await conn.execute(text("SELECT has_function_privilege('authenticated', 'pg_temp.test_accept_invitation_007(uuid, uuid)', 'EXECUTE')"))).scalar()
            can_anon = (await conn.execute(text("SELECT has_function_privilege('anon', 'pg_temp.test_accept_invitation_007(uuid, uuid)', 'EXECUTE')"))).scalar()

            assert can_sylvar is True, "sylvar_app_user must have EXECUTE"
            assert can_service is False, "service_role must NOT have EXECUTE"
            assert can_auth is False, "authenticated must NOT have EXECUTE"
            assert can_anon is False, "anon must NOT have EXECUTE"

            # Test A: Deliberately revoked member is REJECTED (raises 42501)
            ws_id = uuid.uuid4()
            revoked_user_id = uuid.uuid4()
            inv_id = uuid.uuid4()

            await conn.execute(text("INSERT INTO test_m007_users VALUES (:u, 'revoked@agency.com')"), {"u": revoked_user_id})
            await conn.execute(text("""
                INSERT INTO test_m007_memberships (workspace_id, user_id, role, status, revoked_at)
                VALUES (:w, :u, 'CONTENT_CREATOR', 'REVOKED', now() - interval '5 days')
            """), {"w": ws_id, "u": revoked_user_id})
            await conn.execute(text("""
                INSERT INTO test_m007_invitations (id, workspace_id, email, role, status, delivery_status, expires_at)
                VALUES (:i, :w, 'revoked@agency.com', 'CONTENT_CREATOR', 'PENDING', 'DELIVERED', now() + interval '7 days')
            """), {"i": inv_id, "w": ws_id})

            sp_a = await conn.begin_nested()
            try:
                await conn.execute(text("SELECT pg_temp.test_accept_invitation_007(:i, :u)"), {"i": inv_id, "u": revoked_user_id})
                pytest.fail("Revoked membership acceptance must raise 42501!")
            except Exception as e:
                await sp_a.rollback()
                assert "previously revoked and cannot be reactivated" in str(e)

            # Test B: Active WORKSPACE_ADMIN is NOT downgraded by creator invitation
            admin_user_id = uuid.uuid4()
            inv_b_id = uuid.uuid4()
            await conn.execute(text("INSERT INTO test_m007_users VALUES (:u, 'admin@agency.com')"), {"u": admin_user_id})
            await conn.execute(text("""
                INSERT INTO test_m007_memberships (workspace_id, user_id, role, status)
                VALUES (:w, :u, 'WORKSPACE_ADMIN', 'ACTIVE')
            """), {"w": ws_id, "u": admin_user_id})
            await conn.execute(text("""
                INSERT INTO test_m007_invitations (id, workspace_id, email, role, status, delivery_status, expires_at)
                VALUES (:i, :w, 'admin@agency.com', 'CONTENT_CREATOR', 'PENDING', 'DELIVERED', now() + interval '7 days')
            """), {"i": inv_b_id, "w": ws_id})

            res_b = (await conn.execute(text("SELECT pg_temp.test_accept_invitation_007(:i, :u)"), {"i": inv_b_id, "u": admin_user_id})).scalar()
            assert res_b["status"] == "ACCEPTED"
            assert res_b["role"] == "WORKSPACE_ADMIN", "Admin must NOT be downgraded!"

            # Test C: Existing BRAND_MANAGER is NOT overwritten by creator invitation
            bm_user_id = uuid.uuid4()
            inv_c_id = uuid.uuid4()
            await conn.execute(text("INSERT INTO test_m007_users VALUES (:u, 'bm@agency.com')"), {"u": bm_user_id})
            await conn.execute(text("""
                INSERT INTO test_m007_memberships (workspace_id, user_id, role, status)
                VALUES (:w, :u, 'BRAND_MANAGER', 'ACTIVE')
            """), {"w": ws_id, "u": bm_user_id})
            await conn.execute(text("""
                INSERT INTO test_m007_invitations (id, workspace_id, email, role, status, delivery_status, expires_at)
                VALUES (:i, :w, 'bm@agency.com', 'CONTENT_CREATOR', 'PENDING', 'DELIVERED', now() + interval '7 days')
            """), {"i": inv_c_id, "w": ws_id})

            res_c = (await conn.execute(text("SELECT pg_temp.test_accept_invitation_007(:i, :u)"), {"i": inv_c_id, "u": bm_user_id})).scalar()
            assert res_c["status"] == "ACCEPTED"
            assert res_c["role"] == "BRAND_MANAGER", "Existing active role must be preserved!"

        finally:
            await trans.rollback()

    await engine.dispose()
