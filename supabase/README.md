Migrations are intentionally empty. Schema DDL/RLS is blocked by OPEN_QUESTIONS #1-#2 (Phase 2).


## Backend runtime database role

The FastAPI backend must connect using the dedicated `sylvar_app_user` role, not
`postgres`, `service_role`, `anon`, or `authenticated`. After applying all schema
migrations, run `supabase/ops/bootstrap_runtime_role.sql` as the project database
owner. Configure the role password and `DATABASE_URL` through your deployment
secret manager. Verify `rolsuper = false` and `rolbypassrls = false` before launch.
The provisioning script is intentionally separate from migrations because hosted
Supabase migration roles may not have permission to create database roles.
