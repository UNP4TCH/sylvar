# SECURITY_ARCHITECTURE.md — Security & Defense-in-Depth
**Reference:** Task 5 Security & API Specification v1.6  

---

## 1. Asymmetric Cryptographic Authentication
* Supabase Auth issues JWT access tokens (1h TTL) signed via RS256/ES256.
* FastAPI backend fetches public keys from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` (24h cache TTL).
* Backend independently validates signature, `exp`, `nbf`, `iss` (`{SUPABASE_URL}/auth/v1`), and `aud` (`authenticated`).

## 2. Server-Side 5-Gate Authorization Pipeline
1. **Gate 1:** Cryptographic JWT verification. Extracts `user_id`.
2. **Gate 2:** Workspace membership query (`workspace_memberships`). Asserts `ACTIVE` status.
3. **Gate 3:** Client brand assignment query (`client_memberships`). Asserts `ACTIVE` status.
4. **Gate 4:** RBAC action check (`WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`).
5. **Gate 5:** Parameterized SQL execution with transaction-local context (`SET LOCAL app.current_workspace_id = ...`).

## 3. Database Least-Privilege & RLS Defense-in-Depth
* Runtime application role `sylvar_app_user` lacks `SUPERUSER` and `BYPASSRLS` privileges.
* RLS enabled and forced on all tenant tables. Fails closed if session context is missing.
* Schema migrations run under separate administrative credentials.

## 4. Prompt-Injection Defense & Zero-Action AI Boundaries
* Untrusted content wrapped in `<untrusted_draft>` and `<reference_facts>` tags.
* System instructions mandate treating delimited content strictly as passive data.
* AI outputs validated via Pydantic v2 schemas (`extra = 'forbid'`).
* AI output can never directly mutate database state, activate rules, or approve collateral.


## 5. Authorization Contract Clarification
Client-scoped operations require both active workspace membership and an active explicit client assignment for all roles, including Workspace Admin. Workspace Admin authority is workspace-scoped for provisioning and membership administration; it does not grant ambient client content, document, memory, audit or review access. Only an assigned Brand Manager may approve/reject/request changes or acknowledge advisories.

JWT validation must use the actual project's issuer, audience, allowed algorithms and JWKS metadata; support key rotation and bounded cache refresh. Confirm the exact Supabase JWT signing configuration rather than assuming RS256/ES256 universally. Re-check database membership/assignment on protected requests so revocation takes effect without waiting for JWT expiry.
