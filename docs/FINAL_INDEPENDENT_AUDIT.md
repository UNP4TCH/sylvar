# SYLVAR — Final Independent Pre-Submission Audit

**Audit date:** 5 November 2026  
**Audited artifact:** uploaded `sylvar.zip` (114,882,332 bytes; 19,164 ZIP entries)  
**Scope:** source, migrations, tests, configuration, frontend, control-pack and evidence documents  
**Method:** three sequential source-review passes; read-only inspection. No repository files were modified.

## Final verdict

# NOT READY FOR EXTERNAL INTEGRATION

This is an evidence-based source audit, not a production penetration test. The uploaded archive contains meaningful remediation work, but the PostgreSQL tenant-context fix is not correctly implemented, audit paths can still produce misleading PASS outcomes, and the actual image-audit path is not connected. The complete backend test suite could not be executed in this audit environment because `aiosqlite` is absent; the frontend test suite could not be executed because `node_modules` is absent. Python bytecode compilation passed.

The reported Antigravity figures (101 backend tests, 46 frontend tests, type checks, lint and build) are claims recorded in `docs/TEST_EVIDENCE.md`; they were not independently reproduced here.

## 1. Three-pass review record

### Pass 1 — Repository, architecture, control pack and deployment surface
- Inventoried 19,164 ZIP entries and separated source/config/docs from generated directories for inspection.
- Inspected backend module layout, frontend components, four SQL migrations, application startup, environment configuration, lockfiles, README and test evidence.
- Found that the submitted archive includes `backend/.env`, `.git`, `.venv`, `node_modules`, caches and generated artifacts. The `.env` contents were deliberately not opened or reproduced.

### Pass 2 — Authentication, database and tenant isolation
- Traced JWT verification into the authorization dependency pipeline and transaction-local PostgreSQL context setup.
- Read all four migrations and checked tenant tables for RLS enablement and policies.
- Checked ORM enum mappings, database session lifecycle, workspace creation and invitation reconciliation.
- Found a PostgreSQL parameterization defect in `SET LOCAL`, swallowed setup errors, missing explicit runtime-role grants/provisioning in migrations, and an RLS policy that does not permit initial workspace insertion under the current context model.

### Pass 3 — Audit engine, AI evidence, review/certificates, ingestion, frontend and tests
- Traced audit execution from asset creation through engine dispatch and verdict aggregation.
- Inspected factual Gemini adapter and offline fallback, visual analyzer, review decision path, certificate generation, document parser/security checks, frontend API calls and regression tests.
- Found that empty Gemini claim output can result in PASS, image bytes are never supplied by the audit route, audit execution remains synchronous, certificate hashes are not independently verifiable signatures, and sequential state checks are not concurrency-safe.
- Attempted the backend test suite; collection failed before tests ran because `aiosqlite` is unavailable in the audit runtime. `python -m compileall -q backend/app backend/tests` passed.

## 2. Executive summary

### Blocking findings

