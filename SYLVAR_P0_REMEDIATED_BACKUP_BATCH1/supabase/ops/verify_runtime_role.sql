-- Run after connecting with the backend DATABASE_URL credentials.
SELECT current_user AS runtime_role,
       rolsuper AS is_superuser,
       rolbypassrls AS bypasses_rls,
       rolcreatedb AS can_create_database,
       rolcreaterole AS can_create_roles
FROM pg_roles
WHERE rolname = current_user;

-- Expected: current_user = sylvar_app_user and all four privilege flags = false.
