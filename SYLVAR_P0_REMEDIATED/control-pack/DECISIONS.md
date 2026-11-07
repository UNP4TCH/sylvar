# DECISIONS.md — Architecture Decision Records (ADR)
**Status:** Authoritative History of Binding Decisions  

---

## ADR-001: Modular Monolith vs. Microservices Architecture
* **Status:** APPROVED / FROZEN (Task 2 v1.2)
* **Context:** A distributed microservice architecture introduces severe operational complexity (RPC overhead, service discovery, distributed tracing, network failure modes) unmanageable for a student hackathon team on an 8 GB RAM laptop.
* **Decision:** SYLVAR is designed strictly as a single-process asynchronous FastAPI modular monolith deployed on Render, paired with a React/Vite SPA on Vercel.
* **Consequences:** All internal component boundaries are enforced via Python package structures and typed interfaces. In-process concurrency is orchestrated via `asyncio.gather`. Zero distributed task queues (Celery/Redis) are required for the MVP.

---

## ADR-002: Exact Three-Role Authorization Model
* **Status:** APPROVED / FROZEN (Task 5 v1.6)
* **Context:** Earlier drafts introduced an auxiliary "Reviewer" role for external client stakeholders, creating role bloat and ambiguous state transitions.
* **Decision:** The platform supports exactly three roles: `WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`. All review, change-request, and approval authority belongs exclusively to Brand Managers.
* **Consequences:** Simplifies RBAC enforcement. External client reviewers are formally deferred to post-hackathon enterprise scope.

---

## ADR-003: Independent Client Brand Scoping
* **Status:** APPROVED / FROZEN (Task 5 v1.6)
* **Context:** Agency creatives should not have ambient access to all agency clients.
* **Decision:** Workspace membership alone does not grant access to client brands. Users must be explicitly assigned to client brands via `client_memberships`. Workspace Admins maintain administrative workspace control but must also specify explicit client contexts for client-scoped operations.
* **Consequences:** Prevents cross-client accidental contamination. All client-scoped routes enforce explicit `client_id` authorization.

---

## ADR-004: Direct PostgreSQL Access & Least-Privilege Application Role
* **Status:** APPROVED / FROZEN (Task 5 v1.6)
* **Context:** Connecting via Supabase REST API (PostgREST) lacks support for complex multi-table ACID transactions and row locking. Connecting via Supabase Service-Role key completely bypasses PostgreSQL Row-Level Security (RLS).
* **Decision:** FastAPI connects directly to PostgreSQL via SQLAlchemy Async and asyncpg using a dedicated application role (`sylvar_app_user`) without `SUPERUSER` or `BYPASSRLS` privileges.
* **Consequences:** Transaction-local session variables (`SET LOCAL app.current_workspace_id = ...`) establish tenant context per transaction. RLS acts as defense-in-depth, while FastAPI enforces mandatory query-scoping in code.

---

## ADR-005: Epistemic Tri-State Factual Verification Logic
* **Status:** APPROVED / FROZEN (Task 4 v1.5)
* **Context:** LLMs frequently exhibit binary bias, incorrectly labeling unverified claims as "hallucinations" or "false" simply because evidence is missing from the prompt.
* **Decision:** Factual verification enforces three epistemic outcomes: `SUPPORTED`, `CONTRADICTED`, and `UNVERIFIED`.
* **Consequences:** Missing evidence results in `UNVERIFIED` (advisory warning). Contradictions generate `BLOCKING` violations. Grounding is verifiable and legally defensible.

---

## ADR-006: Pinned Memory Snapshot Audit Lineage
* **Status:** APPROVED / FROZEN (Task 3 v1.5)
* **Context:** If brand guidelines change, historical audits must not change their outcomes retroactively.
* **Decision:** Every logical audit (`audit_runs`) is permanently pinned to a materialized JSONB snapshot of active brand knowledge at creation time (`memory_snapshot_id`).
* **Consequences:** Historical audits remain 100% reproducible. Brand guidelines can evolve freely; evaluating new knowledge requires creating a brand new logical audit run.