1. **Tenant context does not reliably reach PostgreSQL.** `pipeline.py` issues `SET LOCAL app.current_* = :parameter`. PostgreSQL `SET` does not accept bind parameters in that position. The exception is caught and logged, and authorization continues. With a direct backend connection that does not carry Supabase `auth.uid()` request claims, the RLS helper then has no authenticated user context.
2. **Workspace creation conflicts with its own RLS policy.** The insert policy on `agency_workspaces` requires the new row ID to equal the current workspace context or already appear through a membership. A newly generated workspace has neither. The route also does not establish user context before the creation flow.
3. **Factual verification can pass when the model omits claims.** The Gemini adapter iterates only returned findings. An empty `findings` array, or omitted draft claims, produces no findings and can return PASS. It does not independently enumerate all factual claims in the draft and reconcile them against model output.
4. **Visual verification is not wired into the real audit path.** The audit trigger calls `execute_audit(..., image_bytes=None)` and the asset model/API does not accept image bytes or a durable image reference. The visual engine therefore reports skipped and the orchestrator treats skipped visual execution as PASS. IMAGE/HYBRID assets are not genuinely audited visually.
5. **Certificates are hashes, not independently verifiable signatures.** The backend stores a SHA-256 hash alongside a mutable JSON payload, but the source does not expose a verifier that recomputes the hash or provide a signing key/signature. Database-level immutability is not enforced by a trigger or append-only permission model.
6. **Review decisions are not concurrency-safe.** The route checks PENDING, then later updates the row and creates a certificate. There is no atomic conditional update/row lock/version check and no unique constraint on `compliance_certificates.approval_request_id`.
7. **Audit jobs are not durable background executions.** `trigger_audit` awaits the full engine run in the request transaction. There is no persisted attempt/heartbeat/worker recovery model. M-03 remains unresolved.
8. **Production DB configuration silently falls back to local SQLite.** `get_engine()` uses `sqlite+aiosqlite:///./sylvar_dev.db` when `DATABASE_URL` is absent or a placeholder, without rejecting that configuration in production.

## 3. Original finding verification matrix

Status reflects the source in the uploaded archive, not the implementation agent's completion report.

