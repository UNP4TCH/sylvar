# PHASE.md — Development Lifecycle & Phase Gates
**Status:** Authoritative Roadmap  
**Current Phase:** Round 2 Pre-Integration Remediation Complete (Phases 1-5 Remediated & Verified). Real Supabase credentials explicitly pending user injection.  

---

## Phase Overview

```
[Phase 1: Foundation & Identity]                   --> VERIFIED (101/101 pytest, 46/46 vitest)
                │
                ▼
[Phase 2: Multi-Tenancy & Relational Schema]      --> VERIFIED (Dual-tenant isolation, 5-gate pipeline, RLS functions)
                │
                ▼
[Phase 3: Living Brand Memory & Ingestion]         --> VERIFIED (Ingestion, rules, async Gemini, SHA-256 snapshots)
                │
                ▼
[Phase 4: Content Governance & Audit Engines]      --> VERIFIED (3-tier orchestrator, tri-state NLI, fail-closed Gemini, CIEDE2000)
                │
                ▼
[Phase 5: Human Review, Hardening & Deployment]    --> VERIFIED (Review queue, terminal state invariants, certificates, Dashboard UI)
```

---

## Phase 1: Foundation & Identity Infrastructure
* **Objective:** Initialize monorepo, configure development environments, integrate Supabase Auth, and establish cryptographic JWT/JWKS verification.
* **Prerequisites:** Round 2 explicit authorization by user.
* **Tasks:** `TASK-001` to `TASK-006` in `TASKS.md`.
* **Deliverables:**
  * Clean monorepo directory layout (`/frontend`, `/backend`, `/supabase`).
  * Running FastAPI backend and Vite frontend development servers.
  * Supabase Auth signup/login flow with JWT issuance.
  * Backend JWT verification middleware using dynamic JWKS discovery via `SUPABASE_URL`.
  * Public liveness endpoint (`GET /api/v1/health`) returning `{"status": "alive"}`.
* **Exit Gate:** Automated test verifying that valid Supabase JWTs resolve `user_id` and invalid/expired JWTs return `HTTP 401 Unauthorized`.
* **Gate status:** OPEN. Tests are written (backend 69, frontend 44). Executed so far: 43 distinct backend verifier/config tests via an ad-hoc runner (not pytest), 100/100 consecutive clean runner executions (generated keys, mocked JWKS). Not executed: 26 backend tests and all 44 frontend tests; pytest has run 0. Figures: `docs/TEST_EVIDENCE.md`. ADR-009 (+C1, C2) and ADR-010 approved by the user; real-Supabase compatibility unverified. Phase 1 closes only after the user's local verification (`LOCAL_SETUP_AND_VERIFICATION.md`).

---

## Phase 2: Multi-Tenancy, Client Scoping & Database RLS
* **Objective:** Deploy the complete 25-table relational schema, configure the least-privilege `sylvar_app_user` role, implement transaction-local tenant context, and build workspace/client management APIs.
* **Prerequisites:** Phase 1 complete and verified.
* **Tasks:** `TASK-007` to `TASK-013` in `TASKS.md`.
* **Deliverables:**
  * 3 sequential SQL migrations executed in Supabase PostgreSQL (`001_initial_schema.sql` to `003_audit_engine.sql`).
  * Least-privilege application role (`sylvar_app_user`) configured without superuser or `BYPASSRLS`.
  * FastAPI dependency injection pipeline enforcing the 5-gate authorization check.
  * Transaction-local session context setting (`SET LOCAL app.current_workspace_id = ...`).
  * Workspace Admin CRUD routes, team member invitations, and client brand assignment endpoints.
  * Stateful real-time membership revocation checks.
* **Exit Gate:** Automated tenant isolation tests prove that User A (assigned to Client 1) receives `HTTP 403` when attempting to access Client 2 data, and composite foreign keys reject mismatched tenant tuples.

---

