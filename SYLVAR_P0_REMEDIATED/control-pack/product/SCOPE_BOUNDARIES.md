# SCOPE_BOUNDARIES.md — Ring-Fenced Scope & Progression

## 1. Core MVP Scope (Round 2 Build)
* Multi-client agency workspace partitioning.
* 3-role RBAC (`WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`).
* Direct PostgreSQL data access via SQLAlchemy Async + asyncpg under least-privilege `sylvar_app_user`.
* Supabase Auth integration with cryptographic JWKS JWT verification.
* Multi-format guideline ingestion (TXT, MD, DOCX, text-based PDF) with decompression bomb guards.
* Living Brand Memory with immutable JSONB snapshots and authoritative pointer updates.
* Deterministic regex terminology linter with Unicode NFC normalization.
* Model-assisted atomic factual claim extraction and tri-state NLI verification (`SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`).
* Verbatim substring citation assertion gate.
* Pure-Python Pillow/NumPy CIEDE2000 visual palette analysis with linear-light alpha compositing.
* 3-tier audit execution orchestrator with concurrency locks and heartbeat recovery.
* Surgical AI correction suggestions with visual diffs and version forking.
* Brand Manager human review queue with zero-blocking-issue gate.
* Exportable JSON compliance audit manifests.

## 2. Round 2 Committed Enhancements
* Automated Guideline Contradiction Scanner (Pairwise NLI conflict detection across staged rules).
* Multimodal WCAG 2.1 AA Contrast Engine (Relative luminance math on text-image bounding boxes).
* Longitudinal Mistake Intelligence (SQL aggregation and qualitative root-cause clustering).

## 3. Explicitly Deferred to Future Scope
* Autonomous publishing to social media, CMS, or ad networks.
* Enterprise SAML/Okta SSO and SCIM directory sync.
* Video frame-by-frame and audio transcription auditing.
* Complex OCR for scanned paper documents.
* Vector databases (Chroma, Pinecone, Qdrant).
* Distributed task queues (Celery, Redis) or microservice decompositions.
* Native Figma or Google Docs plugins.