| ID | Status | Evidence / assessment | Required action |
|---|---|---|---|
| C-01 | **UNFIXED** | `backend/app/modules/auth/pipeline.py:40-68` uses bound parameters in `SET LOCAL`; catches `SQLAlchemyError` and continues. | Replace with parameter-safe transaction-local `set_config(..., true)`; fail closed if context setup fails; PostgreSQL integration test. |
| C-02 | **PARTIALLY FIXED** | Migrations 001–004 now use `public.current_app_*` helpers rather than relying exclusively on `auth.uid()`. Those helpers depend on context that C-01 currently fails to set. No PostgreSQL RLS runtime proof supplied. | Fix C-01 and test all policies using the actual runtime DB role and two tenants. |
| C-03 | **PARTIALLY FIXED** | Migrations revoke privileges from `anon` and `authenticated` (migration 001:191–203), but do not create/provision `sylvar_app_user` or grant it required table/sequence/function privileges. No `ALTER DEFAULT PRIVILEGES` or deployed role/grant evidence is present. | Add reproducible least-privilege role/grant provisioning and verify Supabase Data API exposure and runtime role. |
| C-04 | **FIXED IN SOURCE; RUNTIME UNVERIFIED** | ORM models use native `SAEnum`, `create_type=False` and enum-value mapping in `models/client.py`, `document.py`, `memory.py`, `workspace.py`. No live PostgreSQL schema comparison was possible. | Keep; validate migration/model round-trips against PostgreSQL. |
| C-05 | **UNFIXED** | `orchestrator/runner.py:62-87` treats missing text/image as skipped PASS. `audits/router.py:284-295` passes `image_bytes=None` unconditionally. Required modalities can be skipped without blocking. | Make engine applicability explicit by content type; required engine skip/failure must fail closed; wire image storage/input. |
| C-06 | **PARTIALLY FIXED** | `engine_factual/verifier.py:216-258` returns FAIL on live Gemini exceptions when a key exists, but without a key it falls back to a heuristic which can return PASS. | Enforce production configuration; label offline result as non-authoritative and prevent compliance PASS where factual verification is required. |
| C-07 | **PARTIALLY FIXED** | `reviews/router.py:110-134` checks audit workspace/client, asset and exact version and requires COMPLETED. DB-level constraints do not bind audit/asset/version relationships as one composite relationship. | Add composite constraints where practical and regression tests for cross-linked IDs and concurrent submissions. |
| C-08 | **PARTIALLY FIXED** | `reviews/router.py:265-307` rejects non-PENDING decisions sequentially. It does not lock the row or perform `UPDATE ... WHERE status='PENDING'`; certificates have no unique constraint on approval request. | Atomic conditional transition, row lock or version check; unique certificate-per-request constraint; concurrent test. |
| M-01 | **PARTIALLY FIXED** | `auth/dependencies.py:48-102` reconciles by email only and is invoked from workspace creation. It does not require an explicit `email_verified` claim, and no complete Supabase invitation acceptance flow is visible. | Verify email ownership or use provider invitation identity; run sync in authenticated bootstrap; test unverified-email collision. |
| M-02 | **PARTIALLY FIXED** | `GET /workspaces` exists (`workspaces/router.py:31-61`) and Dashboard calls `/api/v1/workspaces`. Actual product path remains blocked by C-01 and workspace creation RLS policy. No browser E2E. | Fix auth/RLS and run actual UI/API journey. |
| M-03 | **UNFIXED** | `audits/router.py:284-299` awaits `execute_audit` inline. No durable attempt entity, worker queue, heartbeat, restart recovery or audit polling lifecycle is present. | Persist attempt state and recovery or explicitly scope MVP to synchronous bounded audits; don't claim durability. |
| M-04 | **PARTIALLY FIXED** | `engine_visual/analyzer.py:160-193` discards alpha<32 but does not perform the ADR-described linear-light compositing for partially transparent pixels. | Implement correct alpha compositing or revise documented algorithm and add semi-transparent pixel tests. |
| M-05 | **PARTIALLY FIXED** | `main.py:48-75` registers SlowAPI middleware and `limiter.py` has default limits. Body limit trusts Content-Length; requests without it can evade the 25 MB guard. Test uses a separate local limiter, not the application instance. | Enforce streaming byte count independent of header; test actual app middleware and proxy behaviour. |
| M-06 | **FIXED IN SOURCE** | Gemini factual calls use `asyncio.to_thread` (`verifier.py:220-222`); extraction uses `asyncio.to_thread` (`gemini_extractor.py:124-130`). | Keep; consider bounded executor/timeouts under load. |
| M-07 | **PARTIALLY FIXED** | Candidate update path validates some statuses/payloads, but full category-specific required-key/value validation before promotion to authoritative rules was not established. | Validate canonical payload schema per category before approval/activation. |
| M-08 | **PARTIALLY FIXED** | Memory activation uses row locking per implementation report, but no PostgreSQL concurrency test or transaction-level proof was available. | Test concurrent activation with PostgreSQL; verify single-active-version invariant at DB level. |
| M-09 | **PARTIALLY FIXED** | `reviews/router.py:274-301` checks submitted IDs against non-critical finding IDs and requires all to be acknowledged. It records IDs but not a distinct acknowledgement event/actor/time; acknowledgement is asserted by the deciding reviewer. | Decide whether reviewer decision itself constitutes acknowledgement; otherwise persist explicit acknowledgement records and actor/time. |
| M-10 | **UNFIXED** | `gemini_verifier.py:108-189` validates returned citations, but no completeness check compares returned claims to all claims in draft. Empty/incomplete model findings can lead to PASS. Prompt delimiters/instructions alone are not a complete prompt-injection defence. | Independently extract claims and reconcile one-to-one; omissions => UNVERIFIED; add adversarial tests. |
| M-11 | **PARTIALLY FIXED** | `matcher.py` adds NFC normalization and lookaround boundaries. If normalization changes codepoint length, returned offsets may not map to original source; further edge-case tests are needed. | Maintain normalized-to-original offset map; validate regex/terms and test punctuation, Unicode and combining characters. |
| M-12 | **PARTIALLY FIXED** | `remediation/engine.py` replaces one occurrence, but `replace(..., 1)` does not prove the intended span is uniquely identified; identical repeated phrases can cause the wrong occurrence to be changed. | Apply by validated finding offsets against exact immutable source version; verify lineage and hash. |
| M-13 | **PARTIALLY FIXED** | DOCX entry/size/ratio guards and PDF 100-page cap exist. Upload is read into memory; PDF fallback returns placeholder text when no text can be extracted (`parser.py:140`); XML uses standard `ElementTree`. | Return explicit unsupported/OCR-required status for no-text PDFs; use hardened XML parsing; stream/bound uploads and test malformed/archive-bomb inputs. |
| M-14 | **UNFIXED** | `db/session.py:23-26` silently falls back to local SQLite when DATABASE_URL is unset/placeholder, including production. | Fail startup in production without a valid PostgreSQL URL; health/readiness must check DB. |
| M-15 | **UNFIXED** | `pipeline.py:53-64` uses invalid parameterized SET LOCAL syntax; lines 66-68 suppress the failure. | Fix context setup, do not swallow failure, add transaction/pool reuse tests on PostgreSQL. |
| M-16 | **PARTIALLY FIXED** | Eight tests in `test_remediation_suite.py` cover a subset of findings. No PostgreSQL RLS suite, browser E2E or concurrency tests were found. | Map every finding to targeted regression tests and add DB/E2E/concurrency suites. |

