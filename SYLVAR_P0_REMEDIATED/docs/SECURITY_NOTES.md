# Security considerations recorded for Phase 1 (MVP decisions)

## 1. Browser session persistence (ADR-010, APPROVED for MVP)
**Decision:** keep supabase-js defaults: the session (access token and refresh token) is persisted in the browser's `localStorage`. No custom session architecture, cookie scheme or backend-for-frontend (BFF) is introduced now.

**Consideration — XSS exposure.** Anything stored in `localStorage` is readable by any JavaScript running on the page. A successful cross-site-scripting (XSS) attack, or a compromised third-party/npm script, could copy the stored tokens. The refresh token is the most sensitive item: it can mint new access tokens after the short-lived access token expires, until it is revoked or the session ends. `HttpOnly` cookies (via a BFF or server-side session) would hide tokens from page scripts, at the cost of a different architecture, CSRF handling and more backend work; that trade-off was deliberately deferred.

**What reduces the risk today (not eliminates it):**
- React escapes rendered values; application code uses no `dangerouslySetInnerHTML` (grep-checked) and no direct `localStorage`/`eval` use.
- The backend never trusts the frontend: every request is authorised from a verified JWT (ADR-009); tokens are not logged or echoed (tested).
- Supabase access-token lifetime is configurable by you (record it in LOCAL_SETUP section D2).
- Keep the frontend dependency set small; commit the lockfile; review additions.

**Not implemented, candidates for later hardening (Phase 5 or before real user data):** a strict Content-Security-Policy and other security headers on the hosting layer; dependency auditing in CI; revisiting a BFF/cookie session if the threat model or data sensitivity requires it. **Revisit trigger:** before storing real customer/brand data or going to production.

## 2. JWKS timing defaults (ADR-009, APPROVED MVP defaults)
Cache TTL 24 h; unknown-kid refresh cooldown 30 s; JWT clock leeway 30 s; JWKS HTTP timeout 5 s. All are configurable by environment variable.

**Known key-rotation and revocation trade-offs (accepted):**
- *Rotation:* a token signed by a newly rotated key is rejected (401) if it arrives within 30 s after a refresh that did not yet contain that key; it verifies once the cooldown has elapsed (the next unknown-kid refresh). The frontend's refresh-and-retry does not help inside that window.
- *Revocation:* a key removed or compromised upstream stays trusted until the cache entry expires (up to 24 h) or another unknown-kid refresh re-reads the key set. This follows the 24 h cache stated in SECURITY_ARCHITECTURE. If faster revocation matters later, lower `JWKS_CACHE_TTL_SECONDS`; the trade-off is more JWKS fetches.
- *Outage:* if the cache has expired and the JWKS cannot be fetched, authentication fails closed with 503 for everyone. While the cache is still fresh, known keys keep working through an outage.
- *Leeway:* 30 s clock leeway means an expired token can be accepted for up to 30 s after `exp`.
- *Startup:* JWKS reachability is not checked at startup; the first authenticated request reveals a bad `JWKS_URL`.

## 3. Startup configuration policy (ADR-009 clarification C1, APPROVED)
Partially configured authentication aborts startup with a clear error. Fully unset, blank or template-placeholder configuration starts the app and protected routes fail closed with 503 `AUTH_NOT_CONFIGURED`.
