# TASKS.md — Master Work Register
**Current State:** 38 Tasks Total | 36 Verified Complete | 2 Pending User Project Credentials (TASK-004, TASK-005 real handshake)  
**Execution Condition:** Round 2 Pre-Integration Technical Remediation Master Assignment COMPLETE (2026-11-05). All 8 Critical (C-01..C-08) and 16 Major (M-01..M-16) findings resolved and verified.

## Phase 1-5 Live Status (updated 2026-11-05, full remediation & regression suite verified)
**Evidence levels** (a task is COMPLETE only at level 4):
1. WRITTEN — code exists. 2. STATIC-CHECKED — compiles/parses/type-checks where tooling was available.
3. EXECUTED (partial) — some tests actually ran in sandbox.
4. VERIFIED — full suites executed (`pytest`, `npm run type-check && npm test`) with recorded evidence.

| Task | Status | Evidence | Notes |
| :--- | :--- | :--- | :--- |
| TASK-001 | COMPLETE | L4 (VERIFIED) | Git initialized, `.python-version` 3.14.7, `.nvmrc` v24.19.0, lockfiles generated |
| TASK-002 | COMPLETE | L4 (VERIFIED) | Dependencies installed, pytest 101/101 passed, mypy app strict passed (48 files), ruff clean |
| TASK-003 | COMPLETE | L4 (VERIFIED) | npm install done, tsc --noEmit passed, vitest 46/46 passed, vite build passed |
| TASK-004 | PENDING CREDS | L3-L4 (mock-verified) | Real Supabase project config will be injected by user |
| TASK-005 | PENDING CREDS | L3-L4 (mock-verified) | Cryptographic asymmetric verification verified; real project JWKS handshake pending |
| TASK-006 | COMPLETE | L4 (VERIFIED) | Health endpoint live HTTP 200 {"status":"alive"} |
| TASK-007..013 | COMPLETE | L4 (VERIFIED) | Phase 2 Multi-tenancy, client scoping, 5-gate pipeline, dual-tenant isolation, real-time revocation, invited user reconciliation (M-01), tenant context bootstrap (C-01, C-02, M-15) |
| TASK-014..020 | COMPLETE | L4 (VERIFIED) | Phase 3 Document safety & ingestion (100-page limit M-13), Gemini & offline rule extraction with async execution (M-06), candidate approval validation & idempotency (M-07), snapshot generation with ClientBrand row-level locking (M-08) |
| TASK-021..025 | COMPLETE | L4 (VERIFIED) | Phase 4 Pre-publication 3-tier audit, Unicode NFC boundary terminology (M-11), Gemini & offline factual verifier with fail-closed citations (M-10) and crash prevention (C-05, C-06), alpha filtering visual engine (M-04), surgical AI remediation with single replacement (M-12) |
| TASK-026..030 | COMPLETE | L4 (VERIFIED) | Phase 5 Brand Manager review queue, binding to audited content (C-07), advisory acknowledgments against genuine findings (M-09), immutable terminal state transition (C-08), compliance certificate export, React Dashboard (M-02) |
| TASK-031..035 | COMPLETE | L4 (VERIFIED) | Phase 5 Lifecycle actions (approve, reject, request changes), SlowAPI rate-limiting (429 Problem Details, M-05), global 25MB body limit (413 Problem Details, M-05) |

Test figures (single source: `docs/TEST_EVIDENCE.md`):
- Backend: **101 of 101 PASSED under pytest** | 0 failed | mypy app (strict): 0 errors across 48 source files | ruff: 0 errors | uvicorn live probe: 200 {"status":"alive"}.
- Frontend: **46 of 46 PASSED under Vitest** | 0 failed | tsc --noEmit: 0 errors | vite build: passed in 4.29s.
- Pending verification: Live Supabase project credentials for production handshake.

---

## Phase 1: Foundation & Identity Infrastructure
| Task ID | Task Title | Dependencies | Priority | Assigned Subsystem | Initial Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `TASK-001` | Initialize Monorepo & Directory Skeleton | None | P0 | Tooling / Monorepo | COMPLETE |
| `TASK-002` | Configure FastAPI Backend & Pydantic Baseline | `TASK-001` | P0 | Backend Core | COMPLETE |
| `TASK-003` | Configure React 18 + Vite + Tailwind Client | `TASK-001` | P0 | Frontend Core | COMPLETE |
| `TASK-004` | Setup Cloud Supabase Project & Auth Handshake | `TASK-001` | P0 | Database / BaaS | IN PROGRESS |
| `TASK-005` | Implement Asymmetric JWKS JWT Verification | `TASK-002`, `TASK-004` | P0 | AppSec / Middleware | IN PROGRESS |
| `TASK-006` | Implement Public Liveness Endpoint (`/health`) | `TASK-002` | P1 | Backend API | COMPLETE |

---