## 4. New findings

### N-01 — Workspace creation is incompatible with current RLS insert policy
**Severity: Critical / integration blocker**  
`supabase/migrations/001_initial_schema.sql:148-156` defines `agency_workspaces` `FOR ALL USING` as `id = current_app_workspace_id()` or an existing membership. A new workspace ID cannot satisfy either branch before the workspace and membership exist. `workspaces/router.py:70-104` inserts the workspace and membership without first setting transaction-local user context. Even after fixing C-01, the workspace row insert needs an explicit safe bootstrap policy or narrowly scoped provisioning function.

### N-02 — Image/HYBRID audit is not implemented end-to-end
**Severity: Critical product-integrity blocker**  
`AssetCreateRequest` accepts content type and text only (`audits/router.py:26-32`). The audit trigger passes `image_bytes=None` (`audits/router.py:284-295`). The visual engine therefore reports skipped and the runner treats that as PASS. An IMAGE/HYBRID asset can receive a successful-looking audit without visual evaluation.

### N-03 — Certificate hash is not a verifiable certificate signature
**Severity: High**  
`reviews/router.py:320-349` hashes a canonical JSON payload and stores the hash and payload. There is no verification route/function that recomputes and compares it, no digital signature, and no DB trigger/append-only constraint preventing mutation. A plain hash stored beside the payload does not authenticate issuer or prevent a privileged writer from replacing both.

### N-04 — Review decision race and duplicate certificates
**Severity: High**  
`reviews/router.py:265-307` performs read-then-write state checking. `models/review.py:83-117` does not declare `approval_request_id` unique, despite the relationship being `uselist=False`. Parallel approval/rejection requests can race and potentially issue multiple certificates or overwrite a decision.

### N-05 — Submitted archive contains a backend `.env`
**Severity: High operational/security hygiene**  
The uploaded ZIP contains `sylvar-phase1/backend/.env`, as well as `.git`, `.venv`, `node_modules` and caches. I did not inspect or disclose `.env` contents. Do not send this archive to another reviewer or publish it. If it contains live credentials, rotate them before external integration. Create a fresh source-only archive excluding `.env`, `.git`, virtual environments, dependencies, build output and caches.

### N-06 — Runtime DB role is not reproducibly provisioned by migrations
**Severity: High / integration blocker**  
The migrations revoke privileges from `anon` and `authenticated`, but the supplied migration set does not create `sylvar_app_user` or grant the runtime role required table, sequence and routine privileges. Actual role grants and bypass-RLS flags cannot be verified from source alone.

### N-07 — Health endpoint is liveness-only, not readiness
**Severity: Medium**  
The health route returns a liveness response; no evidence shows it checks database connectivity, migration state or required provider configuration. HTTP 200 does not prove the system can perform its workflow.

### N-08 — Upload and parser resource handling remains incompletely bounded
**Severity: Medium–High**  
The upload handler reads the entire file into memory before parsing. A Content-Length-only middleware can be bypassed by requests without that header. DOCX XML is parsed with standard `xml.etree.ElementTree`; PDF extraction has placeholder fallback text for no-text documents. These issues need adversarial tests and clearer failure semantics.

