# SYLVAR — P0 Remediation Report

**Prepared:** 5 November 2026  
**Base:** the uploaded `sylvar.zip` snapshot and its accompanying `FINAL_INDEPENDENT_AUDIT.md`  
**Scope:** P0 source remediation only. No live Supabase, Gemini, or production deployment was accessed or modified.

## Result

The source-level P0 changes below are applied in this working copy. **Do not treat this as production-ready or externally verified.** PostgreSQL RLS behavior, actual runtime-role grants, Supabase JWT behavior, live Gemini behavior, and the browser golden path still require execution in the target environment.

## Changes applied

### C-01 / C-02 — PostgreSQL tenant context and workspace bootstrap

- Replaced parameterized `SET LOCAL` with bind-safe `SELECT set_config(:setting_name, :setting_value, true)`.
- Tenant context setup now writes all three settings on every call; `None` explicitly clears the previous scope with an empty transaction-local value.
- Context-setting errors fail closed with `503 TENANT_CONTEXT_UNAVAILABLE`; they are not swallowed.
- Removed the `auth.uid()` fallback from `current_app_user_id()`. The dedicated backend DB role uses only the transaction-local user ID set by the API after JWT verification. This avoids relying on Supabase PostgREST JWT claims that are not present on the separate backend database connection.
- Workspace creation preallocates the workspace UUID, sets the verified user/workspace context, inserts the workspace, and creates the creator's admin membership in the same transaction. It does not bypass RLS.

### C-03 — runtime database role

- Added `supabase/ops/bootstrap_runtime_role.sql` to create/configure `sylvar_app_user` with `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`, and explicit required grants.
- Added `supabase/ops/verify_runtime_role.sql` to inspect the actual connected role and its privilege flags.
- The role password must be set securely by the operator; do not commit it or paste it into chat. Run default-privilege setup as the role that owns/creates future migration objects.

### C-05 — audit engine applicability

- Text engines fail when required text content is missing.
- Visual checks are explicitly recorded as `NOT_APPLICABLE` for the text-only MVP; that status is not represented as a visual PASS.
- IMAGE and HYBRID asset creation/audit are rejected until a real upload, storage, and visual-audit path is implemented.
- A factual engine that is offline, unavailable, or errors causes the overall audit to fail closed rather than producing a compliance PASS.

### C-06 — factual verification completeness

- Gemini findings are reconciled against source sentences. A missing/empty model findings list cannot silently imply that the draft was verified.
- Coverage requires the complete normalized source sentence to be present in an evaluated claim; a short substring such as a single word is not sufficient coverage.
- Missing approved facts produce critical UNVERIFIED findings and a FAIL result.
- Empty draft input fails closed.
- Offline deterministic checks remain advisory and cannot authorize a compliance PASS.
- Gemini model defaults are now explicit `VERIFY_BEFORE_SELECTING` placeholders. Configure `GEMINI_MODEL` only after checking current model availability and structured-output support in the target Google AI account.

### Production database configuration

- Production startup rejects missing/placeholder `DATABASE_URL` and rejects non-PostgreSQL async driver URLs.
- SQLite remains an explicit development/test convenience only.

## Files changed in this pass

- `backend/app/modules/auth/pipeline.py`
- `supabase/migrations/001_initial_schema.sql`
- `backend/app/modules/engine_factual/gemini_verifier.py`
- `backend/app/core/config.py`
- `backend/app/modules/engine_factual/verifier.py`
- `backend/app/modules/documents/extractor.py`
- `backend/app/modules/documents/gemini_extractor.py`
- `backend/tests/test_p0_hardening.py`

The working copy also contains the earlier source remediation and operational files described above, including workspace/audit route changes, `backend/app/db/session.py`, `backend/app/main.py`, `backend/app/modules/orchestrator/runner.py`, and the two `supabase/ops` SQL scripts.

## Verification performed in this environment

| Check | Result | Evidence / limitation |
|---|---|---|
| Python compileall | **PASS** | `backend/app` and `backend/tests` compiled successfully. |
| Tenant context parameterization | **PASS** | Manual smoke check confirmed three `set_config` calls and explicit clearing of unset workspace/client values. |
| Tenant context fail-closed behavior | **PASS** | Simulated PostgreSQL execution error raised `503 TENANT_CONTEXT_UNAVAILABLE`. |
| Production DB guard | **PASS** | Missing URL and SQLite production URL rejected; PostgreSQL async URL accepted by validator. |
| Factual omission handling | **PASS** | Stubbed SDK smoke test: empty findings, short partial claim, and no approved facts all failed closed. No network request was made. |
| Backend pytest suite | **BLOCKED / NOT RUN** | Test collection requires `aiosqlite`, which is absent; package installation is unavailable in this environment. |
| Ruff / mypy | **NOT RUN** | Tools are not installed in this environment. |
| Frontend tests / typecheck / build | **NOT RUN** | Frontend dependency installation was not available in this environment. |
| PostgreSQL migrations and RLS | **NOT RUN** | No PostgreSQL server or Supabase credentials are available here. |
| Runtime-role grants | **NOT RUN** | SQL scripts are supplied; they must be run and verified in the target project. |
| Live Gemini | **NOT RUN** | No API credential or live model check was available. |
| Browser golden path | **NOT RUN** | No running integrated deployment or browser test environment was available. |

## Operator gates before external integration

1. Apply migrations to a disposable PostgreSQL database first.
2. Run `supabase/ops/bootstrap_runtime_role.sql` as the project database owner; set the role password using the provider's secret UI or a secure interactive session.
3. Configure `DATABASE_URL` to use `sylvar_app_user`; run `verify_runtime_role.sql` and confirm `rolsuper=false`, `rolbypassrls=false`, `rolcreatedb=false`, and `rolcreaterole=false`.
4. Execute two-tenant RLS integration tests using the actual runtime role. SQLite tests cannot establish RLS correctness.
5. Install the locked backend/frontend dependencies in the supported local environment and run the complete test, lint, typecheck, and build suites.
6. Configure a currently supported Gemini model and run live tests for empty findings, omitted claims, malformed JSON, provider timeout, and prompt injection.
7. Complete the browser golden path: sign in → create workspace → create client → assign user → upload/approve guidelines → create TEXT asset → audit → review → decision.

## Explicitly out of scope / remaining findings

- Audit execution is still synchronous; no durable worker/restart recovery was added.
- IMAGE/HYBRID workflows are disabled, not implemented.
- Review decision concurrency and certificate authenticity/immutability remain P1 work.
- Invitation email-verification/reconciliation hardening remains P1 work.
- Upload streaming limits/parser hardening, alpha compositing, Unicode offset preservation, and exact-offset remediation remain P1 work.
- Health endpoint is still liveness-only; deployment readiness/observability remains operational work.

**Status:** P0 source remediation applied in this archive; external integration remains blocked pending real PostgreSQL/RLS, provider, and end-to-end verification.
