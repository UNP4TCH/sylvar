# API_DESIGN.md — Complete RESTful API Catalogue
**Base Path:** `/api/v1`  
**Reference:** Task 5 Security & API Specification v1.6  
**Format Standard:** JSON request/response; RFC 9457 Problem Details for all error envelopes.  

---

## 1. API Protocol & Conventions
* **Authentication:** `Authorization: Bearer <jwt_access_token>`.
* **Tenant Scoping:** All client routes include `{workspace_id}` and `{client_id}` in the URL path.
* **Idempotency:** State-mutating endpoints accept an optional `Idempotency-Key` header.
* **Asynchronous Execution:** Audit creation endpoints return `HTTP 202 Accepted` with a status polling URL.

---

## 2. Complete 20-Group Endpoint Contract Catalogue

### Group 1: Auth & User Profile
* **POST `/api/v1/auth/session`**
  * *Purpose:* Exchange credentials for access & refresh tokens.
  * *Auth:* Public.
  * *Request:* `{ "email": "user@agency.com", "password": "SecurePassword123!" }`
  * *Response (200 OK):* `{ "access_token": "eyJhbGci...", "refresh_token": "...", "expires_in": 3600 }`
  * *Errors:* 400 `INVALID_CREDENTIALS`, 429 `RATE_LIMITED`.
* **GET `/api/v1/users/me`**
  * *Purpose:* Retrieve authenticated profile and active workspace/client memberships.
  * *Auth:* Authenticated user.
  * *Response (200 OK):* `{ "user_id": "uuid", "email": "...", "workspaces": [{ "workspace_id": "uuid", "role": "WORKSPACE_ADMIN", "status": "ACTIVE" }] }`
  * *Errors:* 401 `AUTHENTICATION_REQUIRED`.

### Group 2: Workspaces
* **POST `/api/v1/workspaces`**
  * *Purpose:* Create agency workspace. Assigns caller `WORKSPACE_ADMIN`.
  * *Auth:* Authenticated user.
  * *Request:* `{ "name": "Vanguard Creative", "slug": "vanguard-creative" }`
  * *Response (201 Created):* `{ "workspace_id": "uuid", "name": "...", "slug": "...", "created_at": "..." }`
  * *Errors:* 400 `VALIDATION_ERROR`, 409 `SLUG_EXISTS`.
* **GET `/api/v1/workspaces/{w_id}`**
  * *Purpose:* Retrieve workspace metadata.
  * *Auth:* Member of workspace `w_id`.
  * *Response (200 OK):* `{ "workspace_id": "uuid", "name": "...", "slug": "...", "current_role": "WORKSPACE_ADMIN" }`
  * *Errors:* 403 `WORKSPACE_MEMBERSHIP_REQUIRED`, 404 `RESOURCE_NOT_FOUND`.

### Group 3: Workspace Members
* **POST `/api/v1/workspaces/{w_id}/members`**
  * *Purpose:* Invite new workspace member.
  * *Auth:* `WORKSPACE_ADMIN` of workspace `w_id`.
  * *Request:* `{ "email": "copywriter@agency.com", "role": "CONTENT_CREATOR" }`
  * *Response (201 Created):* `{ "membership_id": "uuid", "email": "...", "role": "CONTENT_CREATOR", "status": "INVITED" }`
  * *Errors:* 403 `INSUFFICIENT_PERMISSIONS`, 409 `MEMBER_ALREADY_EXISTS`.
* **DELETE `/api/v1/workspaces/{w_id}/members/{m_id}`**
  * *Purpose:* Canonical endpoint to revoke workspace membership.
  * *Auth:* `WORKSPACE_ADMIN` of workspace `w_id`.
  * *Response (200 OK):* `{ "membership_id": "uuid", "status": "REVOKED", "revoked_at": "..." }`
  * *Errors:* 403 `INSUFFICIENT_PERMISSIONS`, 409 `LAST_ADMIN_PROTECTION`.

