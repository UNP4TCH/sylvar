# Test inventory (all tests written for Phase 1)
Figures are reconciled in `docs/TEST_EVIDENCE.md` (the single source of truth).
Legend — Executed: ran in authoring sandbox via ad-hoc runner (not pytest). Unrun: never executed anywhere. None is "verified" until you run the real suites.

## Backend (pytest) — 69 tests (reconciled; see `docs/TEST_EVIDENCE.md`)
| File | Tests | Covers | State |
|---|---|---|---|
| `tests/test_jwt_verifier.py` | 34 | valid ES256/RS256; expired/leeway; wrong iss/aud; missing exp/sub/iss/aud; non-UUID sub; tampered signature; same-kid impostor; `none`; HS256 confusion; alg allow-list; key-type/alg mismatch; missing kid; malformed/oversized; nbf; aud list; JWKS: unknown kid, rotation, flood/cooldown, cache, TTL refetch, outage 503, no hammering, recovery, private-key/empty doc, leading-zero EC regression, helper fixed-length, single-flight, preserved cache on failed/invalid refresh, revoked-key-until-TTL | Executed (34/34) |
| `tests/test_security_config.py` | 9 | unconfigured/placeholder = None; partial config raises; derivation; explicit override; https-only (localhost exception); HS*/none rejected; numeric bounds; 24h default TTL | Executed (9/9) |
| `tests/test_auth_dependency.py` | 8 | HTTP: valid token→user_id; missing→401 problem+json+WWW-Authenticate; expired; garbage not echoed; non-Bearer scheme; unconfigured→503; JWKS outage→503; `/health` public | Unrun (needs fastapi, httpx) |
| `tests/test_health.py` | 3 | `/health` body; 404 problem details; CORS rejects unlisted origin | Unrun |
| `tests/test_settings.py` | 9 | origins parsing; wildcard rejected; unconfigured warning; placeholders; partial fails fast; configured logs issuer; default TTL; insecure issuer / HS256 fail at startup | Unrun (needs pydantic, pytest caplog) |
| `tests/test_jwks_http.py` | 6 | JWKS transport (MockTransport): parsed object + configured URL, HTTP error statuses, redirects not followed, non-object JSON, >256KB body, invalid JSON | Unrun (needs httpx) |
Helpers: `tests/jwt_helpers.py` (keys, JWKS fake, clock), `tests/settings_helpers.py` (env-isolated Settings).

## Frontend (Vitest) — 44 tests, all Unrun
| File | Tests | Covers |
|---|---|---|
| `src/lib/env.test.ts` | 3 | complete config, trailing slash, missing/placeholder detection |
| `src/lib/api.test.ts` | 4 | bearer header, no header without token, problem+json → ApiError, non-JSON error body |
| `src/lib/authedApi.test.ts` | 9 | token use, signed-out 401, refresh-once-and-retry, no retry loop, refresh failure, non-401 not retried, single-flight concurrent refresh, later refresh, throwing refresh not wedging |
| `src/store/authStore.test.ts` | 14 | sync subscribe, signed-in/out init, stale getSession vs event, cleanup/disposed, Strict Mode double init, getSession error/rejection, failing getter, sign-in/up/out errors, confirmation notice, thrown errors, clearMessages |
| `src/components/AuthForm.test.tsx` | 4 | sign-in submit (trimmed), toggle+sign-up, error/notice, masked password/no client policy |
| `src/components/AuthGate.test.tsx` | 5 | loading, signed-out form, signed-in view, unsubscribe on unmount, Strict Mode lifecycle |
| `src/components/ApiStatus.test.tsx` | 3 | alive, network failure, non-alive payload |
| `src/App.test.tsx` | 2 | product heading, not-configured notice (env mocked) |

## Not tested (by design / not possible here)
Live Supabase sign-up/login; a real JWKS fetch over the network (transport is tested against a mock only); dev servers; production build; lint/mypy.
