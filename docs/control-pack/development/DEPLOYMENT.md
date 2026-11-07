# Deployment Guide

**Targets:** Vercel frontend, Render FastAPI backend, Supabase PostgreSQL/Auth/Storage.

## Environment separation
Maintain separate development/staging/production projects and credentials. Store secrets only in provider secret stores. Frontend receives only public Supabase project URL/anon key as appropriate; never expose database credentials, Gemini keys or service-role secrets.

## Deployment gates
- Pin and verify dependency versions; lock dependencies.
- Run lint, typecheck, unit, integration and security tests.
- Apply reviewed migrations using a separate migration identity, never the runtime role.
- Configure exact CORS origins, HTTPS, health/readiness checks, rate limits and upload limits.
- Configure private storage and short-lived signed URLs.
- Verify database role privileges and RLS with the deployed runtime identity.
- Smoke-test auth, assignment revocation, upload, audit, review and export.
- Document rollback and migration recovery procedures.

Do not deploy a production environment until schema/RLS/API contracts and recovery behavior have passed their gates.