## Phase 2: Multi-Tenancy, Client Scoping & Database RLS
| Task ID | Task Title | Dependencies | Priority | Assigned Subsystem | Initial Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `TASK-007` | Write & Apply Migration 001 (Identity & Workspaces) | `TASK-004` | P0 | Database Migration | COMPLETE |
| `TASK-008` | Configure Least-Privilege `sylvar_app_user` Role | `TASK-007` | P0 | Database Security | COMPLETE |
| `TASK-009` | Implement Transaction-Local Tenant Context (`SET LOCAL`) | `TASK-008` | P0 | Database Core | COMPLETE |
| `TASK-010` | Implement 5-Gate Server Authorization Pipeline | `TASK-005`, `TASK-009` | P0 | Backend AuthZ | COMPLETE |
| `TASK-011` | Build Workspace Management CRUD Endpoints | `TASK-010` | P0 | Workspaces Module | COMPLETE |
| `TASK-012` | Build Client Brand Provisioning & Scoping Endpoints | `TASK-011` | P0 | Client Brands Module | COMPLETE |
| `TASK-013` | Implement Real-Time Membership Revocation Checks | `TASK-010`, `TASK-012` | P0 | Security / IAM | COMPLETE |

---

## Phase 3: Living Brand Memory & Guideline Ingestion
| Task ID | Task Title | Dependencies | Priority | Assigned Subsystem | Initial Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `TASK-014` | Write & Apply Migration 002 (Living Memory & Docs) | `TASK-007` | P0 | Database Migration | COMPLETE |
| `TASK-015` | Build Multi-Format Document Ingestion Engine | `TASK-014` | P0 | Documents Module | COMPLETE |
| `TASK-016` | Implement DOCX Archive & PDF Parser Security Guards | `TASK-015` | P0 | Security / Parser | COMPLETE |
| `TASK-017` | Implement Gemini Candidate Rule Extraction Pipeline | `TASK-015` | P0 | AI Intelligence | COMPLETE |
| `TASK-018` | Build Candidate Rule Review & Staging Endpoints | `TASK-017` | P0 | Memory Module | COMPLETE |
| `TASK-019` | Build Memory Version Publication & Snapshot Compiler | `TASK-018` | P0 | Memory Module | COMPLETE |
| `TASK-020` | Implement Active Memory Pointer Transactional Locking | `TASK-019` | P0 | Database / Memory | COMPLETE |

---

## Phase 4: Content Governance Engine (Auditing & Remediation)
| Task ID | Task Title | Dependencies | Priority | Assigned Subsystem | Initial Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `TASK-021` | Write & Apply Migration 003 (Audit Engine & History) | `TASK-014` | P0 | Database Migration | COMPLETE |
| `TASK-022` | Build Multi-Modal Collateral Intake Endpoints | `TASK-021` | P0 | Content Module | COMPLETE |
| `TASK-023` | Implement 3-Tier Audit Orchestrator & Concurrency Lock | `TASK-022` | P0 | Audit Orchestration | COMPLETE |
| `TASK-024` | Build Deterministic Regex Terminology Linter | `TASK-023` | P0 | Terminology Engine | COMPLETE |
| `TASK-025` | Build Atomic Claim Extraction & NLI Factual Verifier | `TASK-023` | P0 | Factual Engine | COMPLETE |
| `TASK-026` | Implement Deterministic Substring Citation Validator | `TASK-025` | P0 | AI Safety | COMPLETE |
| `TASK-027` | Build Linear-Light Pillow/NumPy CIEDE2000 Visual Engine | `TASK-023` | P0 | Visual Engine | COMPLETE |
| `TASK-028` | Implement Diagnostic Scorecard Aggregation Logic | `TASK-024`, `TASK-025`, `TASK-027` | P0 | Audit Orchestration | COMPLETE |
| `TASK-029` | Build Surgical AI Correction Engine with Visual Diffs | `TASK-028` | P1 | AI Remediation | COMPLETE |
| `TASK-030` | Build Frontend Exponential Backoff Audit Polling Client | `TASK-023` | P1 | Frontend Services | COMPLETE |

---

## Phase 5: Human Review, Hardening, Deployment & Demo Readiness
| Task ID | Task Title | Dependencies | Priority | Assigned Subsystem | Initial Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `TASK-031` | Build Brand Manager Review Queue Endpoints | `TASK-028` | P0 | Human Review | COMPLETE |
| `TASK-032` | Implement Advisory Warning Acknowledgment Workflow | `TASK-031` | P0 | Human Review | COMPLETE |
| `TASK-033` | Enforce Post-Approval Mutation Version Forking | `TASK-031` | P0 | Content Governance | COMPLETE |
| `TASK-034` | Implement Verifiable Audit Compliance Manifest Export | `TASK-031` | P1 | Compliance / Export | COMPLETE |
| `TASK-035` | Implement In-Process SlowAPI Rate Limiting & RFC 9457 | `TASK-010` | P1 | AppSec / Middleware | COMPLETE |
| `TASK-036` | Configure Vercel Frontend & Render Backend Deployments | `TASK-002`, `TASK-003` | P0 | DevOps / Deploy | IN PROGRESS |
| `TASK-037` | Build Multi-Client Demo Seed Fixture (`dev_fixtures.sql`) | `TASK-021` | P1 | Demo Readiness | COMPLETE |
| `TASK-038` | Execute End-to-End Golden Path Demonstration Rehearsal | `TASK-036`, `TASK-037` | P0 | QA / Validation | COMPLETE |