### Group 4: Client Brands
* **POST `/api/v1/workspaces/{w_id}/clients`**
  * *Purpose:* Provision client brand space.
  * *Auth:* `WORKSPACE_ADMIN` of workspace `w_id`.
  * *Request:* `{ "name": "Apex Cloud Security", "code": "APEX", "description": "Cloud security SaaS" }`
  * *Response (201 Created):* `{ "client_id": "uuid", "workspace_id": "uuid", "name": "...", "code": "..." }`
  * *Errors:* 403 `INSUFFICIENT_PERMISSIONS`, 409 `CLIENT_CODE_CONFLICT`.
* **GET `/api/v1/workspaces/{w_id}/clients`**
  * *Purpose:* List client brands accessible to caller.
  * *Auth:* Member of workspace `w_id`; returned client brands must be filtered to active explicit client assignments for every role, including Workspace Admin.
  * *Response (200 OK):* `{ "items": [{ "client_id": "uuid", "name": "...", "active_memory_version_id": "uuid" }] }`

### Group 5: Client Memberships
* **POST `/api/v1/workspaces/{w_id}/clients/{c_id}/members`**
  * *Purpose:* Assign workspace member to client brand.
  * *Auth:* `WORKSPACE_ADMIN` of workspace `w_id`.
  * *Request:* `{ "user_id": "uuid", "client_role": "CONTENT_CREATOR" }`
  * *Response (201 Created):* `{ "client_membership_id": "uuid", "client_id": "uuid", "user_id": "uuid", "status": "ACTIVE" }`
  * *Errors:* 404 `USER_NOT_IN_WORKSPACE`, 409 `CLIENT_ASSIGNMENT_EXISTS`.
* **DELETE `/api/v1/workspaces/{w_id}/clients/{c_id}/members/{cm_id}`**
  * *Purpose:* Canonical endpoint to revoke client brand assignment.
  * *Auth:* `WORKSPACE_ADMIN` of workspace `w_id`.
  * *Response (200 OK):* `{ "client_membership_id": "uuid", "status": "REVOKED", "revoked_at": "..." }`
  * *Errors:* 403 `INSUFFICIENT_PERMISSIONS`, 404 `RESOURCE_NOT_FOUND`.

### Group 6: Guideline Documents
* **POST `/api/v1/workspaces/{w_id}/clients/{c_id}/documents`**
  * *Purpose:* Upload brand guideline file (PDF, DOCX, TXT, MD).
  * *Auth:* Assigned `BRAND_MANAGER`.
  * *Request:* Multipart form (`file: binary`, `title: string`).
  * *Response (202 Accepted):* `{ "document_id": "uuid", "title": "...", "processing_status": "PENDING", "sha256": "..." }`
  * *Errors:* 413 `FILE_TOO_LARGE` (>20MB), 415 `UNSUPPORTED_MEDIA_TYPE`, 422 `DECOMPRESSION_BOMB_DETECTED`.

### Group 7: Extraction Status
* **GET `/api/v1/workspaces/{w_id}/clients/{c_id}/documents/{d_id}/status`**
  * *Purpose:* Poll document text extraction and candidate parsing progress.
  * *Auth:* Assigned `BRAND_MANAGER`.
  * *Response (200 OK):* `{ "document_id": "uuid", "status": "COMPLETED", "candidate_count": 28, "error_details": null }`

### Group 8: Candidate Rules
* **GET `/api/v1/workspaces/{w_id}/clients/{c_id}/candidates`**
  * *Purpose:* List staged candidate rules awaiting review.
  * *Auth:* Assigned `BRAND_MANAGER`.
  * *Response (200 OK):* `{ "items": [{ "candidate_id": "uuid", "category": "TERMINOLOGY", "payload": {...}, "review_status": "PENDING_REVIEW" }] }`
