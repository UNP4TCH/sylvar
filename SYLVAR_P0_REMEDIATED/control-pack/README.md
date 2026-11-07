# SYLVAR — AI Agent Control Pack
**Version:** 1.0.0  
**Phase State:** Round 1 (PLAN) CLOSED | Round 2 (BUILD) NOT STARTED — PENDING EXPLICIT USER APPROVAL  
**Target:** AI Coding Agents & Engineering Team  
**Architecture:** FastAPI Modular Monolith + React Vite TS + Supabase PostgreSQL  

---

## 1. Purpose of this Control Pack
Naming status: **SYLVAR is a working product name only**; trademark, domain, and software-name clearance remain pending. Inkloom AI is the hackathon problem-statement provider, not the product name.

This directory constitutes the project control pack and operational baseline for building **SYLVAR** (The Pre-Publication CI/CD for Brand Integrity). It translates the approved architectural specifications (System v1.2, Data v1.5, AI v1.5, Security/API v1.6, and Master PRD v1.0.0) into deterministic instructions, governance rules, architectural contracts, development roadmaps, and verification test suites.

Any autonomous AI coding agent (e.g., Claude Code, Cursor, Windsurf, Devin) or human developer MUST follow the protocols established in this pack.

---

## 2. Reading Order for AI Agents
Before inspecting codebase files or executing terminal commands, an agent must read files in this exact sequence:
1. `AGENT.md`: Operational manual, session bootstrap procedure, safety boundaries.
2. `RULES.md`: Non-negotiable engineering rules, anti-patterns, and zero-tolerance violations.
3. `MEMORY.md`: Persistent system invariants, stack parameters, and active baseline context.
4. `PHASE.md`: Active development phase lifecycle, prerequisites, and exit gates.
5. `TASKS.md`: Granular work register, dependency graphs, and execution status.
6. `architecture/ARCHITECTURE.md`: High-level system structure and component boundaries.
7. `product/MASTER_PRD.md`: Full product requirements and epistemic factual model.

---

## 3. Strict Development Constraints
* **Exactly Three User Roles:** `WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`. No fourth role.
* **Dual-Tenant Boundary:** `workspace_id` (Agency) -> `client_id` (Brand). Client brand assignment is strictly required for client-scoped operations. Workspace Admins do not bypass client assignment for client operations.
* **Database Access:** Direct PostgreSQL connection via `SQLAlchemy Async` + `asyncpg`. Dedicated least-privilege application role (`sylvar_app_user`) without `BYPASSRLS`.
* **Tenant Isolation:** Parameterized queries + transaction-local session variables (`SET LOCAL app.current_workspace_id = ...`) + RLS defense-in-depth.
* **Audit Execution States:** `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `INTERRUPTED`. Never use `QUEUED`.
* **Audit Outcomes:** `PASS`, `WARNINGS`, `BLOCKED`.
* **Factual Verification Outcomes:** `SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`. `UNVERIFIED` does not mean false.
* **Zero-Action AI Boundary:** Models evaluate and suggest; AI never approves content, activates memory, or modifies permissions.
* **Pinned Snapshot Lineage:** Audits evaluate strictly against the immutable memory snapshot pinned at creation (`memory_snapshot_id`).
* **Retries:** New physical execution attempt (`audit_execution_attempts`) under same logical audit run (`audit_runs`). Same pinned snapshot. Never merge findings across attempts.
* **Hardware & Budget:** 8 GB RAM, Intel i3-1215U, Windows 11 compatibility. Cloud-first Supabase DB by default. Zero Redis, Celery, microservices, or vector databases.

---

## 4. Current Project State
* **Round 1 (Planning & Specification):** CLOSED / ARCHIVED.
* **Agent Control Pack:** GENERATED & VALIDATED.
* **Round 2 (Implementation / Build):** **NOT STARTED**.
* **Authorization Status:** **BLOCKED** — Waiting for explicit user prompt authorizing Round 2 implementation.


## 5. Authority and Known Verification Gates
Binding decisions in `DECISIONS.md` and invariants in `RULES.md` take precedence over conflicting prose in the PRD or API catalogue. The binding addendum in `product/MASTER_PRD.md` resolves known conflicts. `references/OPEN_QUESTIONS.md` lists implementation-blocking verification gates.

The database catalogue is not yet executable DDL; API endpoint catalogue entries are not yet complete OpenAPI/DTO contracts. Do not invent missing details. Complete and verify these contracts before dependent implementation.

## 6. Freeze and Authorization
This is a frozen planning baseline candidate, not proof that the system has been implemented or tested. Round 2 remains NOT STARTED. No code, migrations, deployments or external service mutations are authorized until the user explicitly authorizes Round 2.
