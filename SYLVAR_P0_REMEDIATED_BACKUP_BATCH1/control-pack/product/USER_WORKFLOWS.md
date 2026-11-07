# USER_WORKFLOWS.md — Detailed User Journeys & State Machines

## 1. Guideline Upload to Living Memory Publication
1. Brand Manager navigates to client brand space -> Brand Knowledge.
2. Clicks "Upload Guideline", selects `Brand_Guide_2026.pdf`.
3. Ingestion pipeline validates MIME magic bytes, stores file in private bucket, extracts text sections.
4. Background Gemini task extracts candidate entities into `extracted_candidates` (`PENDING_REVIEW`).
5. Brand Manager reviews candidates in staging queue, edits wording, approves valid rules, rejects duplicates.
6. Brand Manager clicks "Publish Memory Release (v1.0)".
7. System inserts `brand_memory_versions`, commits `brand_memory_snapshots` JSONB payload with SHA-256 hash, and transactionally updates `client_brands.active_memory_version_id`.

## 2. Pre-Flight Content Submission, Remediation & Review
1. Content Creator selects active client brand, enters ad copy, attaches display banner PNG.
2. Clicks "Run Pre-Flight Audit".
3. System creates `audit_runs` pinned to active `memory_snapshot_id`. Creates `audit_execution_attempts` (Attempt #1, `RUNNING`). Returns `HTTP 202 Accepted`.
4. Orchestrator executes Terminology, Factual NLI, and Visual checks concurrently via `asyncio.gather`.
5. Scorecard renders: Terminology flags prohibited term (`BLOCKING`); Factual flags contradicted claim (`BLOCKING`); Visual flags off-palette accent (`ADVISORY`). Overall outcome: `BLOCKED`. Asset state: `ISSUES_FOUND`.
6. Creator clicks "Generate Fix" on contradicted claim. Model generates minimal-edit rewrite. Creator reviews side-by-side diff and clicks "Accept Fix & Re-Audit".
7. System forks asset version v1.1 (`created_from_correction_id` linked). Original v1.0 preserved. Delta re-audit executes.
8. Re-audit clears blocking issues. Overall outcome: `WARNINGS`. Asset moves to `READY_FOR_REVIEW`.
9. Creator submits asset for review with justification note. Asset moves to `UNDER_REVIEW`.
10. Brand Manager opens review queue, reviews findings and note, acknowledges advisory, and clicks "Approve". Asset moves to `APPROVED`. Compliance audit record committed to `audit_history`.
