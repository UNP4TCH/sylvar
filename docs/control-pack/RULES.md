# RULES.md — Binding Engineering Laws
**Status:** Invariant  
**Enforcement:** Zero-Tolerance Automated & Manual Validation  

---

## Law 1: Exactly Three User Roles
* The system supports exactly three roles: `WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`.
* A fourth role (such as "Reviewer", "Auditor", or "Editor") is **strictly forbidden**.
* Workspace membership and client brand assignment are independent. Having `WORKSPACE_ADMIN` at the workspace level does NOT grant ambient access to client brands without explicit authorization checks.

## Law 2: Dual-Tenant Isolation by Default
* Every query executed against tenant-scoped tables MUST filter by both `workspace_id` and `client_id`.
* The application database role (`sylvar_app_user`) MUST NOT possess `SUPERUSER` or `BYPASSRLS` privileges.
* Transaction-local tenant context (`SET LOCAL app.current_workspace_id = ...`) MUST be executed inside an explicit transaction block immediately upon acquiring a connection from the pool.
* Frontend-supplied `workspace_id` or `client_id` in HTTP headers or path parameters must NEVER be trusted without server-side verification against the authenticated user's database records.

## Law 3: Canonical Audit Execution States
* Audit execution attempts and logical runs use exactly: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `INTERRUPTED`.
* **NEVER** introduce `QUEUED` or any other transient status in the database or backend contracts.
* Audit outcomes are distinct from execution states: `PASS`, `WARNINGS`, `BLOCKED`.
* Required component check failures MUST result in terminal audit outcome `BLOCKED`.

## Law 4: Epistemic Factual Outcomes
* Factual verification outcomes are strictly: `SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`.
* `UNVERIFIED` **does NOT mean false**. Absence of evidence must NEVER be classified as `CONTRADICTED` or `SUPPORTED`.
* Prompts or heuristics that attempt to force binary True/False logic onto factual claims are strictly prohibited.
* Suspected prompt injections are security signals, NOT factual claims. Do not classify an injection attempt as `UNVERIFIED`.

## Law 5: Immutable Pinned Memory Snapshots
* Every logical audit run (`audit_runs`) MUST be pinned to exactly one immutable memory snapshot (`memory_snapshot_id`).
* Retries of an audit MUST evaluate against the same pinned snapshot hash.
* If brand guidelines are modified and a new memory version is activated, existing audits remain pinned to their original snapshot. Evaluating newer knowledge requires creating a brand new logical audit run.
* Evidence references (`rule_id`, `rule_revision_id`, `evidence_quote`) MUST be validated against the exact immutable rule revision stored inside that pinned snapshot.

## Law 6: Retries and Attempt Isolation
* Every retry creates a brand new physical execution attempt (`audit_execution_attempts`) with an incremented `attempt_number`.
* All required component checks (Terminology, Factual, Visual) MUST be re-executed under the new attempt.
* Component results from different physical attempts MUST **NEVER** be combined, merged, or patched together.
* Historical execution attempts and findings are immutable and must never be overwritten or deleted.

## Law 7: Zero-Action AI Boundaries
* External foundation models (Google Gemini API) are untrusted analytical tools.
* An AI response can **NEVER** directly approve collateral, reject collateral, activate brand memory rules, invite members, modify roles, or bypass gating checks.
* AI correction suggestions are optional proposals. A creator must explicitly accept them, which forks a new immutable version and triggers a fresh pre-flight audit.

## Law 8: Linear-Light Visual Math
* Color difference calculations MUST use pure-Python NumPy implementations of the standardized CIEDE2000 ($\Delta E_{00}$) equation verified against the Sharma (2005) reference dataset.
* Semi-transparent pixels ($0 < A < 255$) MUST be converted from sRGB to linear-light RGB before compositing against the background canvas, then transformed back to sRGB for CIELAB conversion.
* Fully transparent pixels ($A = 0$) MUST be excluded from color clustering.
* Visual color deviations ($\Delta E_{00} > 5.0$) are strictly **ADVISORY** potential deviations and can NEVER independently block content approval.

## Law 9: Strict Serialization and Anti-Injection
* Untrusted user copy and guideline text must be treated as passive data payloads enclosed in structured delimiters (`<untrusted_draft>`, `<reference_facts>`).
* Raw user text must NEVER be concatenated directly into privileged instruction templates.
* All model responses MUST be schema-validated using Pydantic v2 with `extra = 'forbid'`. Invalid schemas or ungrounded citations fail closed.

## Law 10: Zero Fake Implementations
* Stubs that return hardcoded `{"status": "ok"}` without database or business logic are strictly banned.
* Never catch exceptions with `except Exception: pass`. All errors must be logged and formatted according to RFC 9457 Problem Details.
* Never claim an activity is `COMPLETE` in `TASKS.md` or reports without passing automated verification tests.


## Law 11: Human Review Authority
Only an active, explicitly assigned `BRAND_MANAGER` may approve, reject, request changes or acknowledge advisory findings. Workspace Admin cannot bypass assignment or act as reviewer.

## Law 12: No Invented Contracts or Guarantees
The 25-table list is not executable DDL and the API catalogue is not a complete DTO/OpenAPI contract. Do not invent missing schema, policies or payloads. Performance/accuracy/cost figures are unverified until measured. Verify model IDs before use.

## Law 13: Process Failure Is Not Durable Execution
In-process asyncio tasks may be lost on process termination. Persist audit/attempt state before dispatch, record component failures, and reconcile stale attempts safely after restart. Never claim durable queue semantics, exactly-once execution or guaranteed recovery.
