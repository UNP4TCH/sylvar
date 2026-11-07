# SYLVAR Round 2 Remediation Status

Date: 5 November 2026

This report describes source changes made to the isolated remediation copy. It does not imply that the user's local Windows checkout has been modified or that live Supabase/Gemini/PostgreSQL integration has been verified.

## Changes in this pass

1. **Client-brand RLS:** the client-brand policy now allows a user to read brands explicitly assigned to them across their workspaces (needed by `/users/me`), while workspace-admin visibility remains constrained to the active workspace and active `WORKSPACE_ADMIN` membership. Inserts/updates remain constrained by `WITH CHECK` to the active workspace and its active workspace admin.
2. **Review acknowledgement IDs:** the dashboard now sends the actual finding UUIDs for MAJOR, MINOR, and ADVISORY findings instead of the hard-coded `ADV-001` placeholder.
3. **Offline factual verification:** the synchronous factual-check facade no longer returns a clean heuristic PASS. When no live provider is configured, it returns FAIL with an explicit UNVERIFIED finding. The asynchronous path remains non-authoritative offline.
4. **JWKS test transport:** the MockTransport handler used by the async HTTP client test is now async, avoiding the synchronous-callback hang.
5. **Document parsing:** DOCX XML parsing uses `defusedxml`; scanned/image-only PDFs with no extractable text now return an explicit 422 instead of synthetic placeholder content.

## Verification performed

- `python -m compileall -q backend/app backend/tests`: PASS.
- Dependency installation: BLOCKED because this execution environment has no network access and cannot fetch build dependencies.
- Backend pytest: NOT RUN; dependencies are not installed in this environment.
- Frontend tests/typecheck/build: NOT RUN in this pass; frontend dependencies are not installed in this environment.
- PostgreSQL migration/RLS execution: NOT RUN; no PostgreSQL server/client is available here.
- Supabase Auth and Gemini live integration: NOT RUN.

## Remaining blockers before external integration

- PostgreSQL execution tests for client-brand policy and tenant isolation.
- Review decision transaction locking and unique certificate constraint.
- Offline audit/review semantics: keep unverified results blocked from verified approval/certification; add an explicit non-certificate demo path if a no-Gemini judging demo is required.
- Invitation reconciliation must require verified email and use a safe privileged workflow.
- Upload streaming byte cap; production config fail-closed behavior; trusted proxy rate-limit identity; prompt-injection hardening.
- Certificate signature/public verification and audit execution durability are still not implemented.

Do not describe this copy as fully production-ready. The current work fixes targeted source defects but requires independent review and live integration tests.
