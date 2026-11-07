# CHANGELOG — SYLVAR Pre-Publication CI/CD

## [0.2.0] - 2026-11-05 — Round 2 Accelerated Build (Phases 1-5 MVP)

### Added
- **Phase 1 (Foundation & Identity):**
  - Cryptographic asymmetric JWT verification (`JWTVerifier`, `JWKSProvider`, `make_http_fetcher`).
  - Fail-closed auth configuration guard with RFC 9457 Problem Details error handler.
  - Public liveness probe endpoint (`GET /api/v1/health`).
  - Baseline verification: 69/69 backend tests passed, 44/44 vitest passed, strict mypy/ruff/tsc clean.
- **Phase 2 (Multi-Tenancy & Authorization):**
  - PostgreSQL DDL schema & RLS policies in `supabase/migrations/001_initial_schema.sql`.
  - Domain models: `User`, `AgencyWorkspace`, `WorkspaceMembership`, `ClientBrand`, `ClientMembership`.
  - 5-Gate authorization pipeline: Gate 1 JWT validation, Gate 2 Workspace membership, Gate 3 Client scoping, Gate 4 RBAC role enforcement (`WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`), Gate 5 Real-time revocation.
  - CRUD endpoints for Workspaces, Members, Client Brands, and Client Memberships.
  - Profile discovery endpoint (`GET /api/v1/users/me`).
  - Integration tests in `tests/test_phase2_multi_tenancy.py`.
- **Phase 3 (Living Brand Memory & Guideline Ingestion):**
  - PostgreSQL DDL schema & RLS policies in `supabase/migrations/002_living_memory.sql`.
  - Domain models: `GuidelineDocument`, `DocumentSection`, `ExtractedCandidate`, `BrandMemoryVersion`, `BrandRule`, `BrandRuleRevision`, `BrandMemorySnapshot`.
  - Document safety engine: 20MB payload limit, format detection (TXT, MD, DOCX, PDF), and DOCX zip bomb protection (entry count, uncompressed limit, ratio check).
  - Document parser & candidate rule extractor in 4 categories: `TERMINOLOGY`, `FACT`, `COLOR`, `VOICE`.
  - Brand Manager approval endpoint (`/knowledge/approve`) generating immutable revisions.
  - Memory version activation (`/memory/activate`) compiling deterministic SHA-256 JSONB snapshot and updating active pointer on ClientBrand.
  - Integration tests in `tests/test_phase3_memory.py`.
- **Phase 4 (Content Governance Engine & Remediation):**
  - PostgreSQL DDL schema & RLS policies in `supabase/migrations/003_audit_engine.sql`.
  - Domain models: `ContentAsset`, `AssetVersion`, `AuditRun`, `AuditCheck`, `AuditFinding`, `CorrectionSuggestion`.
  - Terminology engine: Unicode NFC normalization, deterministic regex, exact character offset spans, and surgical correction suggestions.
  - Factual verification engine: Epistemic tri-state outcomes (`SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`) with verbatim substring citation assertions (ADR-005).
  - Visual compliance engine: Linear-light alpha compositing, CIELAB D65 conversion, pure-Python CIEDE2000 color difference formula with advisory-only threshold (ADR-008).
  - Audit orchestrator: In-process concurrent 3-tier execution with exception isolation and Diagnostic Scorecard (`BLOCKED`, `WARNINGS`, `PASS`).
  - Surgical AI remediation engine: Minimal text replacement maintaining character spans, version forking with `created_from_correction_id`, and re-auditing.
  - Integration tests in `tests/test_phase4_audit.py`.
- **Phase 5 (Human Review & UI Demonstration):**
  - PostgreSQL DDL schema & RLS policies in `supabase/migrations/004_human_review.sql`.
  - Domain models: `ApprovalRequest`, `ComplianceCertificate`.
  - Brand Manager review queue with advisory acknowledgments.
  - Immutable compliance certificate generation with SHA-256 hash manifest.
  - Integration tests in `tests/test_phase5_review.py`.
  - React + TypeScript dashboard (`frontend/src/components/Dashboard.tsx`) providing an interactive 12-step golden path for judges.

### Verified Test Evidence
- **Backend Test Suite:** 85/85 pytest tests passing in 6.95s.
- **Backend Static Typing:** Mypy strict passing across 45 files with 0 errors.
- **Backend Linting:** Ruff passing with 0 errors.
- **Frontend Test Suite:** 44/44 Vitest tests passing.
- **Frontend Static Typing:** TypeScript `tsc --noEmit` passing with 0 errors.
- **Frontend Build:** Vite production build passing in 4.36s.
