# LOCAL SETUP AND VERIFICATION (Phase 1)

Authoritative checklist of everything YOU must do. Nothing below has been run by you yet; the authoring
sandbox had no network, pytest or npm. Do the steps in order and send me failures with full tracebacks.

## A. Honest status (figures: `docs/TEST_EVIDENCE.md`)
- **Backend tests:** 69 distinct written. 43 distinct executed through an ad-hoc runner (NOT pytest): 34 JWT verifier/JWKS + 9 security config, using generated keys and a mocked JWKS. Those 43 passed in 100 of 100 consecutive runner executions (repeats; not a test count). **26 backend tests have never been executed in any form** (health 3, HTTP auth 8, settings 9, JWKS transport 6). pytest itself has run 0 of 69.
- **Frontend tests:** 44 written, 0 executed. Only `env.ts` and `api.ts` pass `tsc --strict`; all other TypeScript/React is UNCHECKED.
- **Statically checked:** Python compiles; JSON parses.
- **Decisions approved by you (2026-11-04):** ADR-009 C1 (partial auth config aborts startup; fully unset starts and returns 503), ADR-009 C2 (JWKS 24 h TTL / 30 s cooldown / 30 s leeway / 5 s timeout), ADR-010 (keep supabase-js localStorage sessions for MVP). Real Supabase compatibility is still unverified; if the project uses HS256 (or anything failing the policy) I stop and report — never weaken it.
- **Earlier unexplained test failure:** strongly attributed (not proven) to a flawed EC-JWK export in my test helper, now fixed; original traceback never captured. Report any intermittent failure WITH traceback.

## B. Tooling and versions
1. Choose and pin runtimes: Python (>=3.11; add `.python-version`) and Node LTS (add `.nvmrc`). Tell me the versions you used.
2. `git init` at the repo root; commit after verification. Do not commit `.env` files (they are git-ignored).

## C. Backend
1. `cd backend && python -m venv .venv && source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)
2. `pip install -e ".[dev]"`
3. `pytest -v` — record pass/fail counts (expected 69 tests). Run it **from `backend/`**.
   - If collection fails with a config error, check `backend/.env` for a *partial* auth configuration (see D3).
4. `ruff check . && mypy app` — report findings (mypy strict may flag items; none have been checked).
5. `pip freeze > requirements.lock.txt` (exact versions are UNVERIFIED until you do this). If your PyJWT is not 2.7.0, note the version.
6. `cp ../.env.example .env`, then `uvicorn app.main:app --reload`.
   - Expected log: a WARNING that JWT authentication is NOT configured (until section D is done).
   - `curl localhost:8000/api/v1/health` → `{"status":"alive"}`.

## D. Supabase (TASK-004 — needs YOUR project; do not share secrets with me)
1. Create a Supabase project; enable Email auth.
2. Record from Supabase Auth settings: email confirmation on/off, minimum password length, JWT expiry.
3. `backend/.env`: set **`SUPABASE_URL` and `JWT_AUDIENCE` together** (a real URL without an audience, or an audience without a URL, aborts startup by design). Leave the service-role key out of every file.
4. `frontend/.env` (copy `.env.frontend.example`): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`. Only the anon/publishable key goes here.
5. Sign up/in through the UI, then inspect a real access token's header and payload (public token only; decode locally or on a trusted tool) and record:
   - header `alg` and `kid` → set `JWT_ALGORITHMS` accordingly (policy allows RS256/RS384/RS512/ES256/ES384/ES512 only)
   - payload `iss` → must equal `<SUPABASE_URL>/auth/v1` **exactly** (no trailing-slash normalisation); otherwise set `JWT_ISSUER`
   - payload `aud` → the value for `JWT_AUDIENCE` (no default exists)
6. Open `<issuer>/.well-known/jwks.json` (or your `JWKS_URL`) in a browser; confirm it lists a key whose `kid` matches the token and whose `x`/`y` (EC) or `n`/`e` (RSA) are present.
7. **If the token's `alg` is HS256 (shared secret), STOP and report to me.** Do not change the policy or the allow-list to make it work.

## E. Live JWT check (TASK-005 exit gate)
1. Restart the backend; the log should now say JWT authentication configured (issuer, algorithms).
2. Call a route protected by `Depends(get_current_user)` with a real token (use the test-route pattern in `tests/test_auth_dependency.py` in a scratch file; no production route exists yet) → expect 200 and your user UUID.
3. Garbage token, expired token, no token → 401 `application/problem+json`. Wrong `JWKS_URL` or backend offline from Supabase → 503, never 200.
4. Note the rotation behaviour: a key rotated upstream is picked up on the next unknown-kid refresh (30s cooldown); a removed key stays trusted until cache TTL (default 24h). Tell me if you want different defaults.
5. Record results; only then can TASK-005 be considered for COMPLETE.

## F. Frontend
1. `cd frontend && npm install` (commit `package-lock.json`)
2. `npm run type-check && npm test` — record counts (expected 44 tests). Report any type errors; none of the React/Supabase/Zustand code has been type-checked.
3. `npm run dev` → with no `.env`, page shows "SYLVAR is not configured" listing missing variables.
4. After D: sign up a test user; outcome should match your confirmation setting (notice vs immediate sign-in).
5. Sign in → "Signed in as <email>" and "API: alive" (backend running; `ALLOWED_ORIGINS` includes `http://localhost:5173`; CORS problems show as "unreachable").
6. Sign out works; reload keeps the session; wrong password shows the provider's error.
7. React Strict Mode (default in dev): watch the browser console/network for duplicate auth subscriptions or flicker back to signed-out on reload; report any.
8. `npm run build` succeeds.
9. shadcn/ui is NOT initialised: when ready run its init (`npx shadcn@latest init`), tell me the result.

## G. Decisions (all recorded; nothing pending)
- ADR-009 C1, ADR-009 C2 and ADR-010 are APPROVED (`control-pack/DECISIONS.md`). Security consequences, including the XSS exposure of localStorage sessions and the JWKS rotation/revocation trade-offs: `docs/SECURITY_NOTES.md`.
- New decision needed only if verification shows incompatibility (e.g. HS256 signing): STOP and report.

## H. Open items I did not touch
- `/auth/session` vs Supabase Auth ownership (OPEN_QUESTIONS #5).
- All Phase 2 gates (DDL, RLS, DTOs, DB role, restart reconciliation). Phase 2 has NOT started.
- No CI; no Docker; no production deployment config.

## I. Closing Phase 1
Phase 1 closes only when C, D, E and F pass and you report the results to me. I then update TASKS.md/PHASE.md/MEMORY.md with the evidence and mark tasks COMPLETE where the pack's requirements are met. Phase 2 starts only on your explicit instruction.
