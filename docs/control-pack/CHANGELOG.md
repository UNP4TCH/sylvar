# CHANGELOG.md — Engineering Modification Log
All notable changes to the SYLVAR project specifications and codebase are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — Round 2 (Phase 1 Verification & Baseline)
### Verified (2026-11-05)
- Git repository initialized at root with runtime pins (`.python-version` 3.14.7, `.nvmrc` v24.19.0).
- Backend environment initialized (`.venv`), dependencies installed, and locked in `backend/requirements.lock.txt` (`PyJWT==2.15.1`).
- Backend test suite verified under `pytest -v`: 69 of 69 tests passed in 1.64s.
- Backend static checks verified: `mypy app` (strict mode, 16 source files, 0 errors) and `ruff check .` (0 errors).
- Backend live liveness verified: `uvicorn app.main:app` health probe `GET /api/v1/health` returns HTTP 200 `{"status": "alive"}` with unconfigured auth warning logged.
- Frontend environment initialized (`node_modules`), dependencies locked in `frontend/package-lock.json`.
- Frontend static check verified: `npm run type-check` (`tsc --noEmit`) 0 errors.
- Frontend test suite verified under Vitest: 44 of 44 tests passed across 8 test suites.
- Frontend production build verified: `npm run build` succeeds (dist assets generated in 2.43s).

### Fixed
- Fixed mypy strict type narrowing error for `jwt_audience` in `app/core/security/config.py:109`.
- Cleaned unused `uuid` import and normalized dict literals in backend test helpers; configured `[tool.ruff.lint] ignore = ["B008"]` for FastAPI `Depends`.
- Fixed `.gitignore` to un-mask `.env.frontend.example` and ignore `.mypy_cache/`.

---

## [1.0.0] — 2026-11-02
### Added
- Initial AI Agent Control Pack generated; corrected control-pack revision adds missing development, reference and template documents.
- Master Product Requirements Document (`product/MASTER_PRD.md`) consolidating all 32 required sections.
- Comprehensive architectural specifications: `ARCHITECTURE.md`, `DATABASE_DESIGN.md`, `API_DESIGN.md`, `AI_INTELLIGENCE.md`, `SECURITY_ARCHITECTURE.md`.
- Added implementation guides: `development/IMPLEMENTATION_PLAN.md`, `PHASE_GUIDE.md`, `CODING_STANDARDS.md`, `TESTING_STRATEGY.md`, `ERROR_HANDLING.md`, `DEPLOYMENT.md`.
- Full traceability and decision registers: `REQUIREMENT_TRACEABILITY.md`, `DECISION_REGISTER.md`, `OPEN_QUESTIONS.md`, `ENVIRONMENT_SETUP.md`.

### Fixed
- Formalized exact 3-role permission model (`WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`), removing all legacy mentions of "Reviewer".
- Corrected linear-light alpha compositing equations to use explicit, reliable mathematical formulas.
- Removed all invalid audit lifecycle enums (eliminated `QUEUED`, standardized on `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `INTERRUPTED`).
- Reclassified performance metrics as empirical engineering benchmarks rather than unverified guarantees.
- Aligned database access model with direct PostgreSQL connection via SQLAlchemy Async + asyncpg under least-privilege `sylvar_app_user` without `BYPASSRLS`.
- Removed `SUPABASE_SERVICE_ROLE_KEY` from required backend runtime credentials.

### Corrected in control-pack validation
- Removed Workspace Admin client-assignment bypass from the PRD/API contract.
- Reserved human review decisions for assigned Brand Managers.
- Reclassified table inventory as conceptual; complete schema and RLS are explicit blocking gates.
- Documented process-restart limitations of in-process audit execution.
- Replaced unverified model IDs and performance guarantees with implementation-time verification/benchmark requirements.
- Added missing development, references and templates directories.


## 2026-11-04 — Phase 1 implementation (unverified)
Added: monorepo skeleton; FastAPI app factory, settings, RFC 9457 errors (`ProblemException`), `GET /api/v1/health`;
framework-free JWT verification (`core/security/*`: config, JWKS provider with TTL/cooldown/kid lookup, asymmetric-only verifier);
`modules/auth/dependencies.py` (`get_current_user`, 401 / fail-closed 503); React/Vite/Tailwind client with env validation,
API client, Supabase auth store and sign-in/up form; backend + frontend tests; `.env.example` files.
Fixed during review: comma-separated `ALLOWED_ORIGINS` (JSON-list parsing would have crashed startup); RS/EC key-type mismatch
raised an unhandled TypeError (would have been HTTP 500) — now TOKEN_INVALID.
Not done by design: DB, migrations, RLS, workspaces, roles, `/auth/session` (OPEN_QUESTIONS #5), `/system/status`.

## 2026-11-04 — Phase 1 second pass (unverified)
Added: `lib/authedApi.ts` (token from Supabase client, single refresh-and-retry on 401), `AuthGate`, `ApiStatus` (public `/health` probe), sign-up notice, thrown-error handling in the auth store; backend nbf/aud-list tests, startup-failure tests.
Changed: JWKS cache TTL default 600s -> 86400s to match SECURITY_ARCHITECTURE (24h); decode errors of any library type now map to 401 (never 500); removed invented 8-char password minimum from the form (server policy applies); tests no longer read a real `.env`.
ADR-009 approved as policy.

## 2026-11-04 — Phase 1 focused review pass (unverified)
Backend: partial auth config now fails fast (blank/placeholder = unset); startup logs auth state; test helper builds RFC 7518 fixed-length EC JWKs (root cause of earlier flaky run, see PHASE1_STATUS); +8 JWKS tests (single-flight, preserved cache on failed/invalid refresh, TTL/revocation behaviour, leading-zero EC regression).
Frontend: auth store `init()` now subscribes first and returns its cleanup synchronously; stale `getSession` results ignored (Strict-Mode-safe); `authedApi` single-flight refresh; +8 tests.
Docs: ADR-009 clarification C1; TEST_INVENTORY.md; PHASE1_HANDOFF.md.

## 2026-11-04 — Decisions recorded and test-figure reconciliation
Decisions: ADR-009 clarification C1 APPROVED; ADR-009 clarification C2 (JWKS timing defaults) APPROVED; ADR-010 (keep supabase-js localStorage session persistence for MVP) APPROVED. XSS consideration and rotation/revocation trade-offs documented in `docs/SECURITY_NOTES.md`.
Documentation: new `docs/TEST_EVIDENCE.md` is the single source for test figures. Corrected an error: `test_jwks_http.py` has 6 tests (not 5), so backend written = 69 (not 68) and never-executed = 26 (not 25). Replaced imprecise "45 consecutive"/"24 runs" tallies with a batch ledger; headline figure is 100/100 clean runner executions of the 43 executed tests, measured at the final code state. Earlier changelog/test counts in this file are historical.
No code changes. Phase 2 not started. Phase 1 not complete.
