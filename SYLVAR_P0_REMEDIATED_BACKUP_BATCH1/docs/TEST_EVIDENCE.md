# Test evidence ledger (single source of truth for all test figures)
Measured 2026-11-05 after completing Stages 1–5 Pre-Integration Technical Remediation (resolving all 8 Critical and 16 Major findings).

## 2026-11-05 Pre-Integration Remediation & Full Verification Suite (Phases 1–5)
Measured on Windows 11 with Python 3.14.7, Node v24.19.0, npm 11.17.0.

| Check | Target | Result | Details |
|---|---|---|---|
| Backend Test Suite | `pytest backend/tests` | **101 of 101 PASSED** | 8 auth_dependency, 3 health, 6 jwks_http, 34 jwt_verifier, 9 security_config, 9 settings, 5 phase2_multi_tenancy, 5 phase3_memory, 4 phase4_audit, 3 phase5_review, 4 gemini_factual, 2 gemini_extractor, 1 rate_limiter, 8 test_remediation_suite. Zero failures. |
| Remediation Regression Suite | `pytest tests/test_remediation_suite.py` | **8 of 8 PASSED** | Dedicated test suite verifying C-01..C-08 and M-01..M-16: invitation identity sync (M-01), engine failure crash prevention (C-05), Gemini fail-closed error handling (C-06), citation verification (M-10), Unicode NFC boundary matching (M-11), review binding & double-decision prevention (C-07, C-08), advisory acknowledgment validation (M-09), transparent alpha filtering (M-04), PDF page limit (M-13). |
| Backend Type Checking | `mypy app` | **PASSED (0 errors)** | 48 source files checked with `strict = true`. |
| Backend Linting | `ruff check .` | **PASSED (0 errors)** | Zero lint errors or unhandled warnings across all modules. |
| Backend Lockfile | `requirements.lock.txt` | **LOCKED** | Includes `google-genai>=2.3.0` and `slowapi>=0.1.9`. |
| Backend Health Probe | Live uvicorn server | **HTTP 200 {"status":"alive"}** | Verified via loopback request; returns `{"status":"alive"}` unauthenticated. |
| Frontend Type Checking | `npm run type-check` | **PASSED (0 errors)** | `tsc --noEmit` across all components, store, lib, and test suites. |
| Frontend Test Suite | `npm test` (vitest) | **46 of 46 PASSED** | 8 test files: env (3), api (5), authedApi (10), authStore (14), ApiStatus (3), AuthGate (5), AuthForm (4), App (2). |
| Frontend Production Build | `npm run build` | **PASSED** | `tsc --noEmit && vite build` completed in 4.29s (`dist/index.html`, `dist/assets/*`). |
| Frontend Lockfile | `package-lock.json` | **LOCKED** | All packages clean and locked. |

---

## Historical Phase 1 verification (2026-11-04 authoring baseline)
- 69 of 69 backend tests passed in baseline Phase 1.
- 44 of 44 frontend Vitest tests passed in baseline Phase 1.
