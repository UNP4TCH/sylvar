# SYLVAR — The Pre-Publication CI/CD for Brand Integrity

> **Create with confidence. Publish with integrity.**  
> SYLVAR is an enterprise-grade brand governance platform that acts as an automated continuous-compliance gate in the publishing lifecycle. It bridges creative content generation and enterprise brand integrity by enforcing strict terminology, epistemic factual truth, visual identity guidelines, and human-in-the-loop review workflows before publication.

---

## Live Deployments

* **Public Web Application:** [https://sylvar-green.vercel.app/](https://sylvar-green.vercel.app/)
* **Public Backend API:** [https://sylvar-api.onrender.com](https://sylvar-api.onrender.com)
* **API Health Check:** `https://sylvar-api.onrender.com/api/v1/health`

---

## The Problem SYLVAR Solves

In modern omnichannel enterprises, creative agencies and marketing teams produce high volumes of collateral across distributed workflows. When governance is manual or reactive, brand guidelines become shelfware, resulting in:
1. **Brand Drift:** Inconsistent voice, off-palette visual assets, and banned terminology slipping into production.
2. **Regulatory & Factual Risk:** Ungrounded performance claims, hallucinations, and unsubstantiated product statistics.
3. **Internal Guideline Contradictions:** Conflicting rules authored by disparate teams over time without centralized conflict resolution.
4. **Lack of Cryptographic Accountability:** Absence of verifiable audit trails proving compliance at time of publication.

**SYLVAR solves this by positioning automated compliance checks directly into the pre-publication pipeline — operating as a CI/CD gatekeeper for brand integrity.**

---

## Key Features & Differentiators

### 1. Living Brand Memory Engine
* Ingests unstructured brand guidelines (`.md`, `.txt`, `.pdf`, `.docx`).
* Extracts and deduplicates candidate rules into structured categories: Terminology, Factual Ground Truth, Visual Identity, and Regulatory Disclaimers.
* Brand Managers review, refine, and approve rules into versioned, immutable **Brand Memory Snapshots** sealed with SHA-256 cryptographic digests.

### 2. Multi-Engine Pre-Flight Audit Pipeline
* **Deterministic Terminology Engine:** Zero-hallucination exact and token-boundary regex auditing with UTF-8 NFC normalization against approved and forbidden vocabularies.
* **Epistemic Factual Verifier:** Powered by Google Gemini with strict claim grounding against approved brand ground-truth snapshots. Never hallucinates passing checks.
* **Multimodal Visual Compliance:** Automated palette extraction, CIEDE2000 color distance calculation ($\Delta E_{00}$), and WCAG 2.1 AA contrast ratio verification.
* **Guideline Contradiction Scanner:** Cross-rule semantic similarity scanning that flags internal guideline conflicts for human resolution before they cause audit failures.
* **Unified Compliance Scorecard:** Clear distinction between overall audit verdicts (`PASS`, `WARNINGS`, `BLOCKED`), individual engine results, advisory warnings, and blocking violations.

### 3. Surgical Auto-Remediation & Content Lineage
* Single-click, boundary-safe replacement engine for identified terminology violations.
* Non-destructive text diffs preventing cascading textual corruption.
* Deterministic content version forking with parent-child lineage tracking.

### 4. Human-in-the-Loop Governance & Separation of Duties (SoD)
* Role-based access control: `WORKSPACE_ADMIN`, `BRAND_MANAGER`, and `CONTENT_CREATOR`.
* **Cryptographic Separation of Duties (ADR-003):** Content Creators and submitting authors cannot approve their own submissions. Enforced at both the FastAPI route authorization layer and PostgreSQL database trigger layer.
* Advisory acknowledgment workflows for non-blocking visual/contrast warnings prior to approval.

### 5. Verifiable Compliance Certificates
* Issues canonical JSON compliance certificates sealing the asset content hash, audit evidence digest, active brand memory snapshot hash, and reviewer signatures.
* Offline verifiable via deterministic SHA-256 digest computation over canonicalized payload structures.

### 6. Longitudinal Compliance Analytics
* Executive KPIs: Total audits, pass rate, block rate, warning rate, and affected asset tracking.
* Temporal violation breakdown and recurring failure analysis.
* Strict epistemic separation between observed historical facts and advisory AI recommendations.

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend Client (SPA)                      │
│               Vite + React 18 + TypeScript + Tailwind           │
└────────────────┬───────────────────────────────┬────────────────┘
                 │ (Bearer JWT / GoTrue)         │ (Direct Auth)
                 ▼                               ▼
┌─────────────────────────────────┐    ┌──────────────────────────┐
│         FastAPI Backend         │    │      Supabase Auth       │
│  - 5-Gate Authorization Pipeline│    │  - User Management       │
│  - Multi-Engine Audit Pipeline  │    │  - Session Issuance      │
│  - Contradiction Scanner        │    └────────────┬─────────────┘
│  - Surgical Remediation Engine  │                 │
│  - Certificate Minting & Hash   │                 │
└────────────────┬────────────────┘                 │
                 │ (sylvar_app_user via pooler)     │ (RLS Context)
                 ▼                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                 PostgreSQL Database (Supabase)                  │
│  - Dual-tenant Row-Level Security (RLS) on all tables           │
│  - Anti-tamper triggers & Separation of Duties DB constraints   │
│  - Partial unique indexes ensuring review state idempotency    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 18 / 19, TypeScript, Vite, Tailwind CSS, Lucide Icons, Vitest, Testing Library |
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (asyncio), Pydantic v2, SlowAPI, httpx |
| **Database** | PostgreSQL 15+, Supabase (Auth, GoTrue, Supavisor Pooler), pgvector |
| **AI / Multimodal**| Google Gemini API (`gemini-2.5-flash` / `gemini-3.8-flash`) via official SDK |
| **Security** | JWKS-based JWT validation, PostgreSQL RLS, Nonce anti-replay, Canonical JSON SHA-256 |

---

## Repository Structure

```text
.
├── frontend/                   # Production React + TypeScript SPA
│   ├── src/
│   │   ├── components/         # Studio, Living Memory, Review Queue, Visual, Analytics
│   │   ├── lib/                # API client, auth bindings, error handling, utils
│   │   └── store/              # Client-side session and workspace state
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
├── backend/                    # Production FastAPI Application
│   ├── app/
│   │   ├── core/               # Security, JWKS, rate limiting, error handlers
│   │   ├── db/                 # Async database session & base model
│   │   ├── models/             # SQLAlchemy ORM models (Audit, Review, Memory, Client, Workspace)
│   │   └── modules/            # Domain modules (Audits, Reviews, Memory, Documents, Visual, Contradictions, Analytics)
│   ├── tests/                  # Pytest test suite (194 tests)
│   └── pyproject.toml
├── supabase/                   # Database Migrations & Operational Scripts
│   ├── migrations/             # Schema migrations (001 through 008)
│   └── ops/                    # Runtime role bootstrapping (sylvar_app_user)
├── docs/                       # Public Documentation
│   └── examples/               # Sample guidelines and test data
├── .env.example                # Backend configuration template
├── .env.frontend.example       # Frontend configuration template
├── .gitignore                  # Secret and build artifact exclusion
└── README.md                   # Project documentation
```

---

## Getting Started

### Prerequisites

* **Node.js:** v18.0.0 or higher
* **Python:** v3.11 or higher
* **Supabase Project:** Configured with PostgreSQL database and Authentication enabled.
* **Google Gemini API Key:** For live factual and visual compliance verification.

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
   Fill in your PostgreSQL `DATABASE_URL`, `SUPABASE_URL`, and `GEMINI_API_KEY` (using `.env.example` as a template).

5. **Start the backend server:**
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   Health check: `curl http://localhost:8000/api/v1/health`

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
   npm run dev
   ```
   Open `http://localhost:5173` in your browser.

---

### Database Setup & Migrations

Migrations are stored in [`supabase/migrations`](file:///D:/hackathons/codenexus/SYLVAR_CICD/supabase/migrations) and should be applied sequentially:

1. `001_initial_schema.sql` — Core workspaces, clients, members, and RLS policies.
2. `002_living_memory.sql` — Guideline documents, rule candidates, and memory snapshots.
3. `003_audit_engine.sql` — Content assets, versions, audit runs, checks, and findings.
4. `004_human_review.sql` — Approval requests, review decisions, and compliance certificates.
5. `005_batch1_security_remediation.sql` — RLS tightening, GoTrue user sync triggers, certificate unique constraints.
6. `006_batch2a_invitation_security.sql` — Invitation delivery, verification tokens, security definer functions.
7. `007_batch2a_final_security_correction.sql` — Function ACL hardening and least privilege.
8. `008_batch3_1_governance_hardening.sql` — Separation of duties trigger, partial unique indexes, certificate manifest v1.1.

---

## Testing & Quality Verification

### Backend Test Suite (194 Tests)
```bash
cd backend
pytest tests/ -v
```

### Frontend Test Suite (83 Tests) & Production Build
```bash
cd frontend
# Unit & integration tests
npm test

# TypeScript type check
npm run build
```

---

## Security Model

* **Zero Client-Decided Authorization (ADR-009):** The frontend never makes authorization or compliance decisions. All claims are validated through Supabase JWTs verified against official JWKS keys.
* **PostgreSQL Row-Level Security (RLS):** All client brands, living memory snapshots, and assets are isolated at the database level by workspace and client boundaries via the least-privileged `sylvar_app_user` role.
* **Separation of Duties (SoD):** Enforced at both the API dependency layer and PostgreSQL database trigger layer (`check_separation_of_duties`).
* **Certificate Integrity:** Manifests are verifiable offline through deterministic SHA-256 root hashing over canonicalized JSON payloads.

---

## License

MIT License — see LICENSE for details.