## 5. Security assessment

### Authentication
- Positive: JWT verifier allow-lists asymmetric algorithms and validates issuer/audience/signature/expiry; JWKS cache and refresh code exists.
- Not proven: real Supabase-issued token compatibility, real JWKS rotation and production issuer/audience configuration.
- Concern: invitation reconciliation trusts matching JWT email without an explicit `email_verified` check in the inspected path.

### Tenant isolation / PostgreSQL RLS
- **Not verified and currently blocked by source defect.** No live PostgreSQL was available.
- Parameterized `SET LOCAL` is not valid PostgreSQL parameter syntax and errors are swallowed.
- Workspace creation's RLS insert condition is unsatisfied for a new workspace.
- The migration set does not provision the runtime role/grants.
- SQLite test evidence cannot establish RLS behaviour.

### Authorization
- Positive: client assignment is separately checked from workspace membership in the application authorization pipeline.
- Remaining: DB constraints do not encode all cross-resource relationships, and the authorization pipeline's context setup is unreliable until C-01 is fixed.

### Rate limiting / request size
- Global SlowAPI middleware/default limit is configured.
- The body-size middleware trusts Content-Length; absent/incorrect headers can evade this check. In-memory limits are per process and rely on correct proxy/IP configuration.

### Secrets
- Archive includes `backend/.env`; content not inspected. Do not redistribute this archive. Rotate any live keys that were included.

## 6. AI and audit integrity

- Gemini live provider exceptions are converted to FAIL when a non-placeholder API key is configured.
- Offline mode remains heuristic and can return PASS. This must be explicitly non-authoritative in production.
- Citation validation only checks claims the model returns. It does not prove the model returned every factual claim in the draft.
- Prompt instructions and XML-like delimiters are not a complete prompt-injection defence.
- The visual engine implementation does not match the documented linear-light alpha-compositing method for partially transparent pixels.
- The orchestrator currently interprets missing modality as skipped PASS, while the route always supplies no image bytes.

## 7. Human review and certificate assessment

- Positive: submission checks audit status, client/workspace, asset and exact asset version; terminal decisions are rejected on sequential repeat; acknowledgement IDs are checked against audit findings.
- Remaining: no atomic concurrency guard; certificate-per-review uniqueness is not enforced; no cryptographic signature or independent verification endpoint; audit relationships are not fully constrained at DB level.

## 8. Golden-path assessment

| Workflow step | Source-level assessment |
|---|---|
| Register/sign in | Frontend Supabase auth code exists; live provider integration not tested. |
| Create/access workspace | **Blocked** by invalid tenant context and workspace creation RLS policy. |
| Create client brand | Route exists; depends on working tenant context and DB role. |
| Upload guidelines | Route and parser exist; live Gemini/provider and resource-limit behaviour not tested. |
| Extract/approve rules | APIs exist; category-specific validation and provider integration need further proof. |
| Submit content | Text asset API exists. IMAGE/HYBRID payload path is incomplete. |
| Run audit | Synchronous route exists; image path is absent; factual model completeness is not guaranteed. |
| Inspect diagnostics | API/frontend components exist; actual integrated run not tested. |
| Remediate/re-audit | Version-fork logic exists; span targeting can select the wrong duplicate occurrence. |
| Submit for review | Exact version/audit checks exist. |
| Approve/reject | Sequential state check exists; concurrency race remains. |
| Generate certificate | JSON/hash generated; not an issuer-authenticated signature and not independently verified. |

**Conclusion:** The source demonstrates substantial workflow scaffolding, but the end-to-end golden path is not proven and is blocked at workspace creation on the current PostgreSQL/RLS design.

## 9. Test evidence and reproducibility

