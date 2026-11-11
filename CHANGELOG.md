# CHANGELOG — SYLVAR Pre-Publication CI/CD

## [0.3.0] - 2026-11-11 — Release Candidate & Judge Demo Access

### Added
- **Multi-Engine Governance Hardening:**
  - Multimodal visual compliance analyzer (`CIEDE2000` color distance, WCAG 2.1 AA contrast verification).
  - Cross-rule contradiction scanner for proactive guideline conflict detection and resolution.
  - Longitudinal compliance analytics engine tracking temporal pass/block rates and violation trends.
  - Adversarial payload resistance and boundary-safe UTF-8 NFC text sanitization.
- **Judge Demo Access:**
  - One-click judge evaluation panel on login interface routing through standard GoTrue authentication.
  - Dedicated synthetic demo workspace `Aura Botanica Collective` and client brand `Aura Skincare`.
  - Least-privileged `CONTENT_CREATOR` role enforcement preserving Separation of Duties (SoD).
- **Test Baselines:**
  - 194 backend unit, integration, and security tests.
  - 83 frontend Vitest unit and component tests.
  - Full TypeScript `tsc --noEmit` clean build.

---

## [0.2.0] - 2026-11-05 — Round 2 Accelerated Build (Phases 1-5 MVP)

### Added
- **Phase 1 (Foundation & Identity):**
  - Cryptographic asymmetric JWT verification (`JWTVerifier`, `JWKSProvider`, `make_http_fetcher`).
  - Fail-closed auth configuration guard with RFC 9457 Problem Details error handler.
  - Public liveness probe endpoint (`GET /api/v1/health`).
- **Phase 2 (Multi-Tenancy & Authorization):**
  - PostgreSQL DDL schema & RLS policies in `supabase/migrations/001_initial_schema.sql`.
  - Domain models: `User`, `AgencyWorkspace`, `WorkspaceMembership`, `ClientBrand`, `ClientMembership`.
  - 5-Gate authorization pipeline: Gate 1 JWT validation, Gate 2 Workspace membership, Gate 3 Client scoping, Gate 4 RBAC role enforcement (`WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`), Gate 5 Real-time revocation.
- **Phase 3 (Living Brand Memory & Guideline Ingestion):**
  - PostgreSQL DDL schema & RLS policies in `supabase/migrations/002_living_memory.sql`.
  - Domain models: `GuidelineDocument`, `DocumentSection`, `ExtractedCandidate`, `BrandMemoryVersion`, `BrandRule`, `BrandRuleRevision`, `BrandMemorySnapshot`.
  - Candidate rule extractor in 4 categories: `TERMINOLOGY`, `FACT`, `COLOR`, `VOICE`.
  - Memory version activation compiling deterministic SHA-256 JSONB snapshot.
- **Phase 4 (Content Governance Engine & Remediation):**
  - Terminology engine: Unicode NFC normalization, deterministic regex, exact character offset spans.
  - Factual verification engine: Epistemic tri-state outcomes (`SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`).
  - Surgical remediation engine: Non-destructive text replacement maintaining character spans.
- **Phase 5 (Human Review & UI Demonstration):**
  - Review queue with advisory acknowledgments.
  - Compliance certificate generation with verifiable SHA-256 root hash.
  - React + TypeScript dashboard.