---

## ADR-007: Three-Tier Audit Execution Topology
* **Status:** APPROVED / FROZEN (Task 3 v1.5)
* **Context:** Transient API timeouts or worker restarts must not erase audit history or create concurrency collisions.
* **Decision:** Partition audit execution into `audit_runs` (Logical Tier) -> `audit_execution_attempts` (Physical Attempt Tier) -> `audit_checks` (Component Tier).
* **Consequences:** Partial unique index prevents duplicate running attempts. Retries insert new attempt records without overwriting history. Findings from separate attempts are never merged.

---

## ADR-008: Linear-Light Alpha Compositing & Advisory Visual Governance
* **Status:** APPROVED / FROZEN (Task 4 v1.5)
* **Context:** Blending semi-transparent graphics directly in non-linear sRGB creates dark fringes and color distortion. Color matching on complex photography produces excessive false positives.
* **Decision:** Alpha blending executes in linear-light RGB before CIELAB conversion and CIEDE2000 ($\Delta E_{00}$) calculation. Visual deviations ($\Delta E_{00} > 5.0$) are strictly advisory warnings.
* **Consequences:** Zero blocking visual violations. Human Brand Managers acknowledge advisories during sign-off.

---

## ADR-009: JWT Verification Policy (APPROVED as policy 2026-11-04; Supabase compatibility UNVERIFIED)
* **Status:** APPROVED by user as a security policy only. NOT a confirmation that the real Supabase project is compatible. If the project signs with HS256 (or otherwise fails the policy), implementation must STOP and report; the policy must not be weakened or bypassed.
* **Origin:**  Implemented in Phase 1 as the minimal safe reading of PHASE.md "dynamic JWKS discovery via SUPABASE_URL".
* **Decision:** Asymmetric algorithms only (RS*/ES*), allow-listed and pinned to the token header; HS* and `none` rejected. Issuer/audience/expiry/subject required. `JWT_AUDIENCE` has no default. Issuer and JWKS URL derive from `SUPABASE_URL` unless overridden (UNVERIFIED convention). JWKS cached (default TTL 24h per SECURITY_ARCHITECTURE), kid lookup, bounded refresh cooldown on unknown kid; `nbf` validated when present. Missing config or key-source failure fails closed (HTTP 503). JWT carries identity only; roles/assignments come from the database (Phase 2).
* **Consequences:** Real Supabase issuer/audience/algorithm must be verified locally before TASK-005 can be COMPLETE.

**ADR-009 clarification C1 (2026-11-04) — APPROVED by user:** partially configured authentication (e.g. a real `SUPABASE_URL` but no `JWT_AUDIENCE`, or an audience with no issuer source) aborts application startup with a clear error. A fully unset, blank or template-placeholder configuration may start the application, and protected routes then fail closed with HTTP 503 `AUTH_NOT_CONFIGURED` (with a startup warning). Issuer comparison is exact-string (no trailing-slash normalisation).

**ADR-009 clarification C2 (2026-11-04) — APPROVED by user: MVP JWKS timing defaults.** Cache TTL 24 hours; unknown-kid refresh cooldown 30 seconds; JWT clock leeway 30 seconds; JWKS HTTP timeout 5 seconds. Known rotation/revocation trade-offs are accepted and documented in `docs/SECURITY_NOTES.md` section 2.

---

## ADR-010: Browser Session Persistence for MVP (APPROVED 2026-11-04)
* **Status:** APPROVED by user.
* **Context:** The control pack does not specify where the Supabase browser session is stored.
* **Decision:** Keep the default supabase-js behaviour (session persisted in browser `localStorage`). Do NOT introduce a custom session architecture or BFF at this stage.
* **Consequences:** Tokens are readable by any script running on the page; an XSS or compromised dependency could exfiltrate them (the refresh token being the most sensitive). Accepted for the MVP. Mitigations in place and not-yet-implemented hardening (CSP, dependency auditing, possible BFF/cookie sessions) and the revisit trigger (before real user data/production) are documented in `docs/SECURITY_NOTES.md` section 1.