| Check | Result in this audit |
|---|---|
| ZIP/source inventory | Completed; 19,164 archive entries |
| Python `compileall` | **PASS** (`backend/app`, `backend/tests`) |
| Backend `pytest` | **NOT RUN** — collection stopped: `ModuleNotFoundError: No module named 'aiosqlite'` |
| Frontend Vitest | **NOT RUN** — frontend `node_modules` not present in extracted review copy |
| Frontend type-check/build | Not independently run |
| mypy/Ruff | Not independently run |
| PostgreSQL migrations/RLS | Not run; no PostgreSQL connection supplied |
| Supabase Auth/JWKS | Not run; no live project/token supplied |
| Gemini live | Not run; no live credential supplied |
| Browser E2E | Not run; no running integrated deployment supplied |

The test report claims 101/101 backend and 46/46 frontend tests. Those numbers are not disproved by this audit, but they are not independently reproduced. The suite lacks PostgreSQL RLS, review-concurrency, missing-claim completeness and full golden-path browser evidence.

## 10. Deployment readiness

**Not ready.** Production configuration currently permits silent SQLite fallback. Database role/grants and migration execution are not reproducible from the supplied migration set. The health probe is liveness-only. Real Supabase, Gemini and deployed CORS/proxy behaviour have not been exercised.

## 11. Prioritized corrective actions

### P0 — Must fix before any external integration
1. Replace parameterized `SET LOCAL` with parameter-safe `set_config(..., true)` and fail closed on context errors.
2. Redesign and test safe first-workspace creation under RLS.
3. Add PostgreSQL role/grant provisioning and prove the role is least-privilege and does not bypass RLS.
4. Make required engine applicability explicit; never PASS a required skipped engine.
5. Wire image upload/storage into asset versions and visual audit, or disallow IMAGE/HYBRID types in the MVP UI/API until implemented.
6. Add independent factual-claim completeness detection; model omission must become UNVERIFIED/blocked.
7. Fail startup in production when DATABASE_URL is missing/placeholder; add DB readiness check.

### P1 — Must fix before submission
8. Make review decisions atomic and enforce one certificate per approval request.
9. Add certificate verification (recompute canonical hash) and define tamper/issuer authenticity; enforce append-only/immutable storage semantics.
10. Verify invite email ownership before identity reconciliation and complete the actual invite acceptance flow.
11. Enforce request body limits while streaming, independent of Content-Length; harden XML/PDF handling and reject unextractable content rather than using placeholder text.
12. Correct alpha compositing and preserve original-text offsets through Unicode normalization.
13. Apply remediation by exact source offsets and immutable version hash.
14. Add PostgreSQL integration, concurrency, Gemini omission/prompt-injection and browser golden-path tests.

### P2 — Operational polish
15. Add durable audit attempts/recovery or explicitly document synchronous MVP limits and strict request timeouts.
16. Add deployment-specific readiness, proxy-aware rate-limit configuration, migration checks, observability and operator setup docs.
17. Rebuild the review archive as source-only and ensure no `.env`, `.git`, `.venv`, `node_modules`, caches or build output are included.

## 12. Limits and confidence

This audit is based on the uploaded ZIP only. It does not inspect the user's local working tree after the archive was created, live Supabase project settings, actual database grants, deployed environment variables, live Gemini model availability or public deployment. The ZIP includes Git metadata, but no attempt was made to treat uncommitted local state outside the archive as audited.

**High confidence:** source-level `SET LOCAL` parameterization defect; swallowed context errors; workspace insert/RLS mismatch; omitted Gemini claims can yield PASS; image bytes always passed as `None`; synchronous audit execution; SQLite production fallback; missing certificate uniqueness/verification; archive contains `.env`.

**Requires runtime confirmation:** exact production RLS outcome after context correction, real Supabase role privileges, email verification claim semantics in the configured auth project, proxy/body-limit behaviour, live Gemini response/model compatibility and deployed golden path.

---

## Final verdict

**NOT READY FOR EXTERNAL INTEGRATION**

The remediation pass improved the codebase, but core PostgreSQL authorization setup and audit-integrity gaps remain. Fix the P0 items, verify them against a real PostgreSQL test database, then rerun an independent audit before connecting production services.
