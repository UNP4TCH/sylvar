-- Run once as the Supabase database owner / project administrator.
-- Set a strong password for sylvar_app_user through the provider's secret UI or
-- an interactive psql session; never commit credentials to this repository.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sylvar_app_user') THEN
        EXECUTE 'CREATE ROLE sylvar_app_user LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS';
    END IF;
END
$$;

ALTER ROLE sylvar_app_user
    LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

GRANT USAGE ON SCHEMA public TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sylvar_app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sylvar_app_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO sylvar_app_user;

-- Ensure objects created by the migration owner in future migrations remain usable.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sylvar_app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO sylvar_app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT EXECUTE ON FUNCTIONS TO sylvar_app_user;

-- Verify the security-critical role attributes before using this role.
DO $$
DECLARE role_record RECORD;
BEGIN
    SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
      INTO role_record FROM pg_roles WHERE rolname = 'sylvar_app_user';
    IF role_record.rolsuper OR role_record.rolbypassrls OR role_record.rolcreatedb OR role_record.rolcreaterole THEN
        RAISE EXCEPTION 'sylvar_app_user has excessive privileges';
    END IF;
END
$$;
