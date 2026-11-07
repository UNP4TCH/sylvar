# SYLVAR — Multi-Tenant Brand Governance & Content Compliance Platform

> **Create with confidence. Publish with integrity.**  
> SYLVAR is an enterprise-grade AI content governance and compliance certification engine. It bridges creative generation and brand integrity by enforcing strict brand terminology, factual verification, regulatory disclaimers, and human-in-the-loop review workflows before publication.

---

## Key Capabilities

1. **Living Brand Memory Engine**
   - Automated ingestion of unstructured brand guidelines (.txt, .md, .pdf, .docx).
   - Candidate rule extraction, deduplication, and Brand Manager review/approval workflow.
   - Versioned, immutable Brand Memory Snapshots sealed with SHA-256 cryptographic digests.

2. **Pre-Publication Audit Engine**
   - **Deterministic Terminology & Voice Matching:** Zero-hallucination exact and token-boundary compliance auditing against approved/forbidden vocabularies.
   - **Multimodal Factual Verification:** Live claim verification powered by Google Gemini with strict fallback detection.
   - **Visual Identity Compliance:** Color palette distance analysis (CIEDE2000 ΔE) and logo placement verification.
   - **Scoring & Verdicts:** Comprehensive scorecard generating PASS, WARNINGS, or BLOCKED status with rule-linked findings.

3. **Surgical Auto-Remediation & Content Lineage**
   - Single-click, non-destructive replacement engine for identified violations.
   - Strict UTF-8 NFC normalization and boundary-safe offset calculation preventing cascading textual corruption.
   - Deterministic content version forking with parent-child lineage tracking.

4. **Human-in-the-Loop Governance & Separation of Duties**
   - Multi-role RBAC: Workspace Admin, Brand Manager, and Content Creator.
   - Cryptographically enforced **Separation of Duties (SoD)**: Content Creators and submitting Admins cannot approve their own submissions (enforced at both API and PostgreSQL trigger levels).
   - Advisory acknowledgment workflows for non-blocking compliance warnings.

5. **Tamper-Evident v1.1 Compliance Certificates**
   - Cryptographic manifest sealing the exact asset content SHA-256, audit evidence digest, snapshot hash, and reviewer identities.
   - Public unauthenticated verification endpoint (`/api/v1/compliance/verify/{hash}`).
   - Strict non-standard downgrade: Offline demo or unverified factual checks are permanently stamped as `DEMO_COMPLIANCE_CERTIFICATE` with regulatory disclosures and cannot issue standard certificates.

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend Client (SPA)                      │
│               Vite + React 18 + TypeScript + Tailwind           │
└────────────────┬───────────────────────────────┬────────────────┘
                 │ (Bearer JWT / Gotrue)         │ (Direct Auth)
                 ▼                               ▼
┌─────────────────────────────────┐    ┌──────────────────────────┐
│         FastAPI Backend         │    │      Supabase Auth       │
│  - JWT Verification (JWKS)      │    │  - User Management       │
│  - Governance & Audit Pipeline  │    │  - Session Issuance      │
│  - Surgical Remediation Engine  │    └────────────┬─────────────┘
│  - Certificate Minting & Hash   │                 │
└────────────────┬────────────────┘                 │
                 │ (sylvar_app_user via pooler)     │ (RLS Context)
                 ▼                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                 PostgreSQL Database (Supabase)                  │
│  - Row-Level Security (RLS) on all tenant tables                │
│  - Anti-tamper triggers & Separation of Duties DB constraints   │
│  - Partial unique indexes ensuring review state idempotency    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons, Vitest, Testing Library |
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (asyncio), Pydantic v2, SlowAPI, httpx |
| **Database** | PostgreSQL 15+, Supabase (Auth, Gotrue, Pooler), pgvector |
| **AI / Multimodal**| Google Gemini API (`gemini-2.5-flash` / `gemini-3.8-flash`) via `google-genai` |
| **Security** | JWKS-based JWT validation, PostgreSQL RLS, Nonce anti-replay, Canonical JSON SHA-256 |

---

## Repository Structure