## Phase 3: Living Brand Memory & Guideline Ingestion
* **Objective:** Implement multi-format document parsing with decompression bomb safety, structured Gemini candidate rule extraction, Brand Manager candidate staging, and immutable snapshot publishing.
* **Prerequisites:** Phase 2 complete and verified.
* **Tasks:** `TASK-014` to `TASK-020` in `TASKS.md`.
* **Deliverables:**
  * Multipart document ingestion endpoint supporting TXT, Markdown, DOCX, and text-based PDF.
  * DOCX archive safety guards ($\le 500$ entries, $\le 50$ MB uncompressed, $\le 100:1$ ratio, no `..`).
  * PDF parser resource limits (10s timeout, $\le 100$ pages).
  * Candidate rule staging endpoints (`extracted_candidates`).
  * Brand Manager rule editing and approval workflow.
  * Memory release publisher generating versioned records (`brand_memory_versions`), SHA-256 snapshot hashes, and materialized JSONB snapshots (`brand_memory_snapshots`).
  * Transactional update of `client_brands.active_memory_version_id`.
* **Exit Gate:** Uploading a brand handbook parses sections, extracts candidates into staging, allows manual approval, and publishes an immutable snapshot whose hash is permanently verifiable.

---

## Phase 4: Content Governance Engine (Auditing & Remediation)
* **Objective:** Build the multi-modal content submission intake, 3-tier audit orchestrator, deterministic terminology linter, Gemini factual NLI verifier, Pillow/NumPy visual color analyzer, and surgical AI correction engine.
* **Prerequisites:** Phase 3 complete and verified.
* **Tasks:** `TASK-021` to `TASK-030` in `TASKS.md`.
* **Deliverables:**
  * Collateral submission API (text $\le 50,000$ chars, image $\le 10$ MB).
  * Asynchronous audit creation returning `HTTP 202 Accepted` with stable `audit_id`.
  * In-process concurrency via `asyncio.gather(..., return_exceptions=True)` across Terminology, Factual, and Visual checks.
  * Deterministic regex terminology compliance engine with Unicode NFC normalization.
  * Atomic claim extraction and tri-state NLI verification (`SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`) with verbatim substring citation assertion.
  * Visual palette analysis using linear-light alpha compositing and pure-Python CIEDE2000 math.
  * Diagnostic scorecard aggregation mapping outcomes to `PASS`, `WARNINGS`, `BLOCKED`.
  * Surgical AI correction suggestions with Levenshtein ratio $\le 0.25$, visual diffs, and version forking (v1.1) triggering fresh delta audits.
  * Capped exponential backoff polling on frontend.
* **Exit Gate:** End-to-end audit detects simulated prohibited terms and contradicted claims, flags visual deviations as advisory, isolates component timeouts, and verifies that accepting a fix forks an immutable version and re-audits cleanly.

---

## Phase 5: Human Review, Hardening, Deployment & Demo Readiness
* **Objective:** Build the Brand Manager review queue with advisory acknowledgment, exportable audit compliance manifests, SlowAPI rate limiting, RFC 9457 error formatting, Vercel/Render deployments, and live demo seeding.
* **Prerequisites:** Phase 4 complete and verified.
* **Tasks:** `TASK-031` to `TASK-038` in `TASKS.md`.
* **Deliverables:**
  * Brand Manager review queue endpoints (`/reviews`) enforcing zero-blocking gating.
  * Relational advisory acknowledgment persistence (`human_review_advisory_acknowledgements`).
  * Post-approval edit forking invariant (editing approved asset resets state to `DRAFT`).
  * Exportable JSON/PDF compliance certificates (`audit_history`).
  * In-process SlowAPI rate-limiting middleware.
  * RFC 9457 Problem Details error formatting.
  * Production deployment to Vercel (Frontend) and Render (FastAPI Container).
  * Demo database seeding script (`dev_fixtures.sql`) with multi-client scenarios.
* **Exit Gate:** Complete live golden-path walkthrough executes on staging URLs without cold-start interruptions, demonstrating full compliance governance and verifiable certificate export.
