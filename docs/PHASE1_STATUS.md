# Phase 1 status and review findings (2026-11-04, focused-review pass)

## Evidence summary (figures from `docs/TEST_EVIDENCE.md`)
| Item | Figure |
|---|---|
| Backend distinct tests written | 69 |
| Backend distinct tests executed via ad-hoc runner (not pytest) | 43 (34 verifier/JWKS + 9 security-config) |
| Consecutive successful runner executions, final code state | 100 of 100 (repeats of the same 43 tests; not a test count) |
| Backend tests never executed in any form | 26 (health 3, HTTP auth 8, settings 9, JWKS transport 6); pytest itself has run 0 of 69 |
| Frontend tests | 44 written, 0 executed; no React/Supabase/Zustand code type-checked |
| Static | Python compiles; JSON parses; `env.ts` + `api.ts` pass `tsc --strict` |
| Verified (user, local) | none |

## Review 1 — JWKS caching, refresh, rotation, outage
Confirmed by tests: single-flight cold start (10 concurrent requests = 1 fetch); unknown-kid refresh bounded by cooldown (flood = 1 fetch); rotation picked up once cooldown elapsed; a failed or invalid (`{"keys": []}`, private-key, non-object) refresh never wipes good cached keys; outage = 503, never 200; outage not hammered; recovery after cooldown; stale cache refetched after TTL.
Accepted/documented behaviours (not bugs, but you should know):
- A token signed by a *newly rotated* key that arrives within the 30s cooldown after a refresh gets 401 until the cooldown ends (the frontend refresh-retry will not help inside that window).
- A key removed/revoked upstream stays trusted until the cache TTL (default 24h, per SECURITY_ARCHITECTURE) unless an unknown kid triggers a refresh that happens to re-read the set. Tested as documented behaviour.
- When the TTL expires during a JWKS outage, all authentication returns 503 (fail-closed, per ADR-009).
- A JWKS fetch holds the refresh lock for up to the 5s timeout; requests with already-cached kids are not blocked.
- Entries with private-key members, non-RSA/EC key types, `use != sig`, or missing/duplicate `kid` are ignored.

## Review 2 — Frontend session lifecycle and Strict Mode
FOUND and FIXED: (a) `init()` was async, so React Strict Mode's mount→unmount→mount could leave a live subscription from the first mount (cleanup arrived after the unmount); (b) a late `getSession()` result could overwrite a newer auth event with stale "signed out". Now: subscribe first, return cleanup synchronously, ignore `getSession()` results once an event was seen or the instance is disposed. Concurrent 401s now share one `refreshSession()` call (no refresh-token race). Covered by new store, AuthGate (Strict Mode) and authedApi tests — UNRUN.
Decision (ADR-010, APPROVED): keep supabase-js default `localStorage` session persistence for the MVP; XSS consideration in `docs/SECURITY_NOTES.md`. `authedApi` has no caller until Phase 2 adds protected endpoints (it is tested infrastructure).

## Review 3 — Backend startup/configuration failure
FOUND and FIXED: a *partial* auth config (e.g. audience set, URL missing) silently disabled auth (503s with no explanation). Now it aborts startup with a clear error (names missing settings, never values). Blank/template-placeholder values count as unset, so copying `.env.example` still boots. Startup logs a warning when auth is unconfigured and an info line (issuer, algorithms) when configured. Invalid issuer/JWKS URL (non-https except localhost), HS*/none algorithms, bad bounds, and a `*` CORS origin all fail fast.
Behaviours to know: JWKS reachability is not checked at startup (first auth request reveals it); `create_app()` runs at import, so invalid env also fails pytest collection of modules importing `app.main`; `.env` is read from the current directory (run from `backend/`).

## Review 4 — Consistency with ADR-009 and SECURITY_ARCHITECTURE
| Requirement | Implementation | Result |
|---|---|---|
| RS256/ES256 via JWKS; validate signature, exp, nbf, iss, aud | PyJWT, pinned to header alg from allow-list; nbf validated when present; iss/aud/exp/sub required | Aligned |
| JWKS cache 24h + bounded refresh for rotation | default 86400s; cooldown 30s | Aligned |
| Use project's real issuer/audience/algs; do not assume | audience has no default; issuer/JWKS derived from SUPABASE_URL unless overridden (convention, UNVERIFIED) | Aligned; real values unverified |
| HS*/none rejected | rejected at config and at verify time; alg-confusion test | Aligned |
| Fail closed | 503 on missing config/JWKS failure | Aligned |
| JWT = identity only; roles from DB (ADR-003) | only `user_id`, `exp` exposed | Aligned |
| RFC 9457 errors, no token echo | tested | Aligned |
| Partial config aborts startup | Implemented | Clarification C1 — APPROVED |
| shadcn/ui (MEMORY stack) | not initialised | Gap (needs CLI/network) |

## Review 5 — The earlier unexplained test failures
**Observation:** one sandbox run of the then-35 ad-hoc tests had 19 failures; traceback not captured; no recurrence in the recorded runs that followed (23 recorded clean runs with the flawed helper, then 100/100 with the fixed helper; see ledger).
**My first hypothesis (iat/clock sensitivity) was wrong** — the `iat` change I made was unnecessary (harmless, kept).
**Evidence found:** (1) every failing test used the module-level EC key and no EC-free test failed; (2) PyJWT 2.7.0 `ECAlgorithm.to_jwk` strips leading zero bytes from EC coordinates, and `PyJWK` then rejects its own export ("Coords should be 32 bytes for curve P-256"): measured 19 of 3000 (0.63%) generated P-256 keys fail the round trip, consistent with a single occurrence across the many runs made with the old helper (the exact pre-failure run count was not recorded); (3) forcing such a key as the module-level EC key reproduced **exactly the same 19 failing test names** (set-equal comparison), with the provider correctly failing closed (JWKS_INVALID/503).
**Fix:** the test helper now builds RFC 7518 fixed-length JWKs; regression tests generate a genuinely leading-zero key and verify it is accepted.
**What is still not proven:** the original run's traceback was never captured, so attributing *that* run to this cause is a strong inference (exact failure-set match), not a proof. This affected only test key generation in this sandbox (PyJWT 2.7.0); your local PyJWT version may differ. Real JWKS endpoints publish fixed-length coordinates. If you see any intermittent failure, report it with the traceback.

## Overlooked deliverables check
All five PHASE.md Phase 1 deliverables have code. Nothing was missed that the pack requires, except items that need your machine: running dev servers, lockfiles/version pins, git init, shadcn/ui init, real Supabase sign-up/login, live JWT check. No CI was requested; none added.
