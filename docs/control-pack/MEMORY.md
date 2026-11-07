# MEMORY.md — Persistent Project Context
**Status:** Living Engineering Memory  
**Revision:** 1.0.0  
**Phase:** Round 1 CLOSED | Round 2 IN PROGRESS (Phase 1 only)  

---

## 1. Project Identity & Positioning
* **Product Name:** SYLVAR (working name; clearance pending)
* **Tagline:** The Pre-Publication CI/CD for Brand Integrity
* **Target Audience:** Mid-sized creative and marketing agencies managing multiple client brands.
* **Core Value Proposition:** Intercepts marketing copy and visual graphics before publication, auditing them against versioned, human-approved client knowledge (Living Brand Memory), providing evidence-backed diagnostics, and enforcing human review sign-offs.

---

## 2. Approved Technology Stack
* **Frontend:** React 18.x, Vite 5.x, TypeScript 5.x, Tailwind CSS 3.x, shadcn/ui, Zustand 4.x.
* **Backend:** Python 3.11+, FastAPI 0.110+, Pydantic v2, SQLAlchemy 2.0+ Async, asyncpg 0.29+.
* **Database & BaaS:** Supabase Managed PostgreSQL 15+, Supabase Auth (GoTrue).
* **AI Provider:** Google Gemini API (model ID configured through `GEMINI_MODEL`; verify availability, structured-output support, limits and account terms before selecting a model).
* **Visual Processing:** Pillow 10.x, NumPy 1.26+, Pure-Python CIEDE2000 (Sharma 2005 formulation).
* **Document Parsers:** `pdfplumber`, `python-docx`. Plain text and Markdown handling.
* **Hosting Targets:** Vercel (Frontend SPA), Render (Backend FastAPI Container), Supabase Cloud (PostgreSQL, Auth, Storage).
* **Excluded Infrastructure (Strict MVP Invariant):** NO Redis, NO Celery, NO Microservices, NO Kubernetes, NO Vector Databases (Pinecone/Chroma/Qdrant), NO Scanned OCR engines, NO Auto-publishing integrations.

---

## 3. Epistemic & Audit Invariants
* **User Roles:** Exactly three: `WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`.
* **Client Scoping:** Independent of workspace membership. `client_memberships` table explicitly links members to client brands.
* **Audit Execution Statuses:** `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `INTERRUPTED`.
* **Audit Evaluation Outcomes:** `PASS`, `WARNINGS`, `BLOCKED`.
* **Factual Verification Outcomes:** `SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`.
* **Content Version Lifecycle:** `DRAFT` -> `AUDITING` -> `ISSUES_FOUND` -> `READY_FOR_REVIEW` -> `UNDER_REVIEW` -> `CHANGES_REQUESTED` -> `APPROVED` -> `REJECTED`.
* **Gating Policy:** Assets with $\ge 1$ `BLOCKING` issue or failed required check cannot be submitted for review or approved. Advisory warnings may be acknowledged by a Brand Manager.

---

## 4. Current Workstation & Hardware Constraints
* **OS:** Windows 11 Home / Pro (WSL2 Ubuntu 24.04 recommended).
* **Processor:** 12th Gen Intel Core i3-1215U (6 Cores / 8 Threads).
* **RAM:** 8.0 GB Physical RAM.
* **RAM Budget:** Local dev stack must run under 5.5 GB total footprint.
* **Strategy:** Use Cloud Supabase PostgreSQL for development by default to save 1.5+ GB of local Docker memory overhead.

---

## 5. Round Status & Authorization State
* **Round 1 (Planning & Specification):** CLOSED & APPROVED.
* **Agent Control Pack:** GENERATED.
* **Round 2 (Build & Implementation):** **IN PROGRESS (ACCELERATED BUILD AUTHORIZED ACROSS PHASES 1-5)**.
* **ROUND_2_AUTHORIZED:** `TRUE — PHASES 1-5 MVP ACCELERATED BUILD` (User instruction, 2026-11-04).
* **ADR-009:** Approved and strictly enforced. Asymmetric cryptographic verification (RS256/ES256), fail-closed 503, dynamic JWKS caching with cooldown.
* **Phase 1-5 Verified MVP State:**
  - Backend: 85/85 pytest tests passing. Strict mypy passing across 45 files. Ruff passing with 0 errors.
  - Frontend: 44/44 vitest tests passing. Strict TypeScript passing with 0 errors. Vite production build passed.
  - End-to-end golden path demonstrator ready in frontend Dashboard.
  - Outstanding integration: Live Supabase project credentials (SUPABASE_URL, JWT_AUDIENCE, anon key) to be configured by user for live production deployment.


## 6. Planning Freeze Conditions
The control pack is a planning baseline only. Schema DDL/RLS, complete API DTOs, model selection and process-restart behavior remain explicit verification gates in `references/OPEN_QUESTIONS.md`. Round 2 remains unauthorized until the user explicitly approves it.