```text
.
├── frontend/                   # Production React 18 + TypeScript SPA
│   ├── src/
│   │   ├── components/         # Dashboard, Studio, Living Memory, Review Queue, Auth
│   │   ├── lib/                # API client, auth bindings, error formatting, utils
│   │   └── store/              # Client-side session and workspace state
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
├── backend/                    # Production FastAPI Application
│   ├── app/
│   │   ├── core/               # Configuration, security, JWKS, rate limiting, error handlers
│   │   ├── db/                 # Async database session & base model
│   │   ├── models/             # SQLAlchemy ORM models (Audit, Review, Memory, Client, Workspace)
│   │   └── modules/            # Domain modules (Audits, Reviews, Memory, Documents, Remediation)
│   ├── tests/                  # Pytest test suite (Hardening, Review, Audit, Regression, Memory)
│   └── pyproject.toml
├── supabase/                   # Database Migrations & Operational Scripts
│   ├── migrations/             # Schema migrations (001 through 008)
│   └── ops/                    # Runtime role bootstrapping (sylvar_app_user)
├── docs/                       # Technical Documentation & Architectural Specifications
│   ├── control-pack/           # Product Requirements, Architecture, ADRs, Decision Register
│   ├── reports/                # Audit, verification, and hardening history reports
│   └── examples/               # Sample guidelines and test data
├── .env.example                # Backend configuration template
├── .env.frontend.example       # Frontend configuration template
├── .gitignore                  # Comprehensive secret and build artifact exclusion
└── README.md                   # Project documentation
```

---

## Getting Started

### Prerequisites

- **Node.js:** v18.0.0 or higher
- **Python:** v3.11 or higher
- **Supabase Project:** Configured with PostgreSQL database and Authentication enabled.
- **Google Gemini API Key:** For live factual checking (optional in offline demo evaluation mode).

---

### Backend Setup

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.lock.txt
   # or with pyproject.toml:
   pip install -e .
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Fill in your PostgreSQL `DATABASE_URL`, `SUPABASE_URL`, and `GEMINI_API_KEY`.

5. **Start the backend development server:**
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   The API will be live at `http://localhost:8000`. Probe health: `curl http://localhost:8000/api/v1/health`.

---

### Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Populate `VITE_API_BASE_URL` (`http://localhost:8000`), `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY`.

4. **Start the Vite development server:**
   ```bash
   npm run dev -- --host 0.0.0.0 --port 5173
   ```
   Open `http://localhost:5173` in your browser.

---

### Database Setup & Migrations

Migrations are stored in [`supabase/migrations`](file:///D:/hackathons/codenexus/SYLVAR_ROUND2_REMEDIATED/supabase/migrations) and must be applied sequentially:

1. `001_initial_schema.sql` — Core workspaces, clients, members, and RLS policies.
2. `002_living_memory.sql` — Guideline documents, rule candidates, and memory snapshots.
3. `003_audit_engine.sql` — Content assets, versions, audit runs, checks, and findings.
4. `004_human_review.sql` — Approval requests, review decisions, and compliance certificates.
5. `005_batch1_security_remediation.sql` — RLS tightening, Gotrue user sync triggers, certificate unique constraints.
6. `006_batch2a_invitation_security.sql` — Invitation delivery, verification tokens, security definer functions.
7. `007_batch2a_final_security_correction.sql` — Function ACL hardening and least privilege.
8. `008_batch3_1_governance_hardening.sql` — Separation of duties trigger, partial unique indexes on pending reviews, certificate manifest v1.1.

To bootstrap the least-privilege backend runtime role, run [`supabase/ops/bootstrap_runtime_role.sql`](file:///D:/hackathons/codenexus/SYLVAR_ROUND2_REMEDIATED/supabase/ops/bootstrap_runtime_role.sql) as the database superuser (`postgres`).

---

## Testing & Verification

### Running Backend Tests
The backend test suite executes 38 integration, security, and regression tests:
```bash
cd backend
pytest tests/ -v
```

### Running Frontend Tests & Type Checking
```bash
cd frontend
# Run 76 unit and component tests
npm test -- --run

# Run TypeScript typecheck
npm run type-check

# Run production build
npm run build
```

---

## Security Model

- **Zero Client-Decided Authorization (ADR-009):** The frontend never makes authorization or compliance decisions. All user claims are validated through Supabase JWTs verified against official JWKS keys.
- **PostgreSQL Row-Level Security (RLS):** All client brands, living memory snapshots, and assets are isolated at the database level by workspace and client boundaries.
- **Cryptographic Separation of Duties:** Content Creators cannot self-approve; Admins cannot self-approve assets they authored. Enforced at both FastAPI route dependency layer and PostgreSQL database trigger layer.
- **Manifest Integrity:** Certificates are verifiable offline through deterministic SHA-256 root hashing over canonicalized JSON payloads.

---

## License

Proprietary — Built for CodeNexus Hackathon 2026. All rights reserved.
