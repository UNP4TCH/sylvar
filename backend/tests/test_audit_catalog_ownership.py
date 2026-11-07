"""Direct verification of PostgreSQL function ownership, prosecdef, and catalog ACLs."""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


@pytest.mark.anyio
async def test_audit_postgres_function_ownership_and_privileges():
    """Verify owner, prosecdef, proacl, execute privileges, and ALTER/DROP restrictions."""
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("Skipping PostgreSQL test: DATABASE_URL is not PostgreSQL")

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            print("\n" + "=" * 60)
            print("1. LIVE SCHEMA PUBLIC PRIVILEGES:")
            print("=" * 60)
            for r in ["postgres", "sylvar_app_user", "authenticated", "anon"]:
                can_create = (await conn.execute(text(f"SELECT has_schema_privilege('{r}', 'public', 'CREATE')"))).scalar()
                can_usage = (await conn.execute(text(f"SELECT has_schema_privilege('{r}', 'public', 'USAGE')"))).scalar()
                print(f"Role {r:17} | can_create: {str(can_create):5} | can_usage: {str(can_usage):5}")

            print("\n" + "=" * 60)
            print("2. EXISTING FUNCTIONS IN SCHEMA PUBLIC (CREATED BY MIGRATIONS):")
            print("=" * 60)
            q = text("""
                SELECT 
                    p.proname,
                    pg_get_userbyid(p.proowner) AS owner,
                    p.prosecdef,
                    p.proacl
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname = 'public';
            """)
            rows = (await conn.execute(q)).fetchall()
            for row in rows:
                print(f"Function: {row[0]:32} | Owner: {row[1]:10} | SecDef: {str(row[2]):5} | ACL: {row[3]}")
                assert row[1] in ("postgres", "supabase_admin"), f"Function owner must be postgres or supabase_admin, got {row[1]}"

            print("\n" + "=" * 60)
            print("3. SIMULATING MIGRATION 006 FUNCTION CREATION & ACL ASSIGNMENT:")
            print("=" * 60)
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION pg_temp.accept_workspace_invitation_audit(
                    p_invitation_id UUID,
                    p_user_id UUID
                )
                RETURNS JSONB
                LANGUAGE plpgsql
                SECURITY DEFINER
                SET search_path = pg_catalog, public
                AS $$
                BEGIN
                    RETURN jsonb_build_object('status', 'ACCEPTED');
                END;
                $$;
            """))

            await conn.execute(text("""
                REVOKE ALL ON FUNCTION pg_temp.accept_workspace_invitation_audit(UUID, UUID) FROM PUBLIC, authenticated;
            """))
            await conn.execute(text("""
                GRANT EXECUTE ON FUNCTION pg_temp.accept_workspace_invitation_audit(UUID, UUID) TO sylvar_app_user;
            """))

            q_audit = text("""
                SELECT 
                    p.proname,
                    pg_get_userbyid(p.proowner) AS owner,
                    p.prosecdef,
                    p.proacl
                FROM pg_proc p
                WHERE p.proname = 'accept_workspace_invitation_audit';
            """)
            audit_proc = (await conn.execute(q_audit)).fetchone()
            print(f"Function:  {audit_proc[0]}")
            print(f"Owner:     {audit_proc[1]}")
            print(f"prosecdef: {audit_proc[2]}")
            print(f"proacl:    {audit_proc[3]}")

            assert audit_proc[2] is True, "prosecdef must be True (SECURITY DEFINER)"

            print("\n" + "=" * 60)
            print("4. EFFECTIVE EXECUTE PRIVILEGES:")
            print("=" * 60)
            privs = {}
            for role in ["postgres", "sylvar_app_user", "authenticated", "anon"]:
                has_exec = (await conn.execute(text(f"""
                    SELECT has_function_privilege('{role}', 'pg_temp.accept_workspace_invitation_audit(uuid, uuid)', 'EXECUTE')
                """))).scalar()
                privs[role] = has_exec
                print(f"Role {role:17} | EXECUTE privilege: {has_exec}")

            assert privs["sylvar_app_user"] is True, "sylvar_app_user must have EXECUTE"
            assert privs["authenticated"] is False, "authenticated must NOT have EXECUTE"
            assert privs["anon"] is False, "anon must NOT have EXECUTE"

            print("\n" + "=" * 60)
            print("5. VERIFYING ALTER, DROP, AND REPLACE IMMUTABILITY:")
            print("=" * 60)
            # Try to DROP an existing public function owned by postgres
            sp1 = await conn.begin_nested()
            try:
                await conn.execute(text("DROP FUNCTION public.current_app_user_id();"))
                pytest.fail("sylvar_app_user unexpectedly dropped a postgres-owned function!")
            except Exception as exc:
                await sp1.rollback()
                print(f"DROP FUNCTION blocked: {exc.orig if hasattr(exc, 'orig') else exc}")

            # Try to ALTER OWNER of a postgres-owned function
            sp2 = await conn.begin_nested()
            try:
                await conn.execute(text("ALTER FUNCTION public.current_app_user_id() OWNER TO sylvar_app_user;"))
                pytest.fail("sylvar_app_user unexpectedly altered owner of a postgres-owned function!")
            except Exception as exc:
                await sp2.rollback()
                print(f"ALTER FUNCTION OWNER blocked: {exc.orig if hasattr(exc, 'orig') else exc}")

            # Try to CREATE OR REPLACE a function in public
            sp3 = await conn.begin_nested()
            try:
                await conn.execute(text("""
                    CREATE OR REPLACE FUNCTION public.current_app_user_id()
                    RETURNS UUID LANGUAGE sql AS $$ SELECT NULL::UUID; $$;
                """))
                pytest.fail("sylvar_app_user unexpectedly replaced a public function!")
            except Exception as exc:
                await sp3.rollback()
                print(f"CREATE OR REPLACE in public blocked: {exc.orig if hasattr(exc, 'orig') else exc}")

        finally:
            await trans.rollback()

    await engine.dispose()


@pytest.mark.anyio
async def test_evaluate_dedicated_definer_role():
    """Evaluate whether a dedicated NOLOGIN role can own accept_workspace_invitation."""
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("Skipping PostgreSQL test: DATABASE_URL is not PostgreSQL")

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        print("\n" + "=" * 60)
        print("EVALUATING LIVE POSTGRESQL ROLES & BYPASSRLS CAPABILITIES:")
        print("=" * 60)
        res = (await conn.execute(text("""
            SELECT rolname, rolsuper, rolbypassrls, rolcanlogin, rolinherit
            FROM pg_roles 
            WHERE rolname IN ('postgres', 'sylvar_app_user', 'authenticated', 'anon', 'supabase_admin')
            ORDER BY rolname;
        """))).fetchall()
        for r in res:
            print(f"Role: {r[0]:17} | Super: {str(r[1]):5} | BypassRLS: {str(r[2]):5} | CanLogin: {str(r[3]):5} | Inherit: {str(r[4]):5}")

        # Check existing table owners in public schema
        print("\n" + "=" * 60)
        print("SCHEMA PUBLIC TABLE OWNERS:")
        print("=" * 60)
        tables = (await conn.execute(text("""
            SELECT tablename, tableowner, rowsecurity
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """))).fetchall()
        for t in tables[:8]:
            print(f"Table: {t[0]:30} | Owner: {t[1]:15} | RLS: {t[2]}")

    await engine.dispose()