* **PATCH `/api/v1/workspaces/{w_id}/clients/{c_id}/candidates/{cand_id}`**
  * *Purpose:* Modify candidate rule text, severity, or exceptions.
  * *Auth:* Assigned `BRAND_MANAGER`.
  * *Request:* `{ "payload": {...}, "review_status": "MODIFIED_APPROVED" }`
  * *Response (200 OK):* `{ "candidate_id": "uuid", "review_status": "MODIFIED_APPROVED" }`

### Group 9: Knowledge Approval
* **POST `/api/v1/workspaces/{w_id}/clients/{c_id}/knowledge/approve`**
  * *Purpose:* Formally approve staged candidates into `brand_rules`.
  * *Auth:* Assigned `BRAND_MANAGER`.
  * *Request:* `{ "candidate_ids": ["uuid-1", "uuid-2"] }`
  * *Response (200 OK):* `{ "approved_count": 2, "rules": [{ "rule_id": "uuid", "revision_id": "uuid" }] }`

### Group 10: Living Brand Memory
* **POST `/api/v1/workspaces/{w_id}/clients/{c_id}/memory/activate`**
  * *Purpose:* Compile approved rules, publish version, commit JSONB snapshot, update active pointer.
  * *Auth:* Assigned `BRAND_MANAGER`.
  * *Request:* `{ "version_tag": "v1.0", "change_summary": "Initial release" }`
  * *Response (200 OK):* `{ "memory_version_id": "uuid", "snapshot_id": "uuid", "snapshot_hash": "...", "version_number": 1 }`
  * *Errors:* 409 `CONCURRENT_ACTIVATION_CONFLICT`, 422 `NO_APPROVED_RULES`.

### Group 11: Content Submissions
* **POST `/api/v1/workspaces/{w_id}/clients/{c_id}/assets`**
  * *Purpose:* Create campaign asset container.
  * *Auth:* Assigned `CONTENT_CREATOR`, `BRAND_MANAGER`, or `WORKSPACE_ADMIN`.
  * *Request:* `{ "title": "Q3 Launch Ad", "campaign_name": "Summer2026", "asset_type": "MIXED" }`
  * *Response (201 Created):* `{ "asset_id": "uuid", "title": "...", "current_version_number": 1 }`

### Group 12: Content Versions
* **POST `/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions`**
  * *Purpose:* Upload new draft copy and graphic iteration.
  * *Auth:* Assigned `CONTENT_CREATOR` or `BRAND_MANAGER`.
  * *Request:* `{ "raw_text": "Our platform guarantees 100% uptime...", "image_file_path": "path/banner.png" }`
  * *Response (201 Created):* `{ "version_id": "uuid", "version_number": 1, "lifecycle_state": "DRAFT", "text_sha256": "..." }`

### Group 13: Audit Execution
* **POST `/api/v1/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audits`**
  * *Purpose:* Initialize pre-flight audit against active memory snapshot.
  * *Auth:* Assigned `CONTENT_CREATOR` or `BRAND_MANAGER`.
  * *Response (202 Accepted):* `{ "audit_id": "uuid", "attempt_number": 1, "status": "PENDING", "pinned_snapshot_hash": "...", "status_url": "/api/v1/.../status" }`
  * *Errors:* 409 `CONCURRENT_ATTEMPT_RUNNING`, 422 `NO_ACTIVE_MEMORY_VERSION`.

### Group 14: Audit Status
* **GET `/api/v1/workspaces/{w_id}/clients/{c_id}/audits/{audit_id}/status`**
  * *Purpose:* Poll execution attempt progress and heartbeat.
  * *Auth:* Assigned member.
  * *Response (200 OK):* `{ "audit_id": "uuid", "attempt_number": 1, "status": "RUNNING", "heartbeat_at": "...", "checks": {"terminology": "COMPLETED", "factual": "RUNNING", "visual": "COMPLETED"} }`

### Group 15: Audit Findings
* **GET `/api/v1/workspaces/{w_id}/clients/{c_id}/audits/{audit_id}/findings`**
  * *Purpose:* Retrieve complete diagnostic scorecard and findings.
  * *Auth:* Assigned member.
  * *Response (200 OK):* `{ "audit_id": "uuid", "overall_result": "BLOCKED", "blocking_count": 2, "advisory_count": 1, "findings": [{ "finding_id": "uuid", "severity": "BLOCKING", "evidence_quote": "..." }] }`

### Group 16: Corrections
* **POST `/api/v1/workspaces/{w_id}/clients/{c_id}/findings/{f_id}/corrections`**
  * *Purpose:* Request surgical AI rewrite proposal.
  * *Auth:* Assigned `CONTENT_CREATOR` or `BRAND_MANAGER`.
  * *Response (201 Created):* `{ "correction_id": "uuid", "finding_id": "uuid", "proposed_text": "...", "diff": {...} }`
* **POST `/api/v1/workspaces/{w_id}/clients/{c_id}/findings/{f_id}/corrections/{corr_id}/accept`**
  * *Purpose:* Accept rewrite, fork new immutable asset version, trigger re-audit.
  * *Auth:* Assigned `CONTENT_CREATOR` or `BRAND_MANAGER`.
  * *Response (202 Accepted):* `{ "correction_id": "uuid", "new_asset_version_id": "uuid", "new_audit_id": "uuid", "status": "PENDING" }`

### Group 17: Human Review
* **POST `/api/v1/workspaces/{w_id}/clients/{c_id}/reviews`**
  * *Purpose:* Render review sign-off decision (`APPROVED`, `CHANGES_REQUESTED`, `REJECTED`).
  * *Auth:* Assigned `BRAND_MANAGER`.
  * *Request:* `{ "asset_version_id": "uuid", "audit_run_id": "uuid", "decision": "APPROVED", "acknowledged_finding_ids": ["uuid-adv-1"] }`
  * *Response (201 Created):* `{ "review_id": "uuid", "decision": "APPROVED", "audit_history_id": "uuid" }`
  * *Errors:* 422 `BLOCKING_VIOLATIONS_EXIST`.

### Group 18: Audit History
* **GET `/api/v1/workspaces/{w_id}/clients/{c_id}/audit-history`**
  * *Purpose:* List exportable compliance audit records.
  * *Auth:* Assigned member.
  * *Response (200 OK):* `{ "items": [{ "history_id": "uuid", "asset_id": "uuid", "content_sha256": "...", "snapshot_hash": "..." }] }`

### Group 19: Membership Revocation
* Covered by canonical endpoints:
  * `DELETE /api/v1/workspaces/{w_id}/members/{m_id}` (Group 3)
  * `DELETE /api/v1/workspaces/{w_id}/clients/{c_id}/members/{cm_id}` (Group 5)

### Group 20: Health Checks
* **GET `/api/v1/health`**
  * *Purpose:* Public unauthenticated process liveness check.
  * *Auth:* Public.
  * *Response (200 OK):* `{ "status": "alive" }`
* **GET `/api/v1/system/status`**
  * *Purpose:* Restricted operational readiness telemetry.
  * *Auth:* `WORKSPACE_ADMIN`.
  * *Response (200 OK):* `{ "status": "ready", "database": "connected", "model_provider": "configured" }`


## 3. Binding Authorization Clarifications
- Workspace Admins can provision client brands and manage assignments at workspace scope.
- Every client-scoped endpoint requires active workspace membership AND active explicit `client_memberships` assignment. No Workspace Admin bypass exists.
- Human review decisions and advisory acknowledgements are Brand Manager-only and require assignment to that client.
- The route catalogue is a planning contract, not a complete executable OpenAPI schema. Request/response DTOs, pagination, filtering, idempotency semantics and every error code must be completed and tested before implementation of each endpoint.
- `/api/v1/auth/session` is illustrative only: Supabase Auth owns credential exchange. Do not implement a second password/token issuer in FastAPI unless separately approved. The frontend should use Supabase Auth and send its access JWT to FastAPI.
